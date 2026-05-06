FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential zlib1g-dev libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY client-examples/generate_weather_backgrounds.py /app/generate_weather_backgrounds.py
COPY client-examples/weatherlib /app/weatherlib

RUN pip install --no-cache-dir pillow \
    && python generate_weather_backgrounds.py --width 10 --height 10 --output-dir weather-backgrounds --skip-viewer

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/weather-backgrounds /app/weather-backgrounds

ENV PATH="/opt/venv/bin:${PATH}"

COPY client-examples/weather.py /app/weather.py
COPY client-examples/wallclient /app/wallclient
COPY client-examples/weatherlib /app/weatherlib

ENTRYPOINT ["python", "-u", "weather.py"]
