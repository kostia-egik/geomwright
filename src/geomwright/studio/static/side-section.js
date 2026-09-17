import { t, formatNumber } from "./i18n.js";

const panel = document.querySelector("#axial-preview");
const canvas = document.querySelector("#side-section-canvas");
const ctx = canvas.getContext("2d");
const wrap = panel.closest(".canvas-wrap");
const toggle = document.querySelector("#axial-preview-toggle");
const rail = document.querySelector("#axial-preview-rail");
const stacked = window.matchMedia("(max-width: 1200px)");
let data = null;
let manuallyHidden = false;

function updateLayout() {
  rail.hidden = !data;
  panel.hidden = !data || manuallyHidden;
  wrap.classList.toggle("has-side-section", Boolean(data));
  wrap.classList.toggle("side-section-collapsed", Boolean(data) && manuallyHidden);
  toggle.setAttribute("aria-expanded", String(!panel.hidden));
  toggle.title = t(manuallyHidden ? "chain.axial_show" : "chain.axial_hide");
  toggle.setAttribute("aria-label", toggle.title);
  toggle.firstElementChild.textContent = stacked.matches
    ? (manuallyHidden ? "▴" : "▾") : (manuallyHidden ? "‹" : "›");
  requestAnimationFrame(draw);
}

function label(text, x, y) {
  ctx.font = "600 12px Inter, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const width = ctx.measureText(text).width + 10;
  ctx.fillStyle = "#10151c";
  ctx.fillRect(x - width / 2, y - 10, width, 20);
  ctx.fillStyle = "#c9d6e2";
  ctx.fillText(text, x, y);
}

function dimension(x1, x2, anchor, y, text) {
  ctx.strokeStyle = "#8eacc0";
  ctx.lineWidth = 1;
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(x1, anchor); ctx.lineTo(x1, y + 5);
  ctx.moveTo(x2, anchor); ctx.lineTo(x2, y + 5);
  ctx.moveTo(x1, y); ctx.lineTo(x2, y);
  for (const [x, direction] of [[x1, 1], [x2, -1]]) {
    ctx.moveTo(x + direction * 5, y - 3); ctx.lineTo(x, y);
    ctx.lineTo(x + direction * 5, y + 3);
  }
  ctx.stroke();
  label(text, (x1 + x2) / 2, y - 12);
}

function draw() {
  if (panel.hidden || !data) return;
  const rect = canvas.getBoundingClientRect();
  if (rect.width < 1 || rect.height < 1) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  document.querySelector("#axial-row-count").textContent = t("chain.axial_rows", "", { count: data.row_count });
  document.querySelector("#axial-preview-note").textContent = t(data.row_spacing_mm ? "chain.axial_note" : "chain.axial_missing");
  const n = data.row_count;
  const b = data.tooth_width_mm;
  // Unknown pitch is for layout only: never show it as a measured dimension.
  const pitch = data.row_spacing_mm || b * 1.8;
  const total = (n - 1) * pitch + b;
  const h3 = 0.8 * data.engagement_diameter_mm;
  const radius = b < 0.5 * data.engagement_diameter_mm
    ? (h3 * h3 / (0.8 * b) + 0.2 * b) : 1.7 * data.engagement_diameter_mm;
  const sag = h3 * h3 / (radius + Math.sqrt(radius * radius - h3 * h3));
  const scale = Math.max(0.01, Math.min((rect.width - 64) / total, (rect.height - 144) / (h3 * 1.8)));
  const left = (rect.width - total * scale) / 2;
  const top = Math.max(54, (rect.height - h3 * 1.8 * scale) / 2 - 16);
  const shoulder = top + h3 * scale;
  const connector = shoulder + h3 * 0.25 * scale;
  const bottom = shoulder + h3 * 0.75 * scale;
  const x = (value) => left + value * scale;
  const shape = new Path2D();
  shape.moveTo(left, bottom);
  for (let row = 0; row < n; row++) {
    const start = row * pitch;
    if (row) shape.lineTo(x(start), connector);
    shape.lineTo(x(start), shoulder);
    for (let step = 1; step <= 16; step++) {
      const rise = h3 * step / 16;
      const dx = rise * rise / (radius + Math.sqrt(radius * radius - rise * rise));
      shape.lineTo(x(start + dx), shoulder - rise * scale);
    }
    shape.lineTo(x(start + b - sag), top);
    for (let step = 15; step >= 0; step--) {
      const rise = h3 * step / 16;
      const dx = rise * rise / (radius + Math.sqrt(radius * radius - rise * rise));
      shape.lineTo(x(start + b - dx), shoulder - rise * scale);
    }
    if (row < n - 1) shape.lineTo(x(start + b), connector);
  }
  shape.lineTo(x(total), bottom);
  shape.closePath();
  ctx.fillStyle = "rgba(227,170,79,.09)";
  ctx.fill(shape);
  ctx.save();
  ctx.clip(shape);
  ctx.strokeStyle = "rgba(227,170,79,.22)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let offset = -rect.height; offset < rect.width + rect.height; offset += 12) {
    ctx.moveTo(offset, rect.height); ctx.lineTo(offset + rect.height, 0);
  }
  ctx.stroke(); ctx.restore();
  ctx.strokeStyle = "#e3aa4f"; ctx.lineWidth = 2;
  ctx.stroke(shape);
  ctx.strokeStyle = "rgba(97,192,177,.75)";
  ctx.setLineDash([9, 4, 2, 4]);
  for (let row = 0; row < n; row++) {
    const center = x(row * pitch + b / 2);
    ctx.beginPath(); ctx.moveTo(center, top - 20); ctx.lineTo(center, bottom + 12); ctx.stroke();
    label(String(row + 1), center, top - 17);
  }
  ctx.setLineDash([]);
  dimension(x(0), x(b), top - 5, top - 36, `b = ${formatNumber(b, 2)}`);
  dimension(x(b / 2), x(pitch + b / 2), bottom + 10, bottom + 30,
    data.row_spacing_mm ? `A = ${formatNumber(data.row_spacing_mm, 2)}` : "A = ?");
  dimension(x(0), x(total), bottom + 10, bottom + 66,
    data.total_width_mm ? `B = ${formatNumber(data.total_width_mm, 2)}` : "B = ?");
}

window.addEventListener("geomwright-preview", (event) => {
  data = event.detail?.family === "chain_sprocket" ? event.detail.secondary_view : null;
  updateLayout();
  panel.dataset.state = "ready";
  requestAnimationFrame(draw);
});
toggle.addEventListener("click", () => {
  manuallyHidden = !manuallyHidden;
  updateLayout();
});
window.addEventListener("geomwright-preview-state", (event) => {
  panel.dataset.state = event.detail?.state || "ready";
});
window.addEventListener("geomwright-language", updateLayout);
stacked.addEventListener("change", updateLayout);
new ResizeObserver(draw).observe(canvas);
