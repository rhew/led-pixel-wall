from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import unescape
from typing import Optional

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT = 10
USER_AGENT = "led-pixel-wall-trailstatus/1.0"
TMTB_MOBILE_STATUS_URL = "https://www.trianglemtb.com/mobiletrailstatus.php"

_ANCHOR_RE = re.compile(
    r"<a\b(?P<attrs>[^>]*)href=(?P<quote>[\"'])(?P<href>.*?)(?P=quote)(?P<rest>[^>]*)>"
    r"(?P<label>.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WIDGET_STATUS_SPAN_RE = re.compile(r"<span\b[^>]*>", re.IGNORECASE | re.DOTALL)
_ATTR_RE_TEMPLATE = r'{name}=(?P<quote>["\'])(?P<value>.*?)(?P=quote)'
_WIDGET_DATE_RE = re.compile(
    r'<li\b[^>]*class=(?P<quote>["\'])date(?P=quote)[^>]*>\s*(?P<date>.*?)\s*</li>',
    re.IGNORECASE | re.DOTALL,
)
_WIDGET_STATUS_LINK_RE = re.compile(
    r'<a\b[^>]*href=(?P<quote>["\'])(?P<href>https://www\.trailforks\.com/region/.*?/status/)(?P=quote)',
    re.IGNORECASE | re.DOTALL,
)
_STATUS_PAGE_TIME_RE = re.compile(
    r'<div\b[^>]*class=(?P<quote>["\'])fullTime(?P=quote)[^>]*data-sort=(?P<sort_quote>["\'])(?P<sort>\d+)(?P=sort_quote)[^>]*>(?P<label>.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class TrailStatus:
    name: str
    status: str
    updated: Optional[str]
    detail_url: str
    trailforks_region_id: Optional[int]
    trailforks_widget_url: Optional[str]
    trailforks_status_url: Optional[str]
    updated_epoch: Optional[int]


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _build_scraper():
    if cloudscraper is None:
        raise RuntimeError("cloudscraper is required to fetch Trailforks widget status")

    return cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "linux", "desktop": True}
    )


def _fetch_widget_text(url: str, scraper=None) -> str:
    if scraper is None:
        scraper = _build_scraper()
    response = scraper.get(url, headers={"Referer": TMTB_MOBILE_STATUS_URL}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def _fetch_status_page_text(url: str, scraper=None) -> str:
    if scraper is None:
        scraper = _build_scraper()
    response = scraper.get(url, headers={"Referer": TMTB_MOBILE_STATUS_URL}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def _strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub(" ", value))).strip()


def _normalize_status(raw_status: str) -> str:
    value = raw_status.strip().lower()
    synonyms = {
        "all clear / green": "open",
        "green": "open",
        "good to go": "open",
        "hero dirt": "open",
        "dry": "open",
        "muddy": "wet",
        "hold": "closed",
        "red": "closed",
        "yellow": "caution",
    }
    value = synonyms.get(value, value)
    if "green" in value or "all clear" in value:
        return "open"
    if "red" in value or "closed" in value:
        return "closed"
    if "yellow" in value or "caution" in value:
        return "caution"
    if value == "freeze thaw":
        return "freeze-thaw"
    return value


def _extract_widget_status(widget_html: str) -> str:
    match = _WIDGET_STATUS_SPAN_RE.search(widget_html)
    if match:
        span_tag = match.group(0)
        title_match = re.search(_ATTR_RE_TEMPLATE.format(name="title"), span_tag, re.IGNORECASE | re.DOTALL)
        class_match = re.search(_ATTR_RE_TEMPLATE.format(name="class"), span_tag, re.IGNORECASE | re.DOTALL)
        title = _strip_tags(title_match.group("value")) if title_match else ""
        classes = class_match.group("value").lower() if class_match else ""
        if title:
            return _normalize_status(title)
        if "sgreen" in classes:
            return "open"
        if "sred" in classes:
            return "closed"
        if "syellow" in classes:
            return "caution"

    return "unknown"


def _extract_widget_updated(widget_html: str) -> Optional[str]:
    match = _WIDGET_DATE_RE.search(widget_html)
    if match:
        value = _strip_tags(match.group("date")).strip()
        return value.removeprefix("on ").strip()

    return None


def _extract_widget_status_url(widget_html: str) -> Optional[str]:
    match = _WIDGET_STATUS_LINK_RE.search(widget_html)
    if not match:
        return None
    return match.group("href")


def _extract_precise_updated_epoch(status_page_html: str) -> Optional[int]:
    matches = _STATUS_PAGE_TIME_RE.findall(status_page_html)
    if not matches:
        return None

    epochs: list[int] = []
    for match in matches:
        sort_value = match[2]
        try:
            epochs.append(int(sort_value))
        except ValueError:
            continue
    if not epochs:
        return None
    return max(epochs)


def _extract_trailforks_widget_info(segment_html: str, base_url: str) -> tuple[Optional[int], Optional[str]]:
    iframe_match = re.search(
        r"<iframe\b[^>]*src=(?P<quote>[\"'])(?P<src>.*?)(?P=quote)",
        segment_html,
        re.IGNORECASE | re.DOTALL,
    )
    if not iframe_match:
        return None, None

    widget_url = urllib.parse.urljoin(base_url, iframe_match.group("src"))
    parsed = urllib.parse.urlparse(widget_url)
    query = urllib.parse.parse_qs(parsed.query)
    rid_values = query.get("rid", [])
    if not rid_values:
        return None, widget_url

    try:
        rid = int(rid_values[0])
    except ValueError:
        rid = None
    return rid, widget_url


def _is_trail_link(label: str, href: str) -> bool:
    cleaned_label = _strip_tags(label)
    if not cleaned_label:
        return False

    lowered_label = cleaned_label.lower()
    if lowered_label in {"click here", "trianglemtb", "home"}:
        return False

    parsed = urllib.parse.urlparse(href)
    path = parsed.path.lower()
    if not path.endswith(".php"):
        return False
    if "mobiletrailstatus" in path:
        return False
    if path.endswith("/index.php") or path == "/":
        return False
    return True


def parse_tmtb_trail_statuses(html: str, base_url: str = TMTB_MOBILE_STATUS_URL) -> list[TrailStatus]:
    matches = [match for match in _ANCHOR_RE.finditer(html) if _is_trail_link(match.group("label"), match.group("href"))]
    results: list[TrailStatus] = []

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        segment_html = html[start:end]
        name = _strip_tags(match.group("label"))
        detail_url = urllib.parse.urljoin(base_url, match.group("href"))
        trailforks_region_id, trailforks_widget_url = _extract_trailforks_widget_info(
            segment_html,
            base_url,
        )
        results.append(
            TrailStatus(
                name=name,
                status="unknown",
                updated=None,
                detail_url=detail_url,
                trailforks_region_id=trailforks_region_id,
                trailforks_widget_url=trailforks_widget_url,
                trailforks_status_url=None,
                updated_epoch=None,
            )
        )

    if not results:
        raise RuntimeError("No trail entries found in TriangleMTB trail status HTML")
    return results


def fetch_tmtb_trail_statuses(url: str = TMTB_MOBILE_STATUS_URL) -> list[TrailStatus]:
    trails = parse_tmtb_trail_statuses(_fetch_text(url), base_url=url)
    results: list[TrailStatus] = []
    scraper = _build_scraper()

    for trail in trails:
        try:
            if not trail.trailforks_widget_url:
                results.append(trail)
                continue

            widget_html = _fetch_widget_text(trail.trailforks_widget_url, scraper=scraper)
            status_page_url = _extract_widget_status_url(widget_html)
            updated_epoch = None
            if status_page_url:
                status_page_html = _fetch_status_page_text(status_page_url, scraper=scraper)
                updated_epoch = _extract_precise_updated_epoch(status_page_html)
            results.append(
                TrailStatus(
                    name=trail.name,
                    status=_extract_widget_status(widget_html),
                    updated=_extract_widget_updated(widget_html),
                    detail_url=trail.detail_url,
                    trailforks_region_id=trail.trailforks_region_id,
                    trailforks_widget_url=trail.trailforks_widget_url,
                    trailforks_status_url=status_page_url,
                    updated_epoch=updated_epoch,
                )
            )
        except Exception as exc:
            LOGGER.warning("Trailforks fetch failed for %s: %s", trail.name, exc)
            results.append(trail)

    return results
