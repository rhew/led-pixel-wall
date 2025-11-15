import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional, Tuple

REQUEST_TIMEOUT = 10
USER_AGENT = "led-pixel-wall-weather/1.0"
GEOCODER_URL = "https://nominatim.openstreetmap.org/search"


def _fetch_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/geo+json, application/json",
        },
    )
    if headers:
        for key, value in headers.items():
            req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        charset = resp.headers.get_content_charset() or "utf-8"
        data = resp.read().decode(charset)
    return json.loads(data)


def geocode_location(query: str) -> Tuple[float, float]:
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
    }
    url = GEOCODER_URL + "?" + urllib.parse.urlencode(params)
    data = _fetch_json(url)
    if not data:
        raise RuntimeError(f"Geocoder returned no matches for '{query}'")
    entry = data[0]
    lat = entry.get("lat")
    lon = entry.get("lon")
    if lat is None or lon is None:
        raise RuntimeError("Geocoder response missing coordinates")
    return float(lat), float(lon)


def _parse_iso_timestamp(value: str) -> Optional[datetime]:
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def fetch_point_properties(lat: float, lon: float) -> dict:
    point_url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
    return _fetch_json(point_url).get("properties", {})


def _c_to_f(value_c: float) -> float:
    return value_c * 9.0 / 5.0 + 32.0


def fetch_latest_observation(stations_url: str) -> Tuple[Optional[int], Optional[str]]:
    stations = _fetch_json(stations_url)
    for feature in stations.get("features", []):
        station_id = feature.get("id")
        if not station_id:
            continue
        try:
            obs = _fetch_json(f"{station_id}/observations/latest")
        except Exception as exc:
            print(f"Failed to read observation from {station_id}: {exc}")
            continue

        props = obs.get("properties", {})
        temp_obj = props.get("temperature")
        timestamp_str = props.get("timestamp")
        if not (temp_obj and temp_obj.get("value") is not None and timestamp_str):
            continue

        timestamp = _parse_iso_timestamp(timestamp_str)
        age_seconds = None
        if timestamp:
            age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()
            if age_seconds > 3600:
                print(
                    f"Observation from {station_id} stale ({int(age_seconds)}s old); trying next station."
                )
                continue

        unit_code = (temp_obj.get("unitCode") or "").lower()
        temp_value = float(temp_obj["value"])
        if "celsius" in unit_code or unit_code.endswith("degc"):
            temp_f = _c_to_f(temp_value)
        elif "fahrenheit" in unit_code or unit_code.endswith("degf"):
            temp_f = temp_value
        else:
            print(f"Unknown observation unit '{unit_code}', assuming Celsius")
            temp_f = _c_to_f(temp_value)

        print(
            "Fetched NOAA temperature from observation: "
            f"{int(round(temp_f))}°F "
            f"(age {int(age_seconds) if age_seconds is not None else 'unknown'}s,"
            f" station {station_id})"
        )
        icon_url = props.get("icon") or ""
        return int(round(temp_f)), icon_url

    print("No fresh observations available.")
    return None, None


def extract_icon_code(icon_url: Optional[str]) -> str:
    if not icon_url:
        return ""
    parts = urllib.parse.urlparse(icon_url)
    segments = [segment for segment in parts.path.split("/") if segment]
    if not segments:
        return ""
    last_segment = segments[-1]
    base = last_segment.split(",")[0].strip().lower()
    return base


def fetch_observation_temp_and_icon(stations_url: str) -> Tuple[int, str]:
    temp, icon_url = fetch_latest_observation(stations_url)
    if temp is None:
        raise RuntimeError("No fresh observations available")
    icon_code = extract_icon_code(icon_url)
    return temp, icon_code
