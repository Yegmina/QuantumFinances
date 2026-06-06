export const pestelLabels = {
  political: "Political",
  economic: "Economic",
  social: "Social",
  technological: "Technological",
  environmental: "Environmental",
  legal: "Legal"
};

export function formatPercent(value) {
  const percent = Number(value || 0) * 100;
  if (percent > 0 && percent < 1) return `${percent.toFixed(2)}%`;
  if (percent > 0 && percent < 10) return `${percent.toFixed(1)}%`;
  return `${Math.round(percent)}%`;
}

export function probabilitySentence(result) {
  if (!result) return "Awaiting Q-FIN analysis";
  return `${formatPercent(result.eventProbability.probability)} event probability`;
}

export function sortedScenarioSimilarities(result) {
  if (!result) return [];
  return result.eventProbability.scenarioSimilarities
    .slice()
    .sort((left, right) => right.weightedContribution - left.weightedContribution);
}

export function quantumIntegrityLabel(receipt) {
  if (!receipt) return "No quantum receipt";
  return receipt.hardwareJobSubmitted
    ? `Hardware submitted to ${receipt.targetProvider}`
    : `Local quantum receipt, target later: ${receipt.targetProvider}`;
}

export function weightTotal(weights) {
  return Object.values(weights).reduce((sum, value) => sum + Number(value || 0), 0);
}

export function normalizedWeights(weights) {
  const total = weightTotal(weights) || 1;
  return Object.fromEntries(
    Object.entries(weights).map(([key, value]) => [key, Number(value || 0) / total])
  );
}
