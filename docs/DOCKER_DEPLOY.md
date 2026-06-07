# Docker Deployment

QuantumFinances runs as two containers:

- `backend`: FastAPI on port `8088` inside the Docker network.
- `frontend`: Nginx serving the built Vue app and proxying `/api`, `/docs`, and `/openapi.json` to the backend.

## Local Container Run

```powershell
cd C:\Users\teres\PycharmProjects\q-oracle-scenario-sim
docker compose up --build
```

Open:

```text
http://127.0.0.1:8080
```

The app works with bundled sample snapshots if no external source is configured.

## Environment

Create a local `.env` file if you want OpenAI or external snapshots:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.5
QFIN_WEB_PORT=8080

# Optional external source
SOURCE_BASE_URL=
SOURCE_SNAPSHOT_MANIFEST_URL=
SOURCE_SNAPSHOT_URLS=
```

Do not commit `.env`.

## Production-Style Run

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Default public port is `80` in `docker-compose.prod.yml`. Override it with:

```powershell
$env:QFIN_WEB_PORT="8080"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

## Health Checks

```powershell
docker compose ps
docker compose logs backend
docker compose logs frontend
```

Backend health through Nginx:

```text
http://127.0.0.1:8080/api/health
```

## Build Images Without Running

```powershell
docker compose build
```

## Stop

```powershell
docker compose down
```
