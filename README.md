# Order Tracker

A small order tracking app for the AI Dev Tools Zoomcamp observability homework. It includes a web page, API, tests, and a Docker Compose observability stack. The exercise covers telemetry, alerts, and incident response.

The main user flow is creating an order and checking its status. Three sample orders are created on first startup.

## Run it

You need Docker with Compose. To run the tests, you also need Python 3.11+ and `uv`.

```bash
docker compose up --build -d --wait
```

Open <http://127.0.0.1:8000>. Grafana is at <http://127.0.0.1:3000> (default login `admin` / `admin`); the provisioned **Order Tracker** dashboard shows request counts and errors. Incident-response runs at <http://127.0.0.1:8001> and accepts Grafana alerts at `POST /alerts`. It saves alert payloads and Loki/Tempo evidence in a persistent volume, then starts Copilot CLI for firing alerts.

To enable Copilot CLI in the incident-response container, set `COPILOT_GITHUB_TOKEN` to a GitHub token with Copilot access before running Compose. Do not commit the token. Without it, alerts are still saved and enriched; Copilot is not launched.

Order metrics, logs, and traces are sent to the OpenTelemetry Collector and stored in Prometheus, Loki, and Tempo. App, incident, and telemetry data are stored in Docker volumes and survive container recreation.

If port 8000 is occupied, set `ORDER_TRACKER_PORT`, for example:

```bash
ORDER_TRACKER_PORT=18080 docker compose up --build -d --wait
```

Run tests with `uv run --frozen pytest -q`. Stop the app with `docker compose down`. Add `-v` only if you also want to delete the order data.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Web page |
| GET | `/healthz` | Database health check |
| GET | `/api/orders` | List orders |
| POST | `/api/orders` | Create an order |
| GET | `/api/orders/{id}` | Check an order |
| PATCH | `/api/orders/{id}` | Change an order status |

The incident-response service accepts Grafana webhooks at `POST /alerts`. Saved incidents can be listed with `GET /incidents` or fetched with `GET /incidents/{incident_id}`.

The app uses SQLite to keep setup small. Run one app container at a time. The course exercise is about detecting and handling an incident, not scaling the database.

When running outside Docker Compose without an OTLP endpoint, the app exports telemetry to the console. In Compose, the app sends its metrics, logs, and traces to the Collector over OTLP.
