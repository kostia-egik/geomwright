import { formatNumber, splitReadableSubscripts } from "./i18n.js";

const canvas = document.querySelector("#profile-canvas");
const emptyState = document.querySelector("#canvas-empty");
const context = canvas.getContext("2d");
const state = {
  data: null,
  zoom: 1,
  panX: 0,
  panY: 0,
  dragging: false,
  pointerX: 0,
  pointerY: 0,
};

function resize() {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * ratio));
  canvas.height = Math.max(1, Math.round(rect.height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  draw();
}

function viewport() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const bounds = state.data?.bounds || { x_min: -1, x_max: 1, y_min: -1, y_max: 1 };
  const dx = Math.max(bounds.x_max - bounds.x_min, 1e-6);
  const dy = Math.max(bounds.y_max - bounds.y_min, 1e-6);
  const compact = width < 620;
  const padding = {
    left: compact ? 44 : 76,
    right: compact ? 132 : 190,
    top: compact ? 82 : 104,
    bottom: compact ? 62 : 78,
  };
  const drawableWidth = Math.max(80, width - padding.left - padding.right);
  const drawableHeight = Math.max(80, height - padding.top - padding.bottom);
  const baseScale = Math.min(drawableWidth / dx, drawableHeight / dy);
  const scale = baseScale * state.zoom;
  const centerX = (bounds.x_min + bounds.x_max) / 2;
  const centerY = (bounds.y_min + bounds.y_max) / 2;
  return {
    width,
    height,
    scale,
    padding,
    point: ([x, y]) => [
      padding.left + drawableWidth / 2 + (x - centerX) * scale + state.panX,
      padding.top + drawableHeight / 2 - (y - centerY) * scale + state.panY,
    ],
  };
}

function drawBackground(view) {
  context.clearRect(0, 0, view.width, view.height);
  context.fillStyle = "#10151c";
  context.fillRect(0, 0, view.width, view.height);

  const spacing = 32;
  context.strokeStyle = "rgba(255,255,255,0.035)";
  context.lineWidth = 1;
  context.beginPath();
  for (let x = (state.panX % spacing); x < view.width; x += spacing) {
    context.moveTo(x, 0);
    context.lineTo(x, view.height);
  }
  for (let y = (state.panY % spacing); y < view.height; y += spacing) {
    context.moveTo(0, y);
    context.lineTo(view.width, y);
  }
  context.stroke();
}

function drawPath(
  points,
  view,
  { fill = null, stroke = "#e3aa4f", dashed = false, dash = null, lineWidth = 1.8 } = {},
) {
  if (!points?.length) return;
  context.save();
  context.beginPath();
  const [firstX, firstY] = view.point(points[0]);
  context.moveTo(firstX, firstY);
  for (const point of points.slice(1)) {
    const [x, y] = view.point(point);
    context.lineTo(x, y);
  }
  if (fill) {
    context.closePath();
    context.fillStyle = fill;
    context.fill();
  }
  context.setLineDash(dash || (dashed ? [7, 6] : []));
  context.strokeStyle = stroke;
  context.lineWidth = lineWidth;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.stroke();
  context.restore();
}

function drawAxes(view) {
  const origin = view.point([0, 0]);
  context.save();
  context.strokeStyle = "rgba(126, 163, 196, 0.35)";
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(0, origin[1]);
  context.lineTo(view.width, origin[1]);
  context.moveTo(origin[0], 0);
  context.lineTo(origin[0], view.height);
  context.stroke();
  context.restore();
}

function drawPhantomBodies(view) {
  for (const body of state.data?.phantom_bodies || []) {
    if (!body.outline?.length) continue;
    const points = body.outline.map(view.point);
    const [, bottomLeft, bottomRight] = points;
    const surface = (body.surface?.length ? body.surface : [body.outline[0], body.outline[3]]).map(view.point);
    context.save();
    context.fillStyle = "rgba(132, 174, 204, 0.055)";
    context.strokeStyle = "rgba(157, 177, 191, 0.62)";
    context.lineWidth = 1.2;
    context.beginPath();
    context.moveTo(...surface[0]);
    for (const point of surface.slice(1)) context.lineTo(...point);
    context.lineTo(...bottomRight);
    context.lineTo(...bottomLeft);
    context.closePath();
    context.fill();
    context.beginPath();
    context.moveTo(...surface[0]);
    context.lineTo(...bottomLeft);
    context.moveTo(...surface[surface.length - 1]);
    context.lineTo(...bottomRight);
    context.stroke();

    context.setLineDash([]);
    context.beginPath();
    const width = bottomRight[0] - bottomLeft[0];
    const waves = Math.max(6, Math.round(width / 34));
    const steps = waves * 8;
    for (let index = 0; index <= steps; index += 1) {
      const progress = index / steps;
      const x = bottomLeft[0] + width * progress;
      const y = bottomLeft[1] + Math.sin(progress * waves * Math.PI * 2) * 3.5;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    }
    context.stroke();
    context.restore();
  }
}

function drawReferencePaths(view) {
  for (const reference of state.data?.reference_paths || []) {
    drawPath(reference.points, view, {
      stroke: "rgba(97, 192, 177, 0.68)",
      dash: [11, 4, 2, 4],
      lineWidth: 1.15,
    });
  }
}

function drawDimensionLabel(text, x, y, angle = 0) {
  context.save();
  context.translate(x, y);
  context.rotate(angle);
  const normalFont = "650 13px Inter, ui-sans-serif, system-ui, sans-serif";
  const subscriptFont = "750 12px Inter, ui-sans-serif, system-ui, sans-serif";
  const runs = splitReadableSubscripts(text).map((run) => {
    context.font = run.subscript ? subscriptFont : normalFont;
    return { ...run, width: context.measureText(run.text).width };
  });
  const textWidth = runs.reduce((sum, run) => sum + run.width, 0);
  const width = textWidth + 14;
  context.fillStyle = "rgba(16, 21, 28, 0.92)";
  context.fillRect(-width / 2, -11, width, 22);
  context.fillStyle = "rgba(185, 205, 219, 0.9)";
  context.textAlign = "left";
  context.textBaseline = "alphabetic";
  let cursor = -textWidth / 2;
  for (const run of runs) {
    context.font = run.subscript ? subscriptFont : normalFont;
    context.fillText(run.text, cursor, run.subscript ? 6.5 : 4);
    cursor += run.width;
  }
  context.restore();
}

function readableDimensionAngle(angle) {
  let normalized = angle % (Math.PI * 2);
  if (normalized > Math.PI) normalized -= Math.PI * 2;
  if (normalized <= -Math.PI) normalized += Math.PI * 2;
  if (normalized > Math.PI / 2) normalized -= Math.PI;
  if (normalized < -Math.PI / 2) normalized += Math.PI;
  return normalized;
}

function drawHorizontalArrow(x, y, direction) {
  context.moveTo(x, y);
  context.lineTo(x + direction * 6, y - 3);
  context.moveTo(x, y);
  context.lineTo(x + direction * 6, y + 3);
}

function drawVerticalArrow(x, y, direction) {
  context.moveTo(x, y);
  context.lineTo(x - 3, y + direction * 6);
  context.moveTo(x, y);
  context.lineTo(x + 3, y + direction * 6);
}

function drawArrowHead(x, y, directionAngle, size = 7) {
  const wing = 0.48;
  context.moveTo(x, y);
  context.lineTo(
    x - Math.cos(directionAngle - wing) * size,
    y - Math.sin(directionAngle - wing) * size,
  );
  context.moveTo(x, y);
  context.lineTo(
    x - Math.cos(directionAngle + wing) * size,
    y - Math.sin(directionAngle + wing) * size,
  );
}

function dimensionText(item) {
  return `${item.symbol} = ${formatNumber(item.value, 2)}${item.unit ? ` ${item.unit}` : ""}`;
}

function drawHorizontalDimension(item, view) {
  const start = view.point(item.start);
  const end = view.point(item.end);
  const leftX = Math.min(start[0], end[0]);
  const rightX = Math.max(start[0], end[0]);
  const level = Number(item.level || 0);
  const offset = 19 + level * 22;
  const lineY = item.placement === "bottom"
    ? Math.max(start[1], end[1]) + offset
    : Math.min(start[1], end[1]) - offset;

  context.beginPath();
  context.moveTo(start[0], start[1]);
  context.lineTo(start[0], lineY);
  context.moveTo(end[0], end[1]);
  context.lineTo(end[0], lineY);
  context.moveTo(leftX, lineY);
  context.lineTo(rightX, lineY);
  drawHorizontalArrow(leftX, lineY, 1);
  drawHorizontalArrow(rightX, lineY, -1);
  context.stroke();
  drawDimensionLabel(dimensionText(item), (leftX + rightX) / 2, lineY);
}

function drawVerticalDimension(item, view) {
  const start = view.point(item.start);
  const end = view.point(item.end);
  const topY = Math.min(start[1], end[1]);
  const bottomY = Math.max(start[1], end[1]);
  const level = Number(item.level || 0);
  const offset = 22 + level * 20;
  const lineX = item.placement === "right"
    ? Math.max(start[0], end[0]) + offset
    : Math.min(start[0], end[0]) - offset;

  context.beginPath();
  context.moveTo(start[0], start[1]);
  context.lineTo(lineX, start[1]);
  context.moveTo(end[0], end[1]);
  context.lineTo(lineX, end[1]);
  context.moveTo(lineX, topY);
  context.lineTo(lineX, bottomY);
  drawVerticalArrow(lineX, topY, 1);
  drawVerticalArrow(lineX, bottomY, -1);
  context.stroke();
  drawDimensionLabel(
    dimensionText(item),
    lineX + Number(item.label_dx || 0),
    (topY + bottomY) / 2 + Number(item.label_dy || 0),
    item.label_horizontal ? 0 : -Math.PI / 2,
  );
}

function drawDiameterDimension(item, view) {
  const anchor = view.point(item.start);
  const level = Number(item.level || 0);
  const side = item.placement === "left" ? -1 : 1;
  const edgeWorldX = side < 0 ? state.data.bounds.x_min : state.data.bounds.x_max;
  const edge = view.point([edgeWorldX, item.start[1]]);
  const targetWorldX = Number.isFinite(item.target_x) ? item.target_x : edgeWorldX;
  const target = view.point([targetWorldX, item.start[1]]);
  const breakPoint = view.point([edgeWorldX, item.break_radius || state.data.bounds.y_min]);
  const offset = 28 + level * 31;
  const lineX = edge[0] + side * offset;
  const extensionEndX = lineX + side * 8;
  const topY = anchor[1];
  const bottomY = breakPoint[1];

  context.beginPath();
  context.moveTo(target[0], topY);
  context.lineTo(extensionEndX, topY);
  context.moveTo(lineX, topY);
  context.lineTo(lineX, bottomY);
  drawVerticalArrow(lineX, topY, 1);
  context.stroke();
  const labelOffset = side * 12;
  drawDimensionLabel(dimensionText(item), lineX + labelOffset, (topY + bottomY) / 2, -Math.PI / 2);
}

function drawAngularDimension(item, view) {
  if (!Array.isArray(item.vertex) || !Array.isArray(item.left_ray) || !Array.isArray(item.right_ray)) return;
  const vertex = view.point(item.vertex);
  const left = view.point(item.left_ray);
  const right = view.point(item.right_ray);
  const leftAngle = Math.atan2(left[1] - vertex[1], left[0] - vertex[0]);
  const rightAngle = Math.atan2(right[1] - vertex[1], right[0] - vertex[0]);
  let sweep = rightAngle - leftAngle;
  while (sweep <= 0) sweep += Math.PI * 2;
  if (sweep > Math.PI) {
    sweep -= Math.PI * 2;
  }
  const endAngle = leftAngle + sweep;
  const rayLength = Math.min(
    Math.hypot(left[0] - vertex[0], left[1] - vertex[1]),
    Math.hypot(right[0] - vertex[0], right[1] - vertex[1]),
  );
  const radius = Math.max(24, Math.min(46, rayLength * 0.42));
  const extensionRadius = radius + 12;
  const leftRayLength = Math.hypot(left[0] - vertex[0], left[1] - vertex[1]);
  const rightRayLength = Math.hypot(right[0] - vertex[0], right[1] - vertex[1]);
  const leftArc = [vertex[0] + Math.cos(leftAngle) * radius, vertex[1] + Math.sin(leftAngle) * radius];
  const rightArc = [vertex[0] + Math.cos(endAngle) * radius, vertex[1] + Math.sin(endAngle) * radius];

  context.beginPath();
  context.moveTo(vertex[0], vertex[1]);
  context.lineTo(
    vertex[0] + Math.cos(leftAngle) * Math.max(extensionRadius, leftRayLength),
    vertex[1] + Math.sin(leftAngle) * Math.max(extensionRadius, leftRayLength),
  );
  context.stroke();

  context.beginPath();
  context.moveTo(vertex[0], vertex[1]);
  context.lineTo(
    vertex[0] + Math.cos(endAngle) * Math.max(extensionRadius, rightRayLength),
    vertex[1] + Math.sin(endAngle) * Math.max(extensionRadius, rightRayLength),
  );
  context.stroke();

  context.beginPath();
  context.moveTo(leftArc[0], leftArc[1]);
  context.arc(vertex[0], vertex[1], radius, leftAngle, endAngle, sweep < 0);
  context.stroke();

  const sweepSign = Math.sign(sweep) || 1;
  context.beginPath();
  drawArrowHead(leftArc[0], leftArc[1], leftAngle + sweepSign * Math.PI / 2, 6);
  drawArrowHead(rightArc[0], rightArc[1], endAngle - sweepSign * Math.PI / 2, 6);
  context.stroke();

  const middleAngle = leftAngle + sweep / 2;
  drawDimensionLabel(
    dimensionText(item),
    vertex[0] + Math.cos(middleAngle) * (radius + 10),
    vertex[1] + Math.sin(middleAngle) * (radius + 10),
  );
}

function drawRadiusDimension(item, view) {
  if (!Array.isArray(item.center) || !Array.isArray(item.anchor)) return;
  const center = view.point(item.center);
  const anchor = view.point(item.anchor);
  const direction = Math.atan2(anchor[1] - center[1], anchor[0] - center[0]);
  const extensionLength = Number.isFinite(item.extension_length) ? item.extension_length : 44;
  const lineEnd = [
    anchor[0] + Math.cos(direction) * extensionLength,
    anchor[1] + Math.sin(direction) * extensionLength,
  ];
  const label = [
    anchor[0] + Math.cos(direction) * (extensionLength + 20) + Number(item.label_dx || 0),
    anchor[1] + Math.sin(direction) * (extensionLength + 20) + Number(item.label_dy || 0),
  ];

  context.beginPath();
  context.moveTo(center[0], center[1]);
  context.lineTo(anchor[0], anchor[1]);
  context.lineTo(lineEnd[0], lineEnd[1]);
  context.stroke();

  context.beginPath();
  drawArrowHead(anchor[0], anchor[1], direction + Math.PI, 7);
  context.stroke();
  drawDimensionLabel(
    dimensionText(item),
    label[0],
    label[1],
    item.label_horizontal ? 0 : readableDimensionAngle(direction),
  );
}

function drawRadialDimension(item, view) {
  const start = view.point(item.start);
  const end = view.point(item.end);
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const length = Math.hypot(dx, dy);
  if (length <= 1e-6) return;
  const ux = dx / length;
  const uy = dy / length;
  const nx = -uy;
  const ny = ux;
  const middle = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
  context.beginPath();
  context.moveTo(start[0], start[1]);
  context.lineTo(end[0], end[1]);
  drawArrowHead(end[0], end[1], Math.atan2(dy, dx), 7);
  context.stroke();
  const labelNormal = Number(item.label_normal || 0);
  const labelTangent = Number(item.label_tangent || 0);
  drawDimensionLabel(
    dimensionText(item),
    middle[0] + nx * labelNormal + ux * labelTangent,
    middle[1] + ny * labelNormal + uy * labelTangent,
  );
}

function drawDimensions(view) {
  context.save();
  context.strokeStyle = "rgba(142, 174, 196, 0.62)";
  context.lineWidth = 1;
  context.setLineDash([]);
  for (const item of state.data?.dimensions || []) {
    if (!Array.isArray(item.start) || !Array.isArray(item.end)) continue;
    if (item.orientation === "horizontal") drawHorizontalDimension(item, view);
    else if (item.orientation === "vertical") drawVerticalDimension(item, view);
    else if (item.orientation === "diameter") drawDiameterDimension(item, view);
    else if (item.orientation === "angular") drawAngularDimension(item, view);
    else if (item.orientation === "radius") drawRadiusDimension(item, view);
    else if (item.orientation === "radial") drawRadialDimension(item, view);
  }
  context.restore();
}

function draw() {
  const view = viewport();
  drawBackground(view);
  if (!state.data) return;
  drawAxes(view);
  drawPhantomBodies(view);
  drawReferencePaths(view);
  for (const guide of state.data.guide_paths || []) {
    drawPath(guide, view, { stroke: "rgba(157, 177, 191, 0.72)", lineWidth: 1.2 });
  }
  const palette = [
    "#e3aa4f",
    "#61c0b1",
  ];
  (state.data.feature_paths || []).forEach((path, index) => {
    const stroke = palette[index % palette.length];
    drawPath(path, view, { stroke, lineWidth: 2.5 });
  });
  drawDimensions(view);
}

function resetView() {
  state.zoom = 1;
  state.panX = 0;
  state.panY = 0;
  draw();
}

window.addEventListener("geomwright-preview", (event) => {
  state.data = event.detail;
  emptyState.hidden = Boolean(state.data?.closed_points?.length);
  canvas.dataset.state = "ready";
  resetView();
});
window.addEventListener("geomwright-preview-state", (event) => {
  canvas.dataset.state = event.detail?.state || "ready";
});
window.addEventListener("geomwright-language", draw);

canvas.addEventListener("wheel", (event) => {
  event.preventDefault();
  state.zoom = Math.min(12, Math.max(0.35, state.zoom * (event.deltaY < 0 ? 1.12 : 0.89)));
  draw();
}, { passive: false });

canvas.addEventListener("pointerdown", (event) => {
  state.dragging = true;
  state.pointerX = event.clientX;
  state.pointerY = event.clientY;
  canvas.setPointerCapture(event.pointerId);
});

canvas.addEventListener("pointermove", (event) => {
  if (!state.dragging) return;
  state.panX += event.clientX - state.pointerX;
  state.panY += event.clientY - state.pointerY;
  state.pointerX = event.clientX;
  state.pointerY = event.clientY;
  draw();
});

canvas.addEventListener("pointerup", (event) => {
  state.dragging = false;
  canvas.releasePointerCapture(event.pointerId);
});
canvas.addEventListener("pointercancel", () => { state.dragging = false; });
canvas.addEventListener("dblclick", resetView);

new ResizeObserver(resize).observe(canvas);
resize();
