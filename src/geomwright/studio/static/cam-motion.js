import { formatNumber, t } from "./i18n.js";

const panel = document.querySelector("#cam-motion-panel");
const toolbar = document.querySelector("#cam-motion-toolbar");
const wrap = panel.closest(".canvas-wrap");
const profileButton = document.querySelector("#cam-profile-view");
const chartButton = document.querySelector("#cam-chart-view");
const grid = document.querySelector("#cam-motion-grid");
const slider = document.querySelector("#cam-motion-angle");
const readout = document.querySelector("#cam-motion-readout");
const stateLabel = document.querySelector("#cam-motion-state");
const coordinateLabel = document.querySelector("#cam-motion-coordinate");
const SVG = "http://www.w3.org/2000/svg";
const W = 500, H = 210, LEFT = 64, RIGHT = 18, TOP = 18, BOTTOM = 38;
const descriptors = [
  { key: "lift", symbol: "S", unit: "mm" },
  { key: "velocity", symbol: "V", unit: "mm/rad" },
  { key: "acceleration", symbol: "A", unit: "mm/rad²" },
  { key: "jerk", symbol: "J", unit: "mm/rad³" },
];
let data = null, showCharts = false, previewState = "ready", selectedIndex = 0;
let cursors = [];

function svgElement(tag, attrs = {}, text = null) {
  const element = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, String(value));
  if (text !== null) element.textContent = text;
  return element;
}

function showView(charts) {
  showCharts = Boolean(data && charts);
  toolbar.hidden = !data;
  panel.hidden = !showCharts;
  wrap.classList.toggle("has-cam-motion", Boolean(data));
  wrap.classList.toggle("cam-charts-visible", showCharts);
  profileButton.setAttribute("aria-pressed", String(!showCharts));
  chartButton.setAttribute("aria-pressed", String(showCharts));
}

function validPayload(candidate) {
  const count = candidate?.theta_deg?.length;
  return count >= 2 && count <= 10000 && candidate.theta_deg.every((v, i, a) =>
    Number.isFinite(v) && (i === 0 || v > a[i - 1])) &&
    [...descriptors.map(d => d.key), "valve_lift"].every(key =>
      candidate[key]?.length === count && candidate[key].every(Number.isFinite));
}

function nearestIndex(angle) {
  const values = data.theta_deg;
  let low = 0, high = values.length - 1;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (values[mid] < angle) low = mid + 1;
    else high = mid;
  }
  return low > 0 && angle - values[low - 1] < values[low] - angle ? low - 1 : low;
}

function renderState() {
  if (!data) return;
  const stale = previewState !== "ready";
  panel.classList.toggle("motion-stale", stale);
  stateLabel.textContent = t(stale ? "camchart.stale" : data.has_warnings ?
    "camchart.warnings" : "camchart.sampled");
}

function selectPoint(index) {
  if (!data) return;
  selectedIndex = Math.max(0, Math.min(data.theta_deg.length - 1, index));
  slider.value = String(selectedIndex);
  const angle = data.theta_deg[selectedIndex];
  const stage = data.windows.find(w => angle >= w.from_deg - 1e-8 && angle <= w.to_deg + 1e-8);
  const stageText = stage ? t(`camchart.stage.${stage.key}`) : "";
  const parts = [`${formatNumber(angle, 2)}°`, stageText,
    ...descriptors.map(d => `${d.symbol} = ${formatNumber(data[d.key][selectedIndex], 3)} ${t(`camchart.unit.${d.key}`, d.unit)}`),
    `${t("camchart.valve")} = ${formatNumber(data.valve_lift[selectedIndex], 3)} ${t("camchart.unit.lift")}`];
  readout.textContent = parts.filter(Boolean).join(" · ");
  slider.setAttribute("aria-valuetext", `${formatNumber(angle, 2)}° · ${stageText}`);
  for (const { line, x } of cursors) {
    line.setAttribute("x1", x(angle));
    line.setAttribute("x2", x(angle));
  }
}

function seriesPath(values, x, y, breaks = []) {
  let path = "", pen = false, previous = -Infinity;
  data.theta_deg.forEach((theta, i) => {
    if (breaks.some(b => Math.abs(theta - b) < 1e-8)) { pen = false; previous = theta; return; }
    if (breaks.some(b => previous < b && b <= theta)) pen = false;
    path += `${pen ? "L" : "M"}${x(theta).toFixed(3)},${y(values[i]).toFixed(3)} `;
    pen = true;
    previous = theta;
  });
  return path;
}

function renderChart(descriptor) {
  const { key, symbol, unit } = descriptor;
  const card = document.createElement("section");
  card.className = `cam-motion-card motion-${key}`;
  const title = document.createElement("h3");
  title.textContent = `${symbol} · ${t(`camchart.${key}`)} · ${t(`camchart.unit.${key}`, unit)}`;
  const meta = document.createElement("p");
  meta.className = "cam-motion-metric";
  const values = data[key];
  let extent = Math.max(0.01, ...values.map(Math.abs), data.peaks?.[key] || 0);
  const limit = data.limits?.[key];
  if (Number.isFinite(limit) && limit <= extent * 2) extent = Math.max(extent, limit);
  const outside = Number.isFinite(limit) && limit > extent * 1.12;
  const metric = [];
  if (Number.isFinite(data.peaks?.[key])) metric.push(t("camchart.peak", null, { value: formatNumber(data.peaks[key], 3) }));
  if (Number.isFinite(limit)) metric.push(t("camchart.limit", null, { value: formatNumber(limit, 3) }) + (outside ? ` · ${t("camchart.outside")}` : ""));
  if (key === "lift") metric.push(t("camchart.lift_legend"));
  meta.textContent = metric.join(" · ") || t("camchart.samples");
  if (data.limit_exceeded?.[key]) meta.classList.add("motion-exceeded");
  const yMin = key === "lift" ? 0 : -extent * 1.12;
  const yMax = extent * 1.12;
  const start = data.theta_deg[0], end = data.theta_deg.at(-1);
  const x = v => LEFT + (v - start) / (end - start) * (W - LEFT - RIGHT);
  const y = v => TOP + (yMax - v) / (yMax - yMin) * (H - TOP - BOTTOM);
  const svg = svgElement("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", role: "img", "aria-label": title.textContent });
  svg.append(svgElement("title", {}, title.textContent));
  for (const window of data.windows) {
    if (!window.key.startsWith("ramp")) continue;
    svg.append(svgElement("rect", { x: x(window.from_deg), y: TOP, width: x(window.to_deg) - x(window.from_deg),
      height: H - TOP - BOTTOM, class: "motion-ramp" }));
  }
  for (const value of new Set([yMin, 0, yMax])) {
    svg.append(svgElement("line", { x1: LEFT, x2: W - RIGHT, y1: y(value), y2: y(value), class: "motion-grid-line" }));
    svg.append(svgElement("text", { x: LEFT - 6, y: y(value) + 5, "text-anchor": "end" }, formatNumber(value, 1)));
  }
  for (const value of [start, (start + end) / 2, end]) {
    svg.append(svgElement("text", { x: x(value), y: H - 10, "text-anchor": "middle" }, `${formatNumber(value, 1)}°`));
  }
  if (Number.isFinite(limit) && !outside) {
    for (const value of [-limit, limit]) svg.append(svgElement("line", {
      x1: LEFT, x2: W - RIGHT, y1: y(value), y2: y(value), class: "motion-limit" }));
  }
  svg.append(svgElement("path", { d: seriesPath(values, x, y, data.breaks_deg?.[key]), class: "motion-series" }));
  if (key === "lift") svg.append(svgElement("path", { d: seriesPath(data.valve_lift, x, y), class: "motion-valve-series" }));
  const line = svgElement("line", { x1: LEFT, x2: LEFT, y1: TOP, y2: H - BOTTOM, class: "motion-cursor" });
  svg.append(line);
  cursors.push({ line, x });
  svg.addEventListener("pointermove", event => {
    const bounds = svg.getBoundingClientRect();
    const sx = (event.clientX - bounds.left) / bounds.width * W;
    selectPoint(nearestIndex(start + (sx - LEFT) / (W - LEFT - RIGHT) * (end - start)));
  });
  card.append(title, meta, svg);
  return card;
}

function render() {
  grid.replaceChildren();
  cursors = [];
  if (!data) return;
  coordinateLabel.textContent = t(data.coordinate === "valve_command_with_lash" ? "camchart.rocker_coordinate" : "camchart.direct_coordinate");
  if (data.derivative_jumps) coordinateLabel.textContent += ` ${t("camchart.jumps")}`;
  for (const descriptor of descriptors) grid.append(renderChart(descriptor));
  slider.max = String(data.theta_deg.length - 1);
  renderState();
  selectPoint(selectedIndex);
}

profileButton.addEventListener("click", () => showView(false));
chartButton.addEventListener("click", () => showView(true));
slider.addEventListener("input", () => selectPoint(Number(slider.value)));
window.addEventListener("geomwright-preview", event => {
  data = validPayload(event.detail.motion_chart) ? event.detail.motion_chart : null;
  previewState = "ready";
  if (data) selectedIndex = nearestIndex(data.windows.find(w => w.key === "rise")?.to_deg ?? data.theta_deg[0]);
  render();
  showView(showCharts);
});
window.addEventListener("geomwright-preview-state", event => { previewState = event.detail.state; renderState(); });
window.addEventListener("geomwright-language", render);
window.addEventListener("geomwright-cam-motion-reset", () => { data = null; grid.replaceChildren(); showView(false); });
