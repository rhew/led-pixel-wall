from typing import Dict, List, Tuple

FRAME_INTERVAL_SEC = 1.0
DEFAULT_ANIMATION_KEY = "clear"
DAY_DIGIT_COLOR = (255, 220, 60)
NIGHT_DIGIT_COLOR = (200, 200, 200)

FALLBACK_DAY_COLOR = (80, 120, 80)
FALLBACK_NIGHT_COLOR = (0, 30, 0)

DIGITS_3X5: Dict[str, List[str]] = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["1", "1", "1", "1", "1"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    "-": ["00", "00", "11", "00", "00"],
    "?": ["111", "001", "011", "000", "010"],
    " ": ["000", "000", "000", "000", "000"],
}

ICON_ANIMATIONS = {
    "clear": {
        "day": "weather-backgrounds/clear-day.png",
        "night": "weather-backgrounds/clear-night.png",
    },
    "cloudy": {
        "day": "weather-backgrounds/cloudy-day.png",
        "night": "weather-backgrounds/cloudy-night.png",
    },
    "overcast": {
        "day": "weather-backgrounds/overcast-day.png",
        "night": "weather-backgrounds/overcast-night.png",
    },
    "rain": {
        "day": "weather-backgrounds/rain-day.png",
        "night": "weather-backgrounds/rain-night.png",
    },
    "thunder": {
        "day": "weather-backgrounds/thunder-day.png",
        "night": "weather-backgrounds/thunder-night.png",
    },
    "snow": {
        "day": "weather-backgrounds/snow-day.png",
        "night": "weather-backgrounds/snow-night.png",
    },
    "sleet": {
        "day": "weather-backgrounds/sleet-day.png",
        "night": "weather-backgrounds/sleet-night.png",
    },
    "fog": {
        "day": "weather-backgrounds/fog-day.png",
        "night": "weather-backgrounds/fog-night.png",
    },
    "severe": {
        "day": "weather-backgrounds/severe.png",
        "night": "weather-backgrounds/severe.png",
    },
}

ICON_CODE_TO_KEY = {
    "skc": "clear",
    "few": "clear",
    "wind_skc": "clear",
    "wind_few": "clear",
    "hot": "clear",
    "cold": "clear",
    "sct": "cloudy",
    "bkn": "cloudy",
    "ovc": "overcast",
    "wind_sct": "cloudy",
    "wind_bkn": "cloudy",
    "wind_ovc": "overcast",
    "rain": "rain",
    "rain_showers": "rain",
    "rain_showers_hi": "rain",
    "rain_sleet": "rain",
    "rain_fzra": "rain",
    "rain_snow": "snow",
    "fzra": "rain",
    "tsra": "thunder",
    "tsra_sct": "thunder",
    "tsra_hi": "thunder",
    "sleet": "sleet",
    "snow": "snow",
    "snow_sleet": "snow",
    "snow_fzra": "snow",
    "blizzard": "snow",
    "fog": "fog",
    "dust": "fog",
    "smoke": "fog",
    "haze": "fog",
    "tornado": "severe",
    "hurricane": "severe",
    "tropical_storm": "severe",
}

