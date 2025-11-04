# NOAA Icon to LED Animation Mapping

Animations change with time of day. The table below lists the currently supported NOAA icon codes and the PNG assets they map to. All assets live under `weather-backgrounds/`.

| Icon codes | Description | Animation (day / night) |
| ---------- | ----------- | ----------------------- |
| `skc`, `few`, `wind_skc`, `wind_few`, `hot`, `cold` | Clear skies | `clear-day.png` / `clear-night.png` |
| `sct`, `bkn`, `ovc`, `wind_sct`, `wind_bkn`, `wind_ovc` | Partly to mostly cloudy | `cloudy-day.png` / `cloudy-night.png` |
| `rain`, `rain_showers`, `rain_showers_hi`, `rain_sleet`, `rain_fzra`, `fzra` | Rain | `rain-day.png` / `rain-night.png` |
| `tsra`, `tsra_sct`, `tsra_hi` | Thunderstorms | `thunder-day.png` / `thunder-night.png` |
| `snow`, `snow_sleet`, `snow_fzra`, `rain_snow`, `sleet`, `blizzard` | Frozen precipitation | `snow-day.png` / `snow-night.png` |
| `fog`, `dust`, `smoke`, `haze` | Reduced visibility | `fog-day.png` / `fog-night.png` |
| `tornado`, `hurricane`, `tropical_storm` | Severe weather | `severe.png` |

Any icon code not listed falls back to the clear animation.

Icon data source: https://api.weather.gov/icons/
