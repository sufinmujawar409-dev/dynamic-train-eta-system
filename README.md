# Dynamic ETA

Production foundation for a Dynamic ETA service, with a FastAPI backend and a Vite React TypeScript frontend.

## Project structure

- `backend/app` — FastAPI application
- `backend/app/db` — SQLAlchemy database engine, session, models, and initialization
- `backend/alembic` — database migrations
- `frontend` — Vite React TypeScript application
- `ml` — DEMO ETA training dataset, training script, and versioned artifact
- `docs` — project documentation

## Setup

### Backend


From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

### Database configuration

Copy `.env.example` to `.env` and set `DATABASE_URL` for PostgreSQL. Do not
commit `.env` or real credentials:

```text
DATABASE_URL=postgresql+psycopg://postgres:change-me@localhost:5432/dynamic_eta
```

If `DATABASE_URL` is not set, the application uses a local SQLite file
(`dynamic_eta_dev.db`) so the API can start during early development. This
fallback is not intended for production. PostgreSQL connection errors are not
hidden when a PostgreSQL URL is configured.

Install PostgreSQL separately, create the `dynamic_eta` database, and ensure
the PostgreSQL server is running before applying migrations.

### Frontend and 3D visualization

```powershell
cd frontend
npm install
```

The frontend is a responsive React/TypeScript operations dashboard with a
DEMO-labelled interactive Leaflet railway map. It uses `leaflet` and
`react-leaflet` for the route, station markers, selected train position,
zoom, pan, and map controls. It includes desktop sidebar
and mobile bottom navigation sections for Overview, Live Trains, 3D Map,
Alerts, Analytics, and Settings, plus Light/Dark/System theme persistence.
Set `VITE_API_BASE_URL` to point at the API; it defaults to
`http://127.0.0.1:8000`. The dashboard calls the existing `/api/trains`,
`/api/trains/{id}/live`, `/route`, and `/eta` endpoints and provides loading,
empty, and error states.

### Phase 8 data integration foundation

The ingestion path is provider-based:

```text
TrainDataProvider -> normalization and validation -> ETA service -> REST/WebSocket -> dashboard
WeatherProvider   -> weather metadata and ETA risk factor
```

`DemoDataAdapter` is the safe local fallback and labels every result as
`DEMO`/`SIMULATED`. `LiveRailwayDataProvider` is an adapter boundary for a
future authorized railway or GPS integration; it does not call, scrape, or
simulate any railway API. A live provider must be supplied by implementing the
documented provider contract and configuring its authorized endpoint and key.

The canonical train snapshot validates train IDs, timezone-aware timestamps,
coordinates, speed, delay, freshness, source, liveness, and data quality.
`GET /api/trains/metadata` exposes the selected provider, model version,
weather configuration, and realtime interval. Train, live-position, ETA, and
WebSocket responses expose source/freshness metadata, ETA confidence, and
weather status. Incoming events are persisted when a matching database train
record exists.

### Environment variables

Copy `.env.example` to `.env` for local configuration. Never commit secrets:

```text
DATA_PROVIDER=demo
RAILWAY_API_BASE_URL=
RAILWAY_API_KEY=
WEATHER_API_BASE_URL=
WEATHER_API_KEY=
STALE_AFTER_SECONDS=30
REALTIME_INTERVAL_SECONDS=2
```

`DATA_PROVIDER=demo` requires no external credentials. `DATA_PROVIDER=live`
requires both railway settings and returns a clear unavailable/configuration
error until an authorized provider implementation is supplied. Weather is
optional; when it is not configured, the API returns `Weather data unavailable`
and does not invent temperature, precipitation, wind, or visibility values.

### OpenWeather integration

When `OPENWEATHER_API_KEY` is present in the root `.env`, the existing weather
provider uses the OpenWeather Current Weather endpoint with the train's current
latitude and longitude. Successful observations are marked `source=OPENWEATHER`,
`data_quality=LIVE`, and include temperature, feels-like temperature, humidity,
wind speed, visibility, precipitation when supplied, and the observation time.
Missing keys, timeouts, non-success responses, and malformed payloads produce
`source=UNAVAILABLE` and never appear as live weather. The railway provider is
unchanged and remains separately authorized/provider-based.

## Run

Start the backend from the repository root:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Start the frontend in a second terminal:

```powershell
cd frontend
npm run dev
```

The backend health check is available at `http://127.0.0.1:8000/health` and returns:

```json
{ "status": "ok", "service": "dynamic-train-eta", "environment": "development" }
```

## Train API

The development adapter exposes clearly labelled `DEMO` data only. It is not
live railway data:

- `GET /api/trains`
- `GET /api/trains/{train_id}`
- `GET /api/trains/{train_id}/live`
- `GET /api/trains/{train_id}/route`
- `GET /api/trains/{train_id}/eta`

Run backend tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
```

### DEMO ML pipeline

The bundled `ml\historical_eta_demo.csv` is synthetic demonstration data, not
railway history. Train and evaluate the RandomForestRegressor (MAE, RMSE, R2)
and write the model plus metadata artifact with:

```powershell
.\.venv\Scripts\python.exe -m ml.train
```

The baseline uses `current_speed`, `current_delay`, `distance_remaining`,
`historical_delay`, `previous_station_delay`, `section_average_speed`,
`weather_factor`, `congestion_factor`, and `signal_halt_minutes` to predict ETA
minutes to the next station. The generated metadata records the model version
and evaluation metrics.

The API loads `ml\artifacts\eta_model.joblib` through the validated reusable
prediction service. Focused ML/API tests can be run with:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
```

### Database migrations and verification

From the repository root, with `DATABASE_URL` configured:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Verify the migration state:

```powershell
.\.venv\Scripts\python.exe -m alembic current
```

The initial migration creates the `trains`, `stations`, `train_routes`,
`train_positions`, `eta_predictions`, and `alerts` tables. The default API
provider remains the explicitly labelled DEMO adapter. Migration `0002` adds
`data_source` and `data_quality` to position and ETA records. Persistence is
best-effort so an unavailable database does not interrupt the realtime stream.

## Scope

The current system provides a DEMO realtime stream, an authorized live-provider
interface, weather-provider interface, validated ETA enrichment, and responsive
interactive map visualization and additive realtime persistence. It does not implement
authentication, deployment, online retraining, or an actual railway/GPS/weather
API integration.
Actual railway live data requires an authorized data source and its documented
integration contract.

### RailRadar diagnostic integration

The RailRadar adapter is diagnostic-only and is not selected by the main
application provider factory. The single opt-in endpoint is:

```text
GET /api/diagnostics/railradar?train_number=<train-number>
```

The upstream request is fixed to the official documented contract:

```text
GET https://api.railradar.in/v1/trains/{number}/live
Authorization: Bearer <RAILWAY_API_KEY>
?authoritative=true&geometry=true&format=geojson&includeCoordinates=true
```

The adapter maps the documented `data.*` fields and GeoJSON coordinates
explicitly. The endpoint performs one request and returns normalized telemetry
marked `LIVE` only after a successful, validated response. DEMO mode, the
frontend, ETA WebSocket, and main train service remain unchanged.

### Phase 12 alerts and control-room analytics

Realtime telemetry is evaluated by the alert engine after weather enrichment and
ETA prediction. It supports delay, major delay, approaching station, unusual
stoppage, ETA change, stale data, unavailable source, and weather-impact rules.
Alerts have `INFO`, `WARNING`, or `CRITICAL` severity, cooldown deduplication,
acknowledgement, source, quality, and metadata.

Alert endpoints:

- `GET /api/alerts` with `train_id`, `severity`, `type`, and `acknowledged` filters
- `GET /api/alerts/{alert_id}`
- `POST /api/alerts/{alert_id}/acknowledge`
- `GET /api/trains/analytics`

New alerts are included in `WS /ws/trains/{train_id}` events. The dashboard
shows alert severity, acknowledgement controls, realtime warning/critical
notifications, and source-labelled operational analytics. DEMO metrics remain
explicitly marked as DEMO-derived; they are not railway operational claims.
