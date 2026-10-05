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

function drawSilentSection(rect) {
  const drawing = data.drawing;
  const [minX, minY, maxX, maxY] = drawing.bounds;
  const verticalMargin = rect.height >= 360 ? 220 : 150;
  const scale = Math.max(0.01, Math.min((rect.width - 190) / (maxX - minX), (rect.height - verticalMargin) / (maxY - minY)));
  const left = 48 + Math.max(0, (rect.width - 190 - (maxX - minX) * scale) / 2);
  const top = Math.max(76, (rect.height - (maxY - minY) * scale) / 2 - 24);
  const point = ([x, y]) => [left + (x - minX) * scale, top + (y - minY) * scale];
  function path(points) {
    const result = new Path2D();
    if (!points?.length) return result;
    result.moveTo(...point(points[0]));
    for (const p of points.slice(1)) result.lineTo(...point(p));
    return result;
  }
  const hatch = new Path2D();
  for (const polygon of drawing.section_polygons) hatch.addPath(path(polygon));
  if (drawing.outline.length) {
     ctx.fillStyle = drawing.user_paths?.length ? "rgba(101,196,184,.05)" : "rgba(227,170,79,.05)";
    ctx.fill(path(drawing.outline));
  }
  ctx.save();
  ctx.clip(hatch);
   ctx.strokeStyle = drawing.user_paths?.length ? "rgba(101,196,184,.3)" : "rgba(227,170,79,.3)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let offset = -rect.height; offset < rect.width + rect.height; offset += 11) {
    ctx.moveTo(offset, rect.height); ctx.lineTo(offset + rect.height, 0);
  }
  ctx.stroke(); ctx.restore();
  ctx.setLineDash([]);
  ctx.strokeStyle = "#e3aa4f"; ctx.lineWidth = 2;
  for (const points of drawing.visible_paths) ctx.stroke(path(points));
  ctx.strokeStyle = "#65c4b8";
  for (const points of drawing.user_paths || []) ctx.stroke(path(points));
  ctx.lineWidth = 1.2; ctx.setLineDash([6, 4]);
  ctx.strokeStyle = "rgba(227,170,79,.72)";
  for (const points of drawing.reference_paths) ctx.stroke(path(points));
  ctx.strokeStyle = "#8eacc0";
  for (const points of drawing.break_paths) ctx.stroke(path(points));
  ctx.setLineDash([]);
  const bottom = point([maxX, maxY])[1];
  for (const dim of drawing.dimensions) {
    if (dim.symbol === "b₄" && data.row_count === 1) continue;
    const a = point(dim.start), b = point(dim.end);
    const text = `${dim.symbol} = ${formatNumber(dim.value, 2)}`;
    if (dim.orientation === "horizontal") {
      const below = dim.start[1] > minY || dim.level === 2;
       const y = below ? bottom + 32 + (dim.level >= 2 ? 24 * (dim.level - 1) : 0) : top - 28 - 28 * dim.level;
      dimension(a[0], b[0], below ? Math.max(a[1], b[1]) : top, y, text);
    } else {
       const onLeft = dim.start[0] < data.total_width_mm / 2;
      const x = onLeft ? left - 20 : point([maxX, minY])[0] + 22 + dim.level * 28;
      ctx.strokeStyle = "#8eacc0"; ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]); ctx.lineTo(x + 5, a[1]);
      ctx.moveTo(b[0], b[1]); ctx.lineTo(x + 5, b[1]);
      ctx.moveTo(x, a[1]); ctx.lineTo(x, b[1]);
      for (const [y, direction] of [[a[1], 1], [b[1], -1]]) {
        ctx.moveTo(x - 3, y + direction * 5); ctx.lineTo(x, y); ctx.lineTo(x + 3, y + direction * 5);
      }
      ctx.stroke();
      ctx.save(); ctx.translate(x + (onLeft ? -10 : 10), (a[1] + b[1]) / 2); ctx.rotate(-Math.PI / 2);
      label(text, 0, 0); ctx.restore();
    }
  }
  const annotations = drawing.annotations.filter(a => a.value_mm != null || a.value_deg != null)
    .map(a => `${a.symbol === "entrance" ? t("silent.entrance") : a.symbol} ${formatNumber(a.value_mm ?? a.value_deg, 2)}${a.value_deg != null ? "°" : ""}`);
  if (annotations.length && rect.height >= 340) label(annotations.join(" · "), left + (maxX - minX) * scale / 2, Math.min(rect.height - 20, bottom + 94));
  const asme = drawing.axial_source_system === "ramsey_rp_sc";
  const gbSource = drawing.axial_source_system === "gb_10855_2016";
  const titleKey = asme || gbSource ? "silent.axial_profile" : "silent.axial_section";
  for (const node of [panel.querySelector("h3"), rail.querySelector(".axial-rail-caption")]) {
    node.dataset.i18n = titleKey; node.textContent = t(titleKey);
  }
   const note = drawing.status === "user_defined_geometry" ? "silent.axial_completed"
     : drawing.status === "dimensioned_faces_with_schematic_body" ? "silent.axial_note"
     : drawing.status === "dimensioned_ribs_with_schematic_body" ? "silent.axial_gost_type2"
     : drawing.status === "guide_data_unavailable" ? (gbSource ? "silent.axial_gb_missing" : "silent.axial_data_missing")
       : gbSource ? (drawing.status === "source_rounded_edges_with_schematic_body" ? "silent.axial_gb_edges" : "silent.axial_gb_profile")
      : asme ? "silent.axial_partial" : "silent.axial_interpreted";
  document.querySelector("#axial-preview-note").textContent = t(note)
     + (asme && !["guide_data_unavailable", "user_defined_geometry"].includes(drawing.status) ? ` ${t("silent.axial_schematic_placement")}` : "");
  const gb = drawing.external_references?.find(r => r.axial_source_system === "gb_10855_2016");
  if (gb && !gbSource && drawing.status !== "user_defined_geometry") {
    const values = Object.entries(gb.values_mm).map(([symbol, value]) => {
      const tolerance = gb.tolerances_mm[symbol];
      return `${symbol} = ${formatNumber(value, 2)}${tolerance ? ` ± ${formatNumber(tolerance[1], 2)}` : ""}`;
    }).join("; ");
    document.querySelector("#axial-preview-note").textContent += ` ${t("silent.axial_gb_reference", "", { values })}`;
  }
  if (gbSource && gb?.source_pitch_mm === 4.762) {
    document.querySelector("#axial-preview-note").textContent += ` ${t("silent.axial_gb_small_pitch")}`;
  }
  const legend = panel.querySelector(".axial-legend");
   legend.dataset.i18n = drawing.user_paths?.length ? "silent.axial_user_legend" : "silent.axial_legend";
   legend.textContent = t(legend.dataset.i18n);
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
  const silent = data.family === "silent_chain_sprocket";
  document.querySelector("#axial-row-count").textContent = t(silent ? "silent.axial_ribs" : "chain.axial_rows", "", { count: data.row_count });
  if (silent && data.drawing) { drawSilentSection(rect); return; }
  for (const node of [panel.querySelector("h3"), rail.querySelector(".axial-rail-caption")]) {
    node.dataset.i18n = "chain.axial_title"; node.textContent = t("chain.axial_title");
  }
  panel.querySelector(".axial-legend").dataset.i18n = "chain.axial_legend";
  panel.querySelector(".axial-legend").textContent = t("chain.axial_legend");
  const axialNote = silent
    ? (data.axial_layout_status === "width_only" ? "silent.axial_width_only"
      : data.axial_layout_status === "user_width_only" ? "silent.axial_user_width"
        : data.axial_layout_status === "guide_data_unavailable" ? "silent.axial_data_missing" : "silent.axial_note")
    : (data.row_spacing_mm ? "chain.axial_note" : "chain.axial_missing");
  document.querySelector("#axial-preview-note").textContent = t(axialNote);
  const n = data.row_count;
  const b = data.tooth_width_mm;
  // Unknown pitch is for layout only: never show it as a measured dimension.
  const pitch = data.row_spacing_mm || b * 1.8;
  const total = data.total_width_mm || (n - 1) * pitch + b;
  const h3 = data.profile_height_mm || 0.8 * data.engagement_diameter_mm;
  const radius = data.end_round_radius_mm || (b < 0.5 * h3
    ? (h3 * h3 / (0.8 * b) + 0.2 * b) : 1.7 * h3);
  const sag = h3 * h3 / (radius + Math.sqrt(radius * radius - h3 * h3));
  const scale = Math.max(0.01, Math.min((rect.width - 64) / total, (rect.height - 144) / (h3 * 1.8)));
  const left = (rect.width - total * scale) / 2;
  const top = Math.max(54, (rect.height - h3 * 1.8 * scale) / 2 - 16);
  const shoulder = top + h3 * scale;
  const connector = shoulder + h3 * 0.25 * scale;
  const bottom = shoulder + h3 * 0.75 * scale;
  const x = (value) => left + value * scale;
  const shape = new Path2D();
  const firstRib = Math.max(0, (total - ((n - 1) * pitch + b)) / 2);
  shape.moveTo(left, bottom);
  for (let row = 0; row < n; row++) {
    const start = firstRib + row * pitch;
    if (row) shape.lineTo(x(start), connector);
    shape.lineTo(x(start), shoulder);
    for (let step = 1; step <= 16; step++) {
      const rise = h3 * step / 16;
      const dx = rise * rise / (radius + Math.sqrt(radius * radius - rise * rise));
      shape.lineTo(x(start + dx), shoulder - rise * scale);
    }
    const capLeft = start + sag;
    const capRight = start + b - sag;
    shape.lineTo(x(capLeft), top);
    let cursor = capLeft;
    const grooves = (data.guide_grooves_mm || [])
      .filter((groove) => Number.isFinite(groove.depth_mm) && groove.depth_mm > 0)
      .map((groove) => ({
        start: groove.center_mm - groove.width_mm / 2,
        end: groove.center_mm + groove.width_mm / 2,
        depth: groove.depth_mm,
      }))
      .filter((groove) => groove.start > cursor && groove.end < capRight)
      .sort((a, b) => a.start - b.start);
    for (const groove of grooves) {
      const grooveStart = Math.max(cursor, groove.start);
      if (grooveStart <= cursor || groove.end <= grooveStart || groove.end >= capRight) continue;
      const grooveBottom = top + groove.depth * scale;
      shape.lineTo(x(grooveStart), top);
      shape.lineTo(x(grooveStart), grooveBottom);
      shape.lineTo(x(groove.end), grooveBottom);
      shape.lineTo(x(groove.end), top);
      cursor = groove.end;
    }
    shape.lineTo(x(capRight), top);
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
  dimension(x(firstRib), x(firstRib + b), top - 5, top - 36, `${silent ? "b" : "b"} = ${formatNumber(b, 2)}`);
  if (n > 1 && data.row_spacing_mm) {
    dimension(x(firstRib + b / 2), x(firstRib + pitch + b / 2), bottom + 10, bottom + 30,
      `A = ${formatNumber(data.row_spacing_mm, 2)}`);
  }
  dimension(x(0), x(total), bottom + 10, bottom + 66,
    data.total_width_mm ? `B = ${formatNumber(data.total_width_mm, 2)}` : "B = ?");
  if (silent) {
    ctx.strokeStyle = "rgba(239,118,109,.85)";
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    for (const groove of data.guide_grooves_mm || []) {
      if (Number.isFinite(groove.depth_mm) && groove.depth_mm > 0) continue;
      const leftWall = x(groove.center_mm - groove.width_mm / 2);
      const rightWall = x(groove.center_mm + groove.width_mm / 2);
      ctx.moveTo(leftWall, shoulder); ctx.lineTo(leftWall, top - 6);
      ctx.moveTo(rightWall, shoulder); ctx.lineTo(rightWall, top - 6);
    }
    ctx.stroke(); ctx.setLineDash([]);
  }
}

window.addEventListener("geomwright-preview", (event) => {
  const result = event.detail;
  data = result?.family === "silent_chain_sprocket"
    ? { ...(result.secondary_view || {}), family: result.family }
    : result?.family === "chain_sprocket" && result.secondary_view ? result.secondary_view : null;
  if (result?.family !== "silent_chain_sprocket") {
    for (const node of [panel.querySelector("h3"), rail.querySelector(".axial-rail-caption")]) {
      node.dataset.i18n = "chain.axial_title"; node.textContent = t("chain.axial_title");
    }
    panel.querySelector(".axial-legend").dataset.i18n = "chain.axial_legend";
    panel.querySelector(".axial-legend").textContent = t("chain.axial_legend");
  }
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
