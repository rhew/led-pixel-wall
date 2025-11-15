FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY client-examples/generate_weather_backgrounds.py /app/generate_weather_backgrounds.py

RUN pip install --no-cache-dir pillow \
    && python generate_weather_backgrounds.py --width 10 --height 5 --output-dir weather-backgrounds

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY client-examples/weather.py /app/weather.py
COPY client-examples/weatherlib /app/weatherlib
COPY --from=builder /app/weather-backgrounds /app/weather-backgrounds

RUN pip install --no-cache-dir pillow

ENTRYPOINT ["python", "-u", "weather.py"]
