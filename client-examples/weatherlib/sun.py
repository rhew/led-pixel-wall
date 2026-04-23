from datetime import datetime, timedelta, time as dtime
from typing import Tuple

from .noaa import _fetch_json, _parse_iso_timestamp

SUN_API_URL = "https://api.sunrise-sunset.org/json"


def _fetch_sun_cycle(lat: float, lon: float, tzinfo) -> Tuple[datetime, datetime, float]:
    url = f"{SUN_API_URL}?lat={lat:.4f}&lng={lon:.4f}&formatted=0"
    data = _fetch_json(url)
    results = data.get("results", {})
    sunrise = _parse_iso_timestamp(results.get("sunrise", ""))
    sunset = _parse_iso_timestamp(results.get("sunset", ""))
    if not sunrise or not sunset:
        raise RuntimeError("Sunrise/sunset data missing from API response")
    sunrise_local = sunrise.astimezone(tzinfo)
    sunset_local = sunset.astimezone(tzinfo)
    # Refresh after the day these times apply to has rolled over so we always fetch
    # a new cycle instead of re-fetching the same date.
    next_refresh_date = sunrise_local.date() + timedelta(days=1)
    midnight_plus = datetime.combine(next_refresh_date, dtime(0, 0), tzinfo=tzinfo) + timedelta(seconds=1)
    print(
        "Sun cycle: "
        f"sunrise={sunrise_local.isoformat()}, "
        f"sunset={sunset_local.isoformat()} (local)"
    )
    return sunrise_local, sunset_local, midnight_plus.timestamp()


def _is_daytime(local_now: datetime, sunrise: datetime, sunset: datetime) -> bool:
    if sunrise <= sunset:
        return sunrise <= local_now < sunset
    return not (sunset <= local_now < sunrise)


class SunTracker:
    def __init__(self, lat: float, lon: float, tzinfo):
        self.lat = lat
        self.lon = lon
        self.tzinfo = tzinfo
        self.sunrise = datetime.now(tzinfo)
        self.sunset = datetime.now(tzinfo)
        self.refresh_ts = 0.0
        self.refresh()

    def refresh(self) -> None:
        self.sunrise, self.sunset, self.refresh_ts = _fetch_sun_cycle(
            self.lat, self.lon, self.tzinfo
        )

    def update_if_needed(self) -> None:
        now = datetime.now(self.tzinfo)
        if now.timestamp() >= self.refresh_ts:
            try:
                self.refresh()
            except Exception as exc:
                print(f"Failed to refresh sunrise/sunset data: {exc}")
                # Fall forward one day so we don't get stuck on the previous night's
                # times if the API is unavailable at midnight.
                if now.date() > self.sunrise.date():
                    self.sunrise += timedelta(days=1)
                    self.sunset += timedelta(days=1)
                self.refresh_ts = now.timestamp() + 3600

    def is_day(self) -> bool:
        return _is_daytime(datetime.now(self.tzinfo), self.sunrise, self.sunset)
