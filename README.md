# Q-FIN

Standalone scenario engine for market intelligence snapshots, PESTEL vectors, future scenario branches, event probability scoring, and quantum circuit receipts.

Q-FIN can run from bundled sample snapshots or from a configured external JSON snapshot source. No private upstream system is required for the public platform.

## Structure

```text
backend/           FastAPI scenario API
frontend/          Vue 3 platform UI
docs/              runbook and platform notes
quantum_hardware/  IBM/IQM/QMill hardware preparation scripts
```

## Backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8088 --reload
```

The backend reads `OPENAI_API_KEY` from the environment and defaults to `gpt-5.5`.

Optional configuration:

```powershell
$env:OPENAI_MODEL="gpt-5.5"
$env:QUANTUMFINANCES_REQUEST_TIMEOUT_SECONDS="90"
```

## Frontend

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5179
```

Open `http://127.0.0.1:5179`.

## Docker

Build and run the full stack with Docker Compose:

```powershell
docker compose up --build
```

Open `http://127.0.0.1:8080`. The frontend is served by Nginx and proxies `/api` to the FastAPI backend. For production-style deployment:

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

See `docs/DOCKER_DEPLOY.md` for environment variables, health checks, and stop commands.

## External Snapshot Source

Use a manifest:

```powershell
$env:SOURCE_BASE_URL="https://your-source-host"
$env:SOURCE_SNAPSHOT_MANIFEST_URL="https://your-source-host/snapshots.json"
```

or direct URLs:

```powershell
$env:SOURCE_SNAPSHOT_URLS="https://your-source-host/graph_2026_w21.json,https://your-source-host/graph_2026_w22.json"
```

If no source is configured, the backend uses bundled sample snapshots.

## Tests

```powershell
cd backend
pytest

cd ..\frontend
npm run test
npm run build
```

## Quantum Hardware Preparation

The `quantum_hardware/` folder prepares real provider runs without submitting by default.

```powershell
cd quantum_hardware
python .\scripts\prepare_run_payload.py --event "Company becomes the biggest in its market after AI investment and market growth"
python .\scripts\ibm_sampler_v2_submit.py --input .\inputs\latest_run.json --dry-run
```

Use `--submit` only when provider credentials are configured and you are ready to spend hardware time.
