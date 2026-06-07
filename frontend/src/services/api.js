const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8088";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed with status ${response.status}`);
  }

  return response.json();
}

export function health() {
  return request("/api/health");
}

export function listSnapshots() {
  return request("/api/source/snapshots");
}

export function buildSeries(snapshotIds) {
  return request("/api/series/build", {
    method: "POST",
    body: JSON.stringify({ snapshotIds })
  });
}

export function runScenarioEngine(payload) {
  return request("/api/run", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export { API_BASE };
