FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    mosquitto \
    mosquitto-clients \
    jq \
    bluez \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml requirements.txt /app/
COPY sengled_bridge /app/sengled_bridge
COPY mosquitto /app/mosquitto
COPY run.sh /app/run.sh

RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt \
    && /opt/venv/bin/pip install --no-cache-dir -e /app \
    && chmod +x /app/run.sh

EXPOSE 8080/tcp 8883/tcp 9080/udp

CMD ["/app/run.sh"]
