import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Optional, Tuple

REQUEST_TIMEOUT = 10
USER_AGENT = "led-pixel-wall-weather/1.0"
GEOCODER_URL = "https://nominatim.openstreetmap.org/search"
FRESH_OBSERVATION_MAX_AGE_SECONDS = 3600
RED_OBSERVATION_MIN_AGE_SECONDS = 7200
MAX_STATIONS_TO_CHECK = 10


@dataclass
class ObservationChoice:
    temp_f: int
    icon_url: str
    indicator_level: Optional[str]
    station_id: str
    age_seconds: int
    station_rank: int


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


def _parse_observation_choice(
    station_id: str,
    station_rank: int,
    observation: dict,
    indicator_level: Optional[str],
) -> Optional[ObservationChoice]:
    props = observation.get("properties", {})
    temp_obj = props.get("temperature")
    timestamp_str = props.get("timestamp")
    if not (temp_obj and temp_obj.get("value") is not None and timestamp_str):
        return None

    timestamp = _parse_iso_timestamp(timestamp_str)
    if timestamp is None:
        return None

    age_seconds = int((datetime.now(timezone.utc) - timestamp).total_seconds())
    unit_code = (temp_obj.get("unitCode") or "").lower()
    temp_value = float(temp_obj["value"])
    if "celsius" in unit_code or unit_code.endswith("degc"):
        temp_f = _c_to_f(temp_value)
    elif "fahrenheit" in unit_code or unit_code.endswith("degf"):
        temp_f = temp_value
    else:
        print(f"Unknown observation unit '{unit_code}', assuming Celsius")
        temp_f = _c_to_f(temp_value)

    return ObservationChoice(
        temp_f=int(round(temp_f)),
        icon_url=props.get("icon") or "",
        indicator_level=indicator_level,
        station_id=station_id,
        age_seconds=age_seconds,
        station_rank=station_rank,
    )


def _fetch_station_choice(
    station_id: str,
    station_rank: int,
    indicator_level: Optional[str],
) -> Optional[ObservationChoice]:
    try:
        observation = _fetch_json(f"{station_id}/observations/latest")
    except Exception as exc:
        print(f"Failed to read observation from {station_id}: {exc}")
        return None

    choice = _parse_observation_choice(
        station_id,
        station_rank,
        observation,
        indicator_level,
    )
    if choice is None:
        return None

    freshness = "fresh" if choice.age_seconds < FRESH_OBSERVATION_MAX_AGE_SECONDS else "stale"
    print(
        f"Station {station_id} rank {station_rank}: "
        f"{choice.temp_f}°F age={choice.age_seconds}s {freshness}"
    )
    return choice


def _is_fresh(choice: ObservationChoice) -> bool:
    return choice.age_seconds < FRESH_OBSERVATION_MAX_AGE_SECONDS


def indicator_level_for_choice(choice: ObservationChoice) -> Optional[str]:
    if choice.age_seconds >= RED_OBSERVATION_MIN_AGE_SECONDS:
        return "red"
    if choice.station_rank == 1 and _is_fresh(choice):
        return None
    return "yellow"


def _with_indicator(choice: ObservationChoice, indicator_level: str) -> ObservationChoice:
    return replace(choice, indicator_level=indicator_level)


def fetch_best_observation(stations_url: str) -> Optional[ObservationChoice]:
    stations = _fetch_json(stations_url)
    features = stations.get("features", [])[:MAX_STATIONS_TO_CHECK]
    if not features:
        return None

    closest_but_stale: Optional[ObservationChoice] = None
    nearby_but_stale: Optional[ObservationChoice] = None
    distant_but_stale: Optional[ObservationChoice] = None

    first_station_id = features[0].get("id")
    if first_station_id:
        first_choice = _fetch_station_choice(first_station_id, 1, None)
        if first_choice is not None:
            if _is_fresh(first_choice):
                return first_choice
            closest_but_stale = _with_indicator(first_choice, "yellow")

    for station_rank, feature in enumerate(features[1:5], start=2):
        station_id = feature.get("id")
        if not station_id:
            continue
        choice = _fetch_station_choice(station_id, station_rank, "yellow")
        if choice is None:
            continue
        if _is_fresh(choice):
            return choice
        if nearby_but_stale is None:
            nearby_but_stale = _with_indicator(choice, "red")

    for station_rank, feature in enumerate(features[5:], start=6):
        station_id = feature.get("id")
        if not station_id:
            continue
        choice = _fetch_station_choice(station_id, station_rank, "red")
        if choice is None:
            continue
        if _is_fresh(choice):
            return choice
        if distant_but_stale is None:
            distant_but_stale = _with_indicator(choice, "red")

    if closest_but_stale is not None:
        return closest_but_stale
    if nearby_but_stale is not None:
        return nearby_but_stale
    if distant_but_stale is not None:
        return distant_but_stale

    return None


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


def fetch_observation_temp_and_icon(stations_url: str) -> Tuple[int, str, Optional[str]]:
    choice = fetch_best_observation(stations_url)
    if choice is None:
        raise RuntimeError("No usable observations available")
    indicator_level = indicator_level_for_choice(choice)
    if indicator_level is not None:
        choice = _with_indicator(choice, indicator_level)
    icon_code = extract_icon_code(choice.icon_url)
    print(
        f"Selected station {choice.station_id} rank {choice.station_rank} "
        f"age={choice.age_seconds}s indicator={indicator_level_for_choice(choice) or 'none'}"
    )
    return choice.temp_f, icon_code, choice.indicator_level
