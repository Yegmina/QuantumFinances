<template>
  <main class="app-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">QuantumFinances</p>
        <h1>QuantumFinances Scenario Engine</h1>
        <p class="lead">Market intelligence snapshots become clustered graph signals, weekly PESTEL vectors, future scenario branches, event probability scores, and a quantum circuit receipt.</p>
      </div>
      <div class="hero-status">
        <span :class="['status-pill', backendOnline ? 'ok' : 'bad']">{{ backendOnline ? "Backend online" : "Backend offline" }}</span>
        <span class="status-pill ok">Pipeline ready</span>
      </div>
    </section>

    <section class="panel connection-panel">
      <div class="panel-heading">
        <div>
          <p class="section-kicker">Connection</p>
          <h2>Market Intelligence Source</h2>
        </div>
        <button type="button" @click="loadInitialState">Refresh</button>
      </div>
      <div class="connection-grid">
        <div>
          <span class="label">Backend</span>
          <strong>{{ apiBase }}</strong>
        </div>
        <div>
          <span class="label">Source mode</span>
          <strong>{{ snapshotPayload?.sourceConnection?.mode || "unknown" }}</strong>
        </div>
        <div>
          <span class="label">Snapshots</span>
          <strong>{{ snapshots.length }}</strong>
        </div>
        <div>
          <span class="label">Engine</span>
          <strong>{{ healthPayload?.engineMode || "QuantumFinances pipeline" }}</strong>
        </div>
      </div>
      <p v-if="error" class="error-text">{{ error }}</p>
      <div class="snapshot-list">
        <label v-for="snapshot in snapshots" :key="snapshot.id" class="snapshot-choice">
          <input v-model="selectedSnapshotIds" type="checkbox" :value="snapshot.id" />
          <span>{{ snapshot.label }}</span>
        </label>
      </div>
    </section>

    <section class="work-grid">
      <article class="panel">
        <div class="panel-heading compact">
          <div>
            <p class="section-kicker">Scenario Engine</p>
            <h2>Event Query</h2>
          </div>
        </div>
        <label class="input-label" for="eventText">Event</label>
        <textarea id="eventText" v-model="eventText" rows="4"></textarea>

        <div class="ai-note">
          <strong>QuantumFinances decides</strong>
          <span>Scenario count, shots, seed, event vector, PESTEL weights, future vectors, and scenario probabilities.</span>
        </div>

        <button class="primary-button" type="button" :disabled="running || selectedSnapshotIds.length === 0" @click="runEngine">
          {{ running ? "Running QuantumFinances pipeline..." : "Run QuantumFinances pipeline" }}
        </button>
      </article>

      <article class="panel presentation-panel">
        <p class="section-kicker">Presentation Mode</p>
        <h2>{{ probabilitySentenceText }}</h2>
        <p v-if="result" class="presentation-number">{{ formatPercent(result.eventProbability.probability) }}</p>
        <p class="presentation-copy">{{ result ? result.eventProbability.calibrationLabel : "Source adapter, graph clustering, PESTEL calibration, temporal scenarios, event scoring, and circuit receipt." }}</p>
      </article>
    </section>

    <section v-if="series.length" class="panel pipeline-panel">
      <div class="panel-heading">
        <div>
          <p class="section-kicker">Pipeline Map</p>
          <h2>Source Graph To Scenario Probability</h2>
        </div>
        <strong class="run-chip">{{ result ? result.runId : "Awaiting run" }}</strong>
      </div>

      <div class="pipeline-flow">
        <div v-for="stage in pipelineStages" :key="stage.label" class="flow-step">
          <span>{{ stage.index }}</span>
            <strong>{{ stage.label }}</strong>
          <em>{{ stage.value }}</em>
        </div>
      </div>

      <div class="pipeline-viz-grid">
        <article class="viz-block">
          <p class="section-kicker">Graph Clusters</p>
          <h3>Source Link Graph</h3>
          <svg class="graph-svg" viewBox="0 0 320 180" role="img" aria-label="source graph cluster sketch">
            <line x1="62" y1="52" x2="162" y2="32" />
            <line x1="62" y1="52" x2="134" y2="98" />
            <line x1="162" y1="32" x2="250" y2="70" />
            <line x1="134" y1="98" x2="250" y2="70" />
            <line x1="134" y1="98" x2="210" y2="142" />
            <line x1="250" y1="70" x2="210" y2="142" />
            <circle cx="62" cy="52" r="18" />
            <circle cx="162" cy="32" r="14" />
            <circle cx="134" cy="98" r="22" />
            <circle cx="250" cy="70" r="17" />
            <circle cx="210" cy="142" r="15" />
            <text x="62" y="57">C1</text>
            <text x="162" y="37">C2</text>
            <text x="134" y="103">C3</text>
            <text x="250" y="75">C4</text>
            <text x="210" y="147">C5</text>
          </svg>
          <div class="metric-strip">
            <div><span>Clusters</span><strong>{{ graphMetrics.clusters }}</strong></div>
            <div><span>Links</span><strong>{{ graphMetrics.edges }}</strong></div>
            <div><span>Weeks</span><strong>{{ series.length }}</strong></div>
          </div>
        </article>

        <article class="viz-block vector-block">
          <p class="section-kicker">Vectors</p>
          <h3>Weekly PESTEL Matrix</h3>
          <div class="vector-matrix">
            <span></span>
            <b v-for="key in pestelKeys" :key="key">{{ key.slice(0, 3) }}</b>
            <template v-for="week in series" :key="week.weekId">
              <strong>{{ week.weekId }}</strong>
              <span
                v-for="key in pestelKeys"
                :key="`${week.weekId}-${key}`"
                class="heat-cell"
                :style="heatStyle(week.pestel[key])"
              >
                {{ formatPercent(week.pestel[key]) }}
              </span>
            </template>
          </div>
        </article>

        <article class="viz-block">
          <p class="section-kicker">Branches</p>
          <h3>Alternative Futures</h3>
          <div v-if="result" class="branch-stack">
            <div v-for="scenario in result.forecastScenarios" :key="scenario.id" class="branch-row">
              <span>{{ scenario.id }}</span>
              <div class="branch-line"><i :style="{ width: formatPercent(scenario.probability) }"></i></div>
              <strong>{{ formatPercent(scenario.probability) }}</strong>
            </div>
          </div>
          <p v-else class="muted">Run the pipeline to branch Wn into future PESTEL states.</p>
        </article>

        <article class="viz-block">
          <p class="section-kicker">Event Match</p>
          <h3>Interest Vector Similarity</h3>
          <div v-if="result" class="event-vector">
            <div v-for="(value, key) in result.eventProbability.eventVector" :key="key" class="bar-row compact-row">
              <em>{{ pestelLabels[key] }}</em>
              <div class="bar"><span :style="{ width: formatPercent(value) }"></span></div>
              <b>{{ formatPercent(value) }}</b>
            </div>
          </div>
          <p v-else class="muted">The event text becomes an interest vector for weighted cosine comparison.</p>
        </article>

        <article class="viz-block result-block">
          <p class="section-kicker">Result</p>
          <h3>{{ result ? formatPercent(result.eventProbability.probability) : "Pending" }}</h3>
          <p class="muted">{{ result ? result.eventProbability.explanation : "P(event) combines scenario fit with event plausibility." }}</p>
          <div v-if="result" class="score-formula">
            <span>Vector fit</span><strong>{{ formatPercent(result.eventProbability.vectorFit) }}</strong>
            <span>Plausibility</span><strong>{{ formatPercent(result.eventProbability.plausibilityFactor) }}</strong>
            <span>Final</span><strong>{{ formatPercent(result.eventProbability.probability) }}</strong>
          </div>
        </article>
      </div>
    </section>

    <section v-if="series.length" class="panel">
      <div class="panel-heading">
        <div>
          <p class="section-kicker">PESTEL Timeline</p>
          <h2>Weekly World-State Vectors</h2>
        </div>
        <button type="button" @click="loadSeries">Rebuild series</button>
      </div>
      <div class="timeline">
        <div v-for="week in series" :key="week.weekId" class="week-card">
          <strong>{{ week.weekId }}</strong>
          <span>{{ week.label }}</span>
          <div v-for="(value, key) in week.pestel" :key="key" class="bar-row">
            <em>{{ pestelLabels[key] }}</em>
            <div class="bar"><span :style="{ width: formatPercent(value) }"></span></div>
            <b>{{ formatPercent(value) }}</b>
          </div>
        </div>
      </div>
    </section>

    <section v-if="result" class="results-grid">
      <article class="panel">
        <p class="section-kicker">Forecast</p>
        <h2>Alternative Future PESTEL Vectors</h2>
        <div class="scenario-list">
          <div v-for="scenario in result.forecastScenarios" :key="scenario.id" class="scenario-card">
            <div class="scenario-head">
              <strong>{{ scenario.label }}</strong>
              <span>{{ formatPercent(scenario.probability) }}</span>
            </div>
            <p>{{ scenario.explanation }}</p>
            <div class="mini-vector">
              <span v-for="(value, key) in scenario.pestel" :key="key">{{ key.slice(0, 3) }} {{ formatPercent(value) }}</span>
            </div>
          </div>
        </div>
      </article>

      <article class="panel">
        <p class="section-kicker">Event Probability</p>
        <h2>{{ formatPercent(result.eventProbability.probability) }}</h2>
        <p class="muted">{{ result.eventProbability.explanation }}</p>
        <div class="score-formula wide">
          <span>Scenario vector fit</span><strong>{{ formatPercent(result.eventProbability.vectorFit) }}</strong>
          <span>Event plausibility</span><strong>{{ formatPercent(result.eventProbability.plausibilityFactor) }}</strong>
          <span>Final probability</span><strong>{{ formatPercent(result.eventProbability.probability) }}</strong>
        </div>
        <div class="similarity-list compact-details">
          <div v-for="item in scenarioSimilarities" :key="item.scenarioId" class="similarity-row">
            <span>{{ item.scenarioId }}</span>
            <div class="bar"><span :style="{ width: formatPercent(item.similarity) }"></span></div>
            <strong>{{ formatPercent(item.similarity) }}</strong>
          </div>
        </div>
      </article>

      <article class="panel">
        <p class="section-kicker">Engine Decision</p>
        <h2>QuantumFinances</h2>
        <p class="muted">{{ result.engineDecision.rationale }}</p>
        <div class="decision-grid">
          <div><span>Scenarios</span><strong>{{ result.engineDecision.scenarioCount }}</strong></div>
          <div><span>Shots</span><strong>{{ result.engineDecision.shots }}</strong></div>
          <div><span>Seed</span><strong>{{ result.engineDecision.seed }}</strong></div>
          <div><span>Confidence</span><strong>{{ formatPercent(result.engineDecision.confidence) }}</strong></div>
        </div>
        <div class="weight-readout">
          <div v-for="(value, key) in result.engineDecision.dimensionWeights" :key="key" class="bar-row">
            <em>{{ pestelLabels[key] }}</em>
            <div class="bar"><span :style="{ width: formatPercent(value) }"></span></div>
            <b>{{ value.toFixed(2) }}</b>
          </div>
        </div>
      </article>

      <article class="panel quantum-panel">
        <p class="section-kicker">Circuit Receipt</p>
        <h2>{{ result.quantumRun.localRunId }}</h2>
        <div class="receipt-grid">
          <span>Mode</span><strong>{{ result.quantumRun.executionMode }}</strong>
          <span>Qubits</span><strong>{{ result.quantumRun.qubits }}</strong>
          <span>Depth</span><strong>{{ result.quantumRun.depth }}</strong>
          <span>Shots</span><strong>{{ result.quantumRun.shots }}</strong>
        </div>
        <details class="technical-details">
          <summary>Technical circuit details</summary>
          <div class="counts">
            <div v-for="(count, key) in result.quantumRun.counts" :key="key">
              <span>{{ key }}</span>
              <div class="bar"><span :style="{ width: formatPercent(count / result.quantumRun.shots) }"></span></div>
              <strong>{{ count }}</strong>
            </div>
          </div>
          <pre>{{ result.quantumRun.circuitQasm }}</pre>
        </details>
      </article>
    </section>

    <section v-if="result" class="integrity">
      <strong>Integrity:</strong>
      {{ result.integrity.message }}
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { API_BASE, buildSeries, health, listSnapshots, runScenarioEngine } from "./services/api";
import {
  formatPercent,
  pestelLabels,
  probabilitySentence,
  sortedScenarioSimilarities
} from "./services/viewModel";

const apiBase = API_BASE;
const backendOnline = ref(false);
const error = ref("");
const running = ref(false);
const healthPayload = ref(null);
const snapshotPayload = ref(null);
const snapshots = ref([]);
const selectedSnapshotIds = ref([]);
const series = ref([]);
const result = ref(null);
const eventText = ref("Company becomes the biggest in its market after AI investment and market growth");
const pestelKeys = Object.keys(pestelLabels);

const probabilitySentenceText = computed(() => probabilitySentence(result.value));
const scenarioSimilarities = computed(() => sortedScenarioSimilarities(result.value));
const graphMetrics = computed(() => {
  const activeSeries = result.value?.weeklyPestelSeries || series.value;
  return activeSeries.reduce(
    (totals, week) => ({
      clusters: totals.clusters + Number(week.clusterCount || 0),
      edges: totals.edges + Number(week.edgeCount || 0)
    }),
    { clusters: 0, edges: 0 }
  );
});

const pipelineStages = computed(() => [
  { index: "01", label: "Source snapshots", value: `${series.value.length || selectedSnapshotIds.value.length} weeks` },
  { index: "02", label: "Cluster graph", value: `${graphMetrics.value.clusters} clusters` },
  { index: "03", label: "PESTEL vectors", value: "P E S T E L" },
  { index: "04", label: "Future branches", value: result.value ? `${result.value.forecastScenarios.length} scenarios` : "pending" },
  { index: "05", label: "Event similarity", value: result.value ? formatPercent(result.value.eventProbability.probability) : "pending" },
  { index: "06", label: "Circuit receipt", value: result.value?.quantumRun.localRunId || "pending" }
]);

function heatStyle(value) {
  const intensity = Math.max(0, Math.min(1, Number(value || 0)));
  return {
    backgroundColor: `rgba(30, 138, 122, ${0.14 + intensity * 0.76})`,
    color: intensity > 0.55 ? "#ffffff" : "#17202a"
  };
}

async function loadInitialState() {
  error.value = "";
  try {
    healthPayload.value = await health();
    backendOnline.value = true;
    snapshotPayload.value = await listSnapshots();
    snapshots.value = snapshotPayload.value.snapshots;
    selectedSnapshotIds.value = snapshots.value.map((snapshot) => snapshot.id);
    await loadSeries();
  } catch (err) {
    backendOnline.value = false;
    error.value = err instanceof Error ? err.message : "Could not reach QuantumFinances backend.";
  }
}

async function loadSeries() {
  if (!selectedSnapshotIds.value.length) return;
  const payload = await buildSeries(selectedSnapshotIds.value);
  series.value = payload.weeklyPestelSeries;
}

async function runEngine() {
  running.value = true;
  error.value = "";
  try {
    result.value = await runScenarioEngine({
      snapshotIds: selectedSnapshotIds.value,
      eventText: eventText.value,
      useOpenAi: true
    });
    series.value = result.value.weeklyPestelSeries;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Run failed.";
  } finally {
    running.value = false;
  }
}

onMounted(loadInitialState);
</script>
