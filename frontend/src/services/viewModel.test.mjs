import assert from "node:assert/strict";
import {
  formatPercent,
  normalizedWeights,
  probabilitySentence,
  quantumIntegrityLabel,
  sortedScenarioSimilarities
} from "./viewModel.js";

assert.equal(formatPercent(0.704), "70%");
assert.equal(formatPercent(0.0002), "0.02%");
assert.equal(formatPercent(0.062), "6.2%");
assert.deepEqual(normalizedWeights({ economic: 2, legal: 1 }), { economic: 2 / 3, legal: 1 / 3 });

const result = {
  eventProbability: {
    probability: 0.72,
    scenarioSimilarities: [
      { scenarioId: "b", weightedContribution: 0.1 },
      { scenarioId: "a", weightedContribution: 0.3 }
    ]
  }
};

assert.equal(probabilitySentence(result), "72% event probability");
assert.equal(sortedScenarioSimilarities(result)[0].scenarioId, "a");
assert.equal(
  quantumIntegrityLabel({ hardwareJobSubmitted: false, targetProvider: "ibm_runtime_sampler_v2_later" }),
  "Local quantum receipt, target later: ibm_runtime_sampler_v2_later"
);

console.log("Frontend view-model tests passed.");
