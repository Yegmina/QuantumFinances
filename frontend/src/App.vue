<template>
  <div class="app-shell">
    <header class="site-header reveal">
      <div class="brand-mark">
        <span class="brand-icon" aria-hidden="true"></span>
        <div>
          <p class="brand-name">Q-FIN</p>
          <p class="brand-tag">Scenario intelligence</p>
        </div>
      </div>
    </header>

    <section class="hero">
      <div class="hero-copy reveal reveal-delay-1">
        <p class="eyebrow">Event probability</p>
        <h1>See what <em>comes next</em> before the market does.</h1>
        <p class="lead">Turn market snapshots into weekly PESTEL states, branching futures, and a calibrated event probability — each run sealed with a quantum circuit receipt.</p>
      </div>
      <aside class="hero-stat reveal reveal-delay-2">
        <span class="hero-stat-value">{{ result ? formatPercent(result.eventProbability.probability) : "—" }}</span>
        <span class="hero-stat-label">{{ probabilitySentenceText }}</span>
      </aside>
    </section>

    <section class="panel reveal reveal-delay-3">
      <div class="panel-heading compact">
        <div>
          <p class="section-kicker">Market periods</p>
          <h2>Select snapshots</h2>
        </div>
        <button type="button" @click="loadInitialState">Refresh</button>
      </div>
      <div class="snapshot-strip">
        <label v-for="snapshot in snapshots" :key="snapshot.id" class="snapshot-choice">
          <input v-model="selectedSnapshotIds" type="checkbox" :value="snapshot.id" />
          <span>{{ snapshot.label }}</span>
        </label>
      </div>
    </section>

    <section class="work-grid">
      <article class="panel reveal reveal-delay-4">
        <div class="panel-heading compact">
          <div>
            <p class="section-kicker">Your question</p>
            <h2>Describe the event</h2>
          </div>
        </div>
        <label class="input-label" for="eventText">Future event</label>
        <textarea id="eventText" v-model="eventText" rows="4" placeholder="What outcome are you evaluating?"></textarea>

        <div class="ai-note">
          <strong>Q-FIN decides</strong>
          <span>Scenario count, calibration weights, future vectors, and the probability score are set automatically.</span>
        </div>

        <button
          class="primary-button"
          type="button"
          :disabled="running || !ready"
          @click="runEngine"
        >
          {{ running ? "Analyzing scenarios…" : "Run scenario analysis" }}
        </button>
      </article>

      <article class="panel presentation-panel reveal reveal-delay-5" :class="{ 'has-result': !!result }">
        <p class="section-kicker">Probability</p>

        <div class="presentation-metric">
          <span class="presentation-number" :class="{ 'is-placeholder': !result }">
            {{ result ? formatPercent(result.eventProbability.probability) : "—" }}
          </span>
          <span class="presentation-unit">{{ result ? "event probability" : "awaiting analysis" }}</span>
        </div>

        <p class="presentation-headline">
          {{ result ? result.eventProbability.calibrationLabel : "Run an analysis to calculate your probability" }}
        </p>

        <p class="presentation-copy">
          {{
            result
              ? result.eventProbability.explanation
              : "Q-FIN calibrates weekly PESTEL states, branches futures, and scores your event with weighted similarity."
          }}
        </p>
      </article>
    </section>

    <section v-if="series.length" class="panel pipeline-panel reveal reveal-delay-6">
      <div class="panel-heading">
        <div>
          <p class="section-kicker">Pipeline</p>
          <h2>From market graph to probability</h2>
        </div>
      </div>

      <div class="pipeline-flow">
        <div v-for="stage in pipelineStages" :key="stage.label" class="flow-step">
          <span>{{ stage.index }}</span>
          <strong>{{ stage.label }}</strong>
          <em>{{ stage.value }}</em>
        </div>
      </div>

      <div class="pipeline-viz-grid">
        <article class="viz-block cluster-block">
          <p class="section-kicker">Clusters</p>
          <h3>Source link graph</h3>
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
          <h3>Weekly PESTEL matrix</h3>
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

        <article class="viz-block branch-block">
          <p class="section-kicker">Branches</p>
          <h3>Alternative futures</h3>
          <div v-if="result" class="branch-stack">
            <div v-for="scenario in result.forecastScenarios" :key="scenario.id" class="branch-row">
              <span>{{ scenario.id }}</span>
              <div class="branch-line"><i :style="{ width: formatPercent(scenario.probability) }"></i></div>
              <strong>{{ formatPercent(scenario.probability) }}</strong>
            </div>
          </div>
          <p v-else class="muted">Run an analysis to explore future PESTEL states.</p>
        </article>

        <article class="viz-block event-match-block">
          <p class="section-kicker">Event match</p>
          <h3>Interest vector similarity</h3>
          <div v-if="result" class="event-vector">
            <div v-for="(value, key) in result.eventProbability.eventVector" :key="key" class="bar-row compact-row">
              <em>{{ pestelLabels[key] }}</em>
              <div class="bar"><span :style="{ width: formatPercent(value) }"></span></div>
              <b>{{ formatPercent(value) }}</b>
            </div>
          </div>
          <p v-else class="muted">Your event is scored against each scenario using weighted similarity.</p>
        </article>

        <article class="viz-block result-block">
          <p class="section-kicker">Result</p>
          <h3>{{ result ? formatPercent(result.eventProbability.probability) : "—" }}</h3>
          <p class="muted">{{ result ? result.eventProbability.explanation : "Combines scenario fit with event plausibility." }}</p>
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
          <p class="section-kicker">Timeline</p>
          <h2>Weekly PESTEL snapshots</h2>
        </div>
        <button type="button" @click="loadSeries">Rebuild</button>
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
        <h2>Possible futures</h2>
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
        <p class="section-kicker">Event probability</p>
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
        <p class="section-kicker">Calibration</p>
        <h2>Analysis settings</h2>
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
        <p class="section-kicker">Quantum receipt</p>
        <h2>{{ result.quantumRun.localRunId }}</h2>
        <div class="receipt-grid">
          <span>Mode</span><strong>{{ result.quantumRun.executionMode }}</strong>
          <span>Qubits</span><strong>{{ result.quantumRun.qubits }}</strong>
          <span>Depth</span><strong>{{ result.quantumRun.depth }}</strong>
          <span>Shots</span><strong>{{ result.quantumRun.shots }}</strong>
        </div>
        <details class="technical-details">
          <summary>Circuit details</summary>
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

    <footer v-if="result" class="site-footer">
      <strong>Quantum receipt</strong> — {{ result.integrity.message }}
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { buildSeries, health, listSnapshots, runScenarioEngine } from "./services/api";
import {
  formatPercent,
  pestelLabels,
  probabilitySentence,
  sortedScenarioSimilarities
} from "./services/viewModel";

const ready = ref(false);
const running = ref(false);
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
  { index: "01", label: "Snapshots", value: `${series.value.length || selectedSnapshotIds.value.length} weeks` },
  { index: "02", label: "Cluster graph", value: `${graphMetrics.value.clusters} clusters` },
  { index: "03", label: "PESTEL vectors", value: "P E S T E L" },
  { index: "04", label: "Future branches", value: result.value ? `${result.value.forecastScenarios.length} scenarios` : "Awaiting run" },
  { index: "05", label: "Event similarity", value: result.value ? formatPercent(result.value.eventProbability.probability) : "Awaiting run" },
  { index: "06", label: "Circuit receipt", value: result.value?.quantumRun.localRunId || "Awaiting run" }
]);

function heatStyle(value) {
  const intensity = Math.max(0, Math.min(1, Number(value || 0)));
  return {
    backgroundColor: `rgba(0, 43, 92, ${0.06 + intensity * 0.22})`,
    color: intensity > 0.5 ? "#ffffff" : "#001a38"
  };
}

async function loadInitialState() {
  try {
    await health();
    const payload = await listSnapshots();
    snapshots.value = payload.snapshots;
    selectedSnapshotIds.value = snapshots.value.map((snapshot) => snapshot.id);
    ready.value = snapshots.value.length > 0;
    await loadSeries();
  } catch {
    ready.value = false;
    snapshots.value = [];
    selectedSnapshotIds.value = [];
    series.value = [];
  }
}

async function loadSeries() {
  if (!selectedSnapshotIds.value.length) return;
  try {
    const payload = await buildSeries(selectedSnapshotIds.value);
    series.value = payload.weeklyPestelSeries;
  } catch {
    series.value = [];
  }
}

async function runEngine() {
  running.value = true;
  try {
    result.value = await runScenarioEngine({
      snapshotIds: selectedSnapshotIds.value,
      eventText: eventText.value,
      useOpenAi: true
    });
    series.value = result.value.weeklyPestelSeries;
  } catch {
    /* silent — launch UI avoids surfacing raw API errors */
  } finally {
    running.value = false;
  }
}

onMounted(loadInitialState);
</script>
