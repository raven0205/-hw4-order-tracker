FROM node:22-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global @github/copilot

WORKDIR /srv/incident-response
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY incident_service.py ./

RUN mkdir -p /data && useradd --create-home --uid 10001 incident-response \
    && chown -R incident-response:incident-response /data /srv/incident-response
USER incident-response

ENV INCIDENT_DB_PATH=/data/incidents.sqlite3 \
    COPILOT_CLI=/usr/local/bin/copilot
EXPOSE 8001
CMD ["uvicorn", "incident_service:app", "--host", "0.0.0.0", "--port", "8001"]
