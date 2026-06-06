from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib import request


def post_json(url: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a Q-FIN run payload for hardware execution.")
    parser.add_argument("--backend-url", default=os.getenv("QUANTUMFINANCES_BACKEND_URL", "http://127.0.0.1:8088"))
    parser.add_argument("--event", required=True)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "inputs" / "latest_run.json"))
    parser.add_argument("--scenario-count", type=int, default=None)
    parser.add_argument("--shots", type=int, default=512)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--no-ai", action="store_true", help="Use the local baseline instead of the AI-calibrated engine.")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    payload = {
        "eventText": args.event,
        "shots": args.shots,
        "seed": args.seed,
        "useOpenAi": not args.no_ai,
    }
    if args.scenario_count is not None:
        payload["scenarioCount"] = args.scenario_count

    result = post_json(f"{args.backend_url.rstrip('/')}/api/run", payload, args.timeout)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote hardware payload: {output_path}")
    print(f"Run id: {result.get('runId')}")
    print(f"Event probability: {result.get('eventProbability', {}).get('probability')}")


if __name__ == "__main__":
    main()

