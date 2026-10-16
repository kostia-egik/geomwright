import { t, formatNumber } from "./i18n.js";

function label(ctx, text, x, y, color = "#c9d6e2") {
  ctx.font = "600 11px Inter, system-ui, sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  const width = ctx.measureText(text).width + 8;
  ctx.fillStyle = "#10151c"; ctx.fillRect(x - width / 2, y - 9, width, 18);
  ctx.fillStyle = color; ctx.fillText(text, x, y);
}

function frame(rect, points, margin = {left: 55, right: 72, top: 38, bottom: 40}) {
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const w = Math.max(40, rect.width - margin.left - margin.right);
  const h = Math.max(40, rect.height - margin.top - margin.bottom);
  const scale = Math.min(w / Math.max(1e-6, maxX - minX), h / Math.max(1e-6, maxY - minY));
  return p => [margin.left + w / 2 + (p[0] - (minX + maxX) / 2) * scale,
    margin.top + h / 2 - (p[1] - (minY + maxY) / 2) * scale];
}

function path(ctx, points, project, {closed = false, fill = null, color = "#e3aa4f", dash = [], width = 1.5} = {}) {
  const shape = new Path2D();
  if (!points.length) return shape;
  shape.moveTo(...project(points[0]));
  for (const p of points.slice(1)) shape.lineTo(...project(p));
  if (closed) shape.closePath();
  if (fill) { ctx.fillStyle = fill; ctx.fill(shape); }
  if (color !== false) {
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash);
    ctx.stroke(shape); ctx.setLineDash([]);
  }
  return shape;
}

function dimension(ctx, project, item) {
  const a = project(item.start), b = project(item.end);
  const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
  if (length < 1) return;
  const ux = (b[0] - a[0]) / length, uy = (b[1] - a[1]) / length;
  const nx = uy, ny = -ux, offset = item.offset ?? 25;
  ctx.strokeStyle = "#8eacc0"; ctx.lineWidth = 1; ctx.setLineDash([]);
  ctx.beginPath();
  for (const [p, sign, anchor] of [[a, 1, item.anchor_start], [b, -1, item.anchor_end]]) {
    const x = p[0] + nx * offset, y = p[1] + ny * offset;
    ctx.moveTo(...(anchor ? project(anchor) : p));
    ctx.lineTo(x + Math.sign(offset) * nx * 4, y + Math.sign(offset) * ny * 4);
    ctx.moveTo(x + sign * ux * 5 + nx * 2.5, y + sign * uy * 5 + ny * 2.5);
    ctx.lineTo(x, y); ctx.lineTo(x + sign * ux * 5 - nx * 2.5, y + sign * uy * 5 - ny * 2.5);
  }
  ctx.moveTo(a[0] + nx * offset, a[1] + ny * offset);
  ctx.lineTo(b[0] + nx * offset, b[1] + ny * offset); ctx.stroke();
  ctx.save();
  ctx.translate((a[0] + b[0]) / 2 + nx * (offset + Math.sign(offset) * 11),
    (a[1] + b[1]) / 2 + ny * (offset + Math.sign(offset) * 11));
  let angle = Math.atan2(uy, ux);
  if (angle > Math.PI / 2 || angle < -Math.PI / 2) angle += Math.PI;
  ctx.rotate(angle);
  label(ctx, `${item.symbol} = ${formatNumber(item.value, 2)}`, 0, 0);
  ctx.restore();
}

export function drawBevelAxial(ctx, data, rect) {
  const outline = data.outline || [];
  if (outline.length < 3) return;
  // Show the radial half-section and the cone apex, not a stretched silhouette.
  const project = frame(rect, [...outline, [0, 0]], {left: 60, right: 55, top: 42, bottom: 35});
  const shape = path(ctx, outline, project, {closed: true, fill: "rgba(227,170,79,.04)", width: 1.8});
  ctx.save(); ctx.clip(shape); ctx.strokeStyle = "rgba(227,170,79,.22)"; ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = -rect.height; x < rect.width; x += 10) {
    ctx.moveTo(x, rect.height); ctx.lineTo(x + rect.height, 0);
  }
  ctx.stroke(); ctx.restore();
  const lines = data.tooth_lines || {};
  for (const key of ["pitch_line", "root_line", "tip_cone"]) {
    const line = lines[key] || [];
    path(ctx, line, project, {color: key === "pitch_line" ? "#61c0b1" : "#8eacc0", dash: [7, 4, 2, 4], width: 1});
    if (line.length >= 2) path(ctx, [line.at(-1), [0, 0]], project,
      {color: "rgba(142,172,192,.4)", dash: [4, 4], width: 1});
  }
  path(ctx, [[data.back_face_x_mm * 1.07, 0], [3, 0]], project,
    {color: "#8eacc0", dash: [9, 3, 2, 3], width: 1});
  const apex = project([0, 0]);
  label(ctx, "O", apex[0] + 10, apex[1] - 9);
  dimension(ctx, project, {symbol: "B", start: [data.back_face_x_mm, data.tip_corner_radius_mm],
    end: [Math.max(data.front_face_x_mm, data.inner_tip_corner_x_mm), data.tip_corner_radius_mm],
    anchor_start: [data.back_face_x_mm, data.back_face_radius_mm],
    anchor_end: data.front_face_x_mm >= data.inner_tip_corner_x_mm
      ? [data.front_face_x_mm, data.front_face_radius_mm]
      : [data.inner_tip_corner_x_mm, data.inner_tip_corner_radius_mm],
    value: data.blank_width_mm, offset: 24});
  if (lines.pitch_line?.length >= 2) {
    dimension(ctx, project, {symbol: "b", start: lines.pitch_line[0], end: lines.pitch_line[1],
      value: data.face_width_mm, offset: 26});
    dimension(ctx, project, {symbol: "Rₑ", start: [0, 0], end: lines.pitch_line[0],
      value: data.outer_cone_distance_mm, offset: 18});
    const p = project(lines.pitch_line[0]), end = project(lines.pitch_line[1]);
    const vx = end[0] - p[0], vy = end[1] - p[1], len = Math.hypot(vx, vy);
    const ux = vx / len, uy = vy / len;
    const x = p[0] - ux * 32, y = p[1] - uy * 32;
    ctx.strokeStyle = "#61c0b1"; ctx.beginPath();
    ctx.moveTo(x, y); ctx.lineTo(...p);
    ctx.moveTo(p[0] - ux * 6 + uy * 3, p[1] - uy * 6 - ux * 3);
    ctx.lineTo(...p); ctx.lineTo(p[0] - ux * 6 - uy * 3, p[1] - uy * 6 + ux * 3); ctx.stroke();
    label(ctx, "D", x - 8, y + (data.pitch_cone_angle_deg > 65 ? 8 : -8), "#61c0b1");
  }
  label(ctx, `δ = ${formatNumber(data.pitch_cone_angle_deg, 2)}° · δₐ = ${formatNumber(data.face_cone_angle_deg, 2)}° · δ_f = ${formatNumber(data.root_cone_angle_deg, 2)}°`,
    rect.width / 2, rect.height - 12);
}

export function drawBevelTooth(ctx, data, rect) {
  if (!data?.outline?.length) return;
  const project = frame(rect, data.outline, {left: 42, right: 42, top: 54, bottom: 32});
  const shape = path(ctx, data.outline, project, {closed: true, fill: "rgba(227,170,79,.05)",
    color: data.profile ? false : "#e3aa4f", width: 1.8});
  if (data.profile) path(ctx, data.profile, project, {width: 1.8});
  if (data.break_path) path(ctx, data.break_path, project, {color: "rgba(227,170,79,.82)", width: 1.15});
  ctx.save(); ctx.clip(shape);
  for (const ref of data.references || []) {
    path(ctx, ref.points, project, {color: ref.key === "pitch" ? "#61c0b1" : "rgba(142,172,192,.6)",
      dash: ref.key === "pitch" ? [7, 3, 2, 3] : [3, 4], width: 1});
  }
  ctx.restore();
  for (const item of data.dimensions || []) dimension(ctx, project, item);
  label(ctx, t("gear.bevel_tooth_basis"), rect.width / 2, rect.height - 12);
}
