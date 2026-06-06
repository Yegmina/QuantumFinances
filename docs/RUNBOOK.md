# Q-FIN Runbook

## Full Local Run

1. Export `OPENAI_API_KEY`.
2. Optionally configure an external snapshot source with either `SOURCE_SNAPSHOT_MANIFEST_URL` or `SOURCE_SNAPSHOT_URLS`.
3. Start the backend:

```powershell
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8088 --reload
```

4. Start the frontend:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5179
```

5. Open:

```text
http://127.0.0.1:5179
```

## Expected Platform Flow

1. Connection panel shows source mode:
   - `sample` when bundled sample snapshots are active.
   - `external` when snapshot URLs are configured.
2. PESTEL timeline shows weekly vectors.
3. Enter an event, for example:

```text
Company becomes the biggest in its market after AI investment and market growth
```

4. Run the Q-FIN pipeline.
5. The engine returns PESTEL weights, event vector, scenario count, shots, seed, future vectors, calibrated event probability, and explanation.
6. Show:
   - source graph,
   - PESTEL vector matrix,
   - forecast alternatives,
   - event probability,
   - similarity and plausibility breakdown,
   - circuit receipt.

## Quantum Integrity Rules

Do not claim real quantum hardware unless the run includes:

- provider name,
- backend name,
- real job ID,
- exact circuit,
- shot count,
- raw counts,
- timestamp,
- input vectors.

The current circuit receipt keeps this machine-readable flag until a provider job is attached:

```json
{
  "executionMode": "circuit_receipt",
  "hardwareJobSubmitted": false
}
```

## Later Hardware Run

Implement hardware submission as a separate path:

- Add a provider runtime endpoint.
- Keep circuits tiny because free quantum time is limited.
- Store real hardware receipts separately from local receipts.
