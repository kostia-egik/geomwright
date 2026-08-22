import {
  applyStaticTranslations,
  formatNumber,
  getLocale,
  localizeWarning,
  setLocale,
  splitReadableSubscripts,
  t,
} from "./i18n.js";

const moduleSelect = document.querySelector("#module-select");
const moduleDescription = document.querySelector("#module-description");
const form = document.querySelector("#preview-form");
const fieldsContainer = document.querySelector("#dynamic-fields");
const resetButton = document.querySelector("#reset-button");
const liveIndicator = document.querySelector("#live-indicator");
const summary = document.querySelector("#summary");
const standardBadge = document.querySelector("#standard-badge");
const warningsSection = document.querySelector("#warnings-section");
const warningsList = document.querySelector("#warnings");
const statusDot = document.querySelector("#status-dot");
const statusText = document.querySelector("#status-text");
const languageButtons = [...document.querySelectorAll("[data-language]")];
const cadCreateButton = document.querySelector("#cad-create-button");
const cadCancelButton = document.querySelector("#cad-cancel-button");
const cadTitle = document.querySelector("#cad-title");
const cadDescription = document.querySelector("#cad-description");
const cadResult = document.querySelector("#cad-result");
const cadProgress = document.querySelector("#cad-progress");
const cadProgressBar = document.querySelector("#cad-progress-bar");
const cadProgressFill = document.querySelector("#cad-progress-fill");
const cadProgressPercent = document.querySelector("#cad-progress-percent");
const cadProgressStage = document.querySelector("#cad-progress-stage");
const cadProgressTime = document.querySelector("#cad-progress-time");
const workspaceShell = document.querySelector("#workspace-shell");
const editorShell = document.querySelector("#editor-shell");
const workspaceRefreshButton = document.querySelector("#workspace-refresh");
const workspaceOpenButton = document.querySelector("#workspace-open");
const workspaceNewButton = document.querySelector("#workspace-new");
const workspaceDocumentList = document.querySelector("#workspace-document-list");
const workspaceEmpty = document.querySelector("#workspace-empty");
const workspaceDocument = document.querySelector("#workspace-document");
const workspaceDocumentName = document.querySelector("#workspace-document-name");
const workspaceDocumentPath = document.querySelector("#workspace-document-path");
const workspaceDocumentState = document.querySelector("#workspace-document-state");
const workspaceCloseDocumentButton = document.querySelector("#workspace-close-document");
const workspaceSaveDocumentButton = document.querySelector("#workspace-save-document");
const workspaceSaveAsDocumentButton = document.querySelector("#workspace-save-as-document");
const workspaceCloseDialog = document.querySelector("#workspace-close-dialog");
const workspaceCloseDialogTitle = document.querySelector("#workspace-close-dialog-title");
const workspaceCloseDialogMessage = document.querySelector("#workspace-close-dialog-message");
const workspaceCloseDiscardButton = document.querySelector("#workspace-close-discard");
const workspaceCloseSaveButton = document.querySelector("#workspace-close-save");
const workspaceTree = document.querySelector("#workspace-tree");
const workspaceInspectorEmpty = document.querySelector("#workspace-inspector-empty");
const workspaceInspectorContent = document.querySelector("#workspace-inspector-content");
const workspaceBlockName = document.querySelector("#workspace-block-name");
const workspaceBlockSummary = document.querySelector("#workspace-block-summary");
const workspaceEditBlockButton = document.querySelector("#workspace-edit-block");
const workspaceStatus = document.querySelector("#workspace-status");
const workspaceBusy = document.querySelector("#workspace-busy");
const workspaceBusyText = document.querySelector("#workspace-busy-text");
const workspaceBusyTime = document.querySelector("#workspace-busy-time");
const editorBackButton = document.querySelector("#editor-back");
const editorDocumentActions = document.querySelector("#editor-document-actions");
const editorSaveDocumentButton = document.querySelector("#editor-save-document");
const editorSaveAsDocumentButton = document.querySelector("#editor-save-as-document");
const moduleHeading = document.querySelector("#module-heading");
const editorModePill = document.querySelector("#editor-mode-pill");
const editorModeText = document.querySelector("#editor-mode-text");

let currentModule = null;
let currentSpec = null;
let moduleCatalog = [];
let baselinePayload = {};
let baselinePayloadKey = "{}";
let lastSuccessfulPayloadKey = null;
let lastPreviewResult = null;
let customProfileDraft = null;
let customProfileBase = null;
let customProfileBaseValues = null;
let displayedWarnings = [];
let selectionRevision = 0;
let previewRevision = 0;
let previewController = null;
let previewTimer = null;
let statusDescriptor = { key: "status.loading", state: "idle", variables: {} };
let cadPlanKey = null;
let cadPlanController = null;
let cadBuildActive = false;
let activeCadJobId = null;
let workspaceSnapshot = null;
let selectedWorkspaceDocumentId = null;
let selectedWorkspaceBlock = null;
let editorContext = null;
let workspaceActionActive = false;
let workspaceBusyStartedAt = 0;
let workspaceBusyTimer = null;
let workspaceBusyDescriptor = { key: "workspace.opening", variables: {} };
let workspaceReconnectTimer = null;

function setStatus(key, state = "idle", variables = {}) {
  statusDescriptor = { key, state, variables };
  statusText.textContent = t(key, key, variables);
  statusDot.dataset.state = state;
}

function refreshStatusLanguage() {
  setStatus(statusDescriptor.key, statusDescriptor.state, statusDescriptor.variables);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => localizeValidationError(item)).join("; ")
      : detail || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

function localizeValidationError(item) {
  const location = (item.loc || []).filter((part) => part !== "body").join(".");
  const field = location ? localizedFieldName(location, {}) : "";
  const context = item.ctx || {};
  const keyByType = {
    missing: "error.required",
    float_parsing: "error.invalid_number",
    int_parsing: "error.integer_required",
    greater_than: "error.greater_than",
    greater_than_equal: "error.greater_than_equal",
    less_than: "error.less_than",
    less_than_equal: "error.less_than_equal",
  };
  const key = keyByType[item.type] || "error.invalid_value";
  const message = t(key, item.msg || key, { limit: context.gt ?? context.ge ?? context.lt ?? context.le ?? "" });
  return field ? `${field}: ${message}` : message;
}

function updateWorkspaceBusy() {
  workspaceBusyText.textContent = t(
    workspaceBusyDescriptor.key,
    "Opening and recognizing the model in KOMPAS…",
    workspaceBusyDescriptor.variables,
  );
  workspaceBusyTime.textContent = formatElapsed(Date.now() - workspaceBusyStartedAt);
}

function setWorkspaceBusy(key, variables = {}) {
  workspaceActionActive = true;
  workspaceBusyStartedAt = Date.now();
  workspaceBusyDescriptor = { key, variables };
  workspaceBusy.hidden = false;
  workspaceShell.setAttribute("aria-busy", "true");
  workspaceOpenButton.disabled = true;
  workspaceNewButton.disabled = true;
  workspaceRefreshButton.disabled = true;
  workspaceCloseDocumentButton.disabled = true;
  workspaceSaveDocumentButton.disabled = true;
  workspaceSaveAsDocumentButton.disabled = true;
  updateWorkspaceBusy();
  workspaceBusyTimer = window.setInterval(updateWorkspaceBusy, 250);
}

function clearWorkspaceBusy() {
  workspaceActionActive = false;
  workspaceBusy.hidden = true;
  workspaceShell.removeAttribute("aria-busy");
  workspaceOpenButton.disabled = false;
  workspaceNewButton.disabled = false;
  workspaceRefreshButton.disabled = false;
  workspaceCloseDocumentButton.disabled = !currentWorkspaceDocument();
  workspaceSaveDocumentButton.disabled = !currentWorkspaceDocument();
  workspaceSaveAsDocumentButton.disabled = !currentWorkspaceDocument();
  window.clearInterval(workspaceBusyTimer);
  workspaceBusyTimer = null;
}

function resolveRef(schema, root) {
  if (!schema || !schema.$ref) return schema || {};
  const path = schema.$ref.replace(/^#\//, "").split("/");
  const resolved = path.reduce((value, key) => value?.[key], root);
  return { ...(resolved || {}), ...Object.fromEntries(Object.entries(schema).filter(([key]) => key !== "$ref")) };
}

function concreteSchema(schema, root) {
  const resolved = resolveRef(schema, root);
  const alternatives = resolved.anyOf || resolved.oneOf;
  if (!alternatives) return resolved;
  const preferred = alternatives.find((item) => resolveRef(item, root).type !== "null") || alternatives[0];
  return { ...resolved, ...resolveRef(preferred, root), anyOf: undefined, oneOf: undefined };
}

function humanize(name) {
  return name.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function moduleName(module) {
  return t(`module.${module.kind}.name`, module.name);
}

function moduleDescriptionText(module) {
  return t(`module.${module.kind}.description`, module.description);
}

function moduleStandard(module) {
  return t(`module.${module.kind}.standard`, module.standard);
}

function fieldValue(name, schema) {
  if (Object.hasOwn(baselinePayload, name)) return baselinePayload[name];
  return schema.default ?? "";
}

function localizedFieldName(name, schema) {
  return t(`field.${name}`, schema.title || humanize(name));
}

function localizedEnumValue(name, value) {
  return t(`enum.${name}.${value}`, String(value));
}

function localizedFieldHelp(name, schema) {
  return t(`field.${name}.help`, schema.description || "");
}

function localizedFieldPlaceholder(name, schema) {
  const genericKey = schema.type === "object" ? "field.object_placeholder" : "field.array_placeholder";
  return t(`field.${name}.placeholder`, t(genericKey));
}

const customProfileFields = [
  ["datum_width", "b", true],
  ["datum_offset", "h₀", true],
  ["groove_pitch", "e", true],
  ["edge_distance", "f", true],
  ["groove_depth", "h", true],
  ["groove_angle_degrees", "α", true],
  ["approximate_top_width", "bₐ", false],
  ["minimum_datum_diameter", "Dmin", false],
  ["standard_top_edge_radius", "r", false],
];

function readCustomProfileDraft() {
  const draft = {};
  for (const input of fieldsContainer.querySelectorAll("[data-custom-profile-field]")) {
    if (!input.value.trim() || !Number.isFinite(input.valueAsNumber)) continue;
    draft[input.dataset.customProfileField] = input.valueAsNumber;
  }
  return Object.keys(draft).length ? draft : customProfileDraft;
}

function createCustomProfileEditor() {
  const section = document.createElement("fieldset");
  section.className = "custom-profile-editor";
  section.dataset.customProfileEditor = "";

  const legend = document.createElement("legend");
  legend.textContent = t("custom.title");
  section.append(legend);

  const context = document.createElement("div");
  context.className = "custom-profile-context";
  const status = document.createElement("span");
  status.textContent = customProfileBase
    ? t("custom.based_on", "", { designation: customProfileBase })
    : t("custom.new_profile");
  const restore = document.createElement("button");
  restore.type = "button";
  restore.className = "text-button";
  restore.dataset.restoreCustom = "";
  restore.textContent = t("custom.restore_base");
  restore.hidden = !customProfileBaseValues;
  context.append(status, restore);
  section.append(context);

  const grid = document.createElement("div");
  grid.className = "custom-profile-grid";
  for (const [name, symbol, required] of customProfileFields) {
    const label = document.createElement("label");
    label.className = "custom-profile-field";
    if (!required) label.classList.add("custom-profile-advanced");
    const caption = document.createElement("span");
    caption.textContent = `${t(`custom.field.${name}`)} (${symbol})`;
    const input = document.createElement("input");
    input.type = "number";
    input.step = "any";
    input.min = name === "minimum_datum_diameter" || name === "approximate_top_width" ? "0" : "0.000001";
    input.name = `custom_${name}`;
    input.dataset.customProfileField = name;
    input.required = required;
    const value = customProfileDraft?.[name];
    input.value = Number.isFinite(value) ? value : "";
    label.append(caption, input);
    grid.append(label);
  }
  section.append(grid);

  const advanced = document.createElement("button");
  advanced.type = "button";
  advanced.className = "text-button custom-advanced-toggle";
  advanced.dataset.toggleCustomAdvanced = "";
  advanced.textContent = t("custom.show_advanced");
  section.append(advanced);
  return section;
}

function createField(name, fieldSchema, required) {
  const schema = concreteSchema(fieldSchema, currentSpec.schema);
  const wrapper = document.createElement("label");
  wrapper.className = "field";
  wrapper.dataset.kind = schema.type || "string";
  wrapper.dataset.fieldName = name;

  const heading = document.createElement("span");
  heading.className = "field-heading";
  const title = document.createElement("span");
  title.className = "field-title";
  title.dataset.fieldLabel = "";
  title.textContent = localizedFieldName(name, schema);
  heading.append(title);
  if (required) {
    const marker = document.createElement("sup");
    marker.textContent = "•";
    marker.title = t("field.required_title");
    marker.dataset.requiredMarker = "";
    heading.append(marker);
  }
  const variable = document.createElement("code");
  variable.className = "field-variable";
  variable.textContent = name;
  heading.append(variable);
  wrapper.append(heading);

  const value = fieldValue(name, schema);
  let input;
  if (Array.isArray(schema.enum)) {
    input = document.createElement("select");
    for (const optionValue of schema.enum) {
      const option = document.createElement("option");
      option.value = String(optionValue);
      option.dataset.enumValue = String(optionValue);
      option.textContent = localizedEnumValue(name, optionValue);
      option.selected = optionValue === value;
      input.append(option);
    }
  } else if (schema.type === "boolean") {
    input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(value);
    wrapper.classList.add("checkbox-field");
  } else if (schema.type === "object" || schema.type === "array") {
    input = document.createElement("textarea");
    input.rows = name === "custom_profile" ? 8 : 4;
    input.placeholder = localizedFieldPlaceholder(name, schema);
    input.value = value && typeof value === "object" ? JSON.stringify(value, null, 2) : "";
  } else {
    input = document.createElement("input");
    input.type = schema.type === "number" || schema.type === "integer" ? "number" : "text";
    if (input.type === "number") input.step = schema.type === "integer" ? "1" : "any";
    if (schema.minimum !== undefined) input.min = schema.minimum;
    if (schema.maximum !== undefined) input.max = schema.maximum;
    input.value = value;
  }

  input.name = name;
  input.dataset.schemaType = schema.type || "string";
  input.required = required && input.type !== "checkbox";
  wrapper.append(input);

  const help = localizedFieldHelp(name, schema);
  if (help) {
    const description = document.createElement("small");
    description.dataset.fieldHelp = "";
    description.textContent = help;
    wrapper.append(description);
  }
  return wrapper;
}

function syncConditionalFields() {
  const designation = fieldsContainer.querySelector("[name='designation']")?.value;
  const customMode = designation === "CUSTOM";
  const existing = fieldsContainer.querySelector("[data-custom-profile-editor]");
  for (const wrapper of fieldsContainer.querySelectorAll("[data-field-name^='custom_']")) {
    const input = wrapper.querySelector("input, select, textarea");
    wrapper.hidden = !customMode;
    if (input) {
      input.disabled = !customMode;
      input.required = customMode;
      if (customMode && !input.value) {
        const defaults = {
          custom_shape: "trapezoidal",
          custom_pitch: "5",
          custom_groove_depth: "1.5",
          custom_groove_width: "3",
          custom_pitch_line_offset: "0.6",
          custom_tip_radius: "0.3",
          custom_root_radius: "0.5",
        };
        input.value = defaults[wrapper.dataset.fieldName] || "";
      }
    }
  }
  if (currentModule?.kind !== "v_belt") {
    existing?.remove();
    return;
  }
  if (!customMode) {
    existing?.remove();
    return;
  }
  if (!customProfileDraft && lastPreviewResult?.editable_profile) {
    customProfileDraft = { ...lastPreviewResult.editable_profile };
  }
  if (!existing) fieldsContainer.append(createCustomProfileEditor());
}

function renderFields() {
  fieldsContainer.replaceChildren();
  const properties = currentSpec.schema.properties || {};
  const required = new Set(currentSpec.schema.required || []);
  for (const [name, schema] of Object.entries(properties)) {
    if (name === "custom_profile" || name === "profile_overrides") continue;
    fieldsContainer.append(createField(name, schema, required.has(name)));
  }
  syncConditionalFields();
}

function localizeFields() {
  const properties = currentSpec?.schema?.properties || {};
  for (const wrapper of fieldsContainer.querySelectorAll("[data-field-name]")) {
    const name = wrapper.dataset.fieldName;
    const schema = concreteSchema(properties[name], currentSpec.schema);
    wrapper.querySelector("[data-field-label]").textContent = localizedFieldName(name, schema);
    const marker = wrapper.querySelector("[data-required-marker]");
    if (marker) marker.title = t("field.required_title");
    for (const option of wrapper.querySelectorAll("option[data-enum-value]")) {
      option.textContent = localizedEnumValue(name, option.dataset.enumValue);
    }
    const textarea = wrapper.querySelector("textarea");
    if (textarea) {
      textarea.placeholder = localizedFieldPlaceholder(name, schema);
    }
    const help = wrapper.querySelector("[data-field-help]");
    if (help) help.textContent = localizedFieldHelp(name, schema);
  }
}

function collectPayload() {
  const payload = {};
  for (const input of fieldsContainer.querySelectorAll("input:not(:disabled), select:not(:disabled), textarea:not(:disabled)")) {
    if (input.dataset.customProfileField) continue;
    const type = input.dataset.schemaType;
    if (type === "boolean") {
      payload[input.name] = input.checked;
      continue;
    }
    const raw = input.value.trim();
    if (!raw) continue;
    if (type === "number" || type === "integer") {
      const value = input.valueAsNumber;
      if (!Number.isFinite(value)) throw new Error(`${localizedFieldName(input.name, {})}: ${t("error.invalid_number")}`);
      if (type === "integer" && !Number.isInteger(value)) {
        throw new Error(`${localizedFieldName(input.name, {})}: ${t("error.integer_required")}`);
      }
      payload[input.name] = value;
    }
    else if (type === "object" || type === "array") payload[input.name] = JSON.parse(raw);
    else payload[input.name] = raw;
  }
  if (currentModule?.kind === "v_belt" && payload.designation === "CUSTOM") {
    const customProfile = { designation: "CUSTOM", family: "custom" };
    for (const input of fieldsContainer.querySelectorAll("[data-custom-profile-field]")) {
      if (!input.value.trim()) continue;
      const value = input.valueAsNumber;
      if (!Number.isFinite(value)) throw new Error(`${t(`custom.field.${input.dataset.customProfileField}`)}: ${t("error.invalid_number")}`);
      customProfile[input.dataset.customProfileField] = value;
    }
    payload.custom_profile = customProfile;
  }
  if (baselinePayload.profile_overrides && typeof baselinePayload.profile_overrides === "object") {
    payload.profile_overrides = { ...baselinePayload.profile_overrides };
  }
  return payload;
}

function payloadKey(payload) {
  return JSON.stringify(payload);
}

function currentDirtyState() {
  try {
    return payloadKey(collectPayload()) !== baselinePayloadKey;
  } catch (_error) {
    return true;
  }
}

function updateDirtyState() {
  const dirty = currentDirtyState();
  resetButton.disabled = !dirty;
  liveIndicator.dataset.state = dirty ? "dirty" : "live";
  if (dirty) {
    const key = (() => {
      try { return payloadKey(collectPayload()); } catch (_error) { return null; }
    })();
    if (key !== cadPlanKey) {
      cadPlanController?.abort();
      cadPlanController = null;
      cadPlanKey = null;
      cadCreateButton.disabled = true;
      if (!cadBuildActive) cadResult.textContent = "";
    }
  }
  if (editorContext && !cadBuildActive && cadPlanKey) {
    cadCreateButton.disabled = !dirty;
  }
  return dirty;
}

function renderReadableSubscripts(element, value) {
  element.replaceChildren(...splitReadableSubscripts(value).map((run) => {
    if (!run.subscript) return document.createTextNode(run.text);
    const subscript = document.createElement("sub");
    subscript.className = "readable-subscript";
    subscript.textContent = run.text;
    return subscript;
  }));
}

function renderSummary(values) {
  summary.replaceChildren();
  for (const [key, value] of Object.entries(values || {})) {
    if (value === null || value === undefined) continue;
    const dt = document.createElement("dt");
    renderReadableSubscripts(dt, t(`summary.${key}`, humanize(key)));
    const dd = document.createElement("dd");
    if (typeof value === "number") dd.textContent = formatNumber(value, 2);
    else if (["standard_system", "profile", "designation", "profile_shape"].includes(key)) dd.textContent = localizedEnumValue(key, value);
    else dd.textContent = String(value);
    summary.append(dt, dd);
  }
}

function renderWarnings(items, remember = true) {
  if (remember) displayedWarnings = items || [];
  warningsList.replaceChildren();
  warningsSection.hidden = !displayedWarnings.length;
  for (const warning of displayedWarnings) {
    const item = document.createElement("li");
    item.textContent = localizeWarning(warning);
    warningsList.append(item);
  }
}

function invalidatePreviewRequest() {
  previewRevision += 1;
  previewController?.abort();
  previewController = null;
}

function previewResultWarnings(result) {
  return result.warning_items?.length ? result.warning_items : (result.warnings || []);
}

async function runPreview({ force = false } = {}) {
  clearTimeout(previewTimer);
  previewTimer = null;
  invalidatePreviewRequest();
  const revision = ++previewRevision;
  const controller = new AbortController();
  previewController = controller;

  const dirty = updateDirtyState();
  if (!form.checkValidity()) {
    cadPlanController?.abort();
    cadPlanKey = null;
    cadCreateButton.disabled = true;
    setStatus("status.incomplete", "error");
    window.dispatchEvent(new CustomEvent("geomwright-preview-state", { detail: { state: "stale" } }));
    previewController = null;
    return;
  }

  let payload;
  try {
    payload = collectPayload();
  } catch (error) {
    renderWarnings([{ message: error.message }]);
    setStatus("status.error", "error", { message: error.message });
    window.dispatchEvent(new CustomEvent("geomwright-preview-state", { detail: { state: "stale" } }));
    previewController = null;
    return;
  }

  const key = payloadKey(payload);
  if (!force && key === lastSuccessfulPayloadKey) {
    const components = lastPreviewResult?.closed_points?.length || 0;
    setStatus(dirty ? "status.updated_dirty" : "status.updated", dirty ? "dirty" : "ready", { count: components });
    window.dispatchEvent(new CustomEvent("geomwright-preview-state", { detail: { state: "ready" } }));
    previewController = null;
    if (currentModule.capabilities.build && cadPlanKey !== key) await prepareCadPlan(payload, key);
    return;
  }

  setStatus("status.calculating", "working");
  window.dispatchEvent(new CustomEvent("geomwright-preview-state", { detail: { state: "pending" } }));
  try {
    const result = await requestJson(currentModule.preview_url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (revision !== previewRevision) return;

    lastSuccessfulPayloadKey = key;
    lastPreviewResult = result;
    if (result.family === "v_belt" && result.editable_profile && result.request?.designation !== "CUSTOM") {
      customProfileDraft = { ...result.editable_profile };
      customProfileBaseValues = { ...result.editable_profile };
      customProfileBase = result.request.designation;
    } else if (result.request?.designation === "CUSTOM") {
      customProfileDraft = { ...result.editable_profile };
    }
    renderSummary(result.summary);
    renderWarnings(previewResultWarnings(result));
    window.dispatchEvent(new CustomEvent("geomwright-preview", { detail: result }));
    window.dispatchEvent(new CustomEvent("geomwright-preview-state", { detail: { state: "ready" } }));
    const components = result.closed_points?.length || 0;
    setStatus(dirty ? "status.updated_dirty" : "status.updated", dirty ? "dirty" : "ready", { count: components });
    if (currentModule.capabilities.build) await prepareCadPlan(payload, key);
  } catch (error) {
    if (error.name === "AbortError" || revision !== previewRevision) return;
    renderWarnings([{ message: error.message }]);
    setStatus("status.error", "error", { message: error.message });
    window.dispatchEvent(new CustomEvent("geomwright-preview-state", { detail: { state: "stale" } }));
  } finally {
    if (revision === previewRevision) previewController = null;
  }
}

function schedulePreview({ immediate = false } = {}) {
  clearTimeout(previewTimer);
  invalidatePreviewRequest();
  const dirty = updateDirtyState();
  setStatus("status.pending", dirty ? "dirty" : "working");
  window.dispatchEvent(new CustomEvent("geomwright-preview-state", { detail: { state: "pending" } }));
  previewTimer = setTimeout(() => runPreview(), immediate ? 0 : 280);
}

function renderModuleCatalogText() {
  for (const option of moduleSelect.options) {
    const module = moduleCatalog.find((item) => item.kind === option.value);
    if (module) option.textContent = moduleName(module);
  }
  if (currentModule) {
    moduleDescription.textContent = moduleDescriptionText(currentModule);
    standardBadge.textContent = moduleStandard(currentModule);
    setStatus(statusDescriptor.key, statusDescriptor.state, statusDescriptor.variables);
  }
}

function currentWorkspaceDocument() {
  return (workspaceSnapshot?.documents || []).find(
    (item) => item.document.runtime_id === selectedWorkspaceDocumentId,
  ) || null;
}

function renderWorkspaceBlockSummary(block) {
  workspaceBlockSummary.replaceChildren();
  for (const [key, value] of Object.entries(block.profile || {})) {
    const dt = document.createElement("dt");
    renderReadableSubscripts(dt, localizedFieldName(key, {}));
    const dd = document.createElement("dd");
    dd.textContent = typeof value === "number" ? formatNumber(value, 2) : localizedEnumValue(key, value);
    workspaceBlockSummary.append(dt, dd);
  }
}

function managedBlockName(block) {
  const profile = block.profile || {};
  const family = {
    v_belt: "block.v_belt",
    poly_v: "block.poly_v",
    flat_belt: "block.flat_belt",
    timing_trapezoidal: "block.timing_trapezoidal",
    timing_curvilinear: "block.timing_curvilinear",
  }[block.module] || "block.generic";
  return t(family, block.name || block.module, {
    designation: profile.designation || "",
    count: profile.groove_count || profile.tooth_count || "",
    crown: formatNumber(profile.crown_height || 0),
  });
}

function selectWorkspaceBlock(block) {
  selectedWorkspaceBlock = block;
  workspaceInspectorEmpty.hidden = true;
  workspaceInspectorContent.hidden = false;
  workspaceBlockName.textContent = managedBlockName(block);
  renderWorkspaceBlockSummary(block);
  workspaceEditBlockButton.disabled = !block.editable;
  for (const item of workspaceTree.querySelectorAll("button.workspace-tree-item")) {
    item.classList.toggle("selected", item.dataset.blockId === block.id);
  }
}

function renderWorkspaceDocument() {
  const entry = currentWorkspaceDocument();
  const selectedBlockId = selectedWorkspaceBlock?.id;
  selectedWorkspaceBlock = selectedBlockId
    ? (entry?.blocks || []).find((block) => block.id === selectedBlockId) || null
    : null;
  workspaceInspectorEmpty.hidden = false;
  workspaceInspectorContent.hidden = true;
  workspaceTree.replaceChildren();
  workspaceEmpty.hidden = Boolean(entry);
  workspaceDocument.hidden = !entry;
  if (!entry) return;

  const documentInfo = entry.document;
  workspaceDocumentName.textContent = documentInfo.name;
  workspaceDocumentPath.textContent = documentInfo.path || t("workspace.unsaved", "Unsaved document");
  workspaceDocumentState.textContent = documentInfo.changed
    ? t("workspace.changed", "Changed")
    : t("workspace.saved", "Saved");
  workspaceCloseDocumentButton.disabled = workspaceActionActive;
  workspaceSaveDocumentButton.disabled = workspaceActionActive || !documentInfo.changed;
  workspaceSaveAsDocumentButton.disabled = workspaceActionActive;

  for (const block of entry.blocks || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "workspace-tree-item";
    button.dataset.blockId = block.id;
    button.innerHTML = `<span class="workspace-tree-icon">◆</span><span class="workspace-tree-label"></span><span class="workspace-tree-meta">Studio</span>`;
    button.querySelector(".workspace-tree-label").textContent = managedBlockName(block);
    button.addEventListener("click", () => selectWorkspaceBlock(block));
    workspaceTree.append(button);
  }
  const externalOperations = (entry.operations || []).filter((item) => !item.owned);
  if (externalOperations.length) {
    const group = document.createElement("div");
    group.className = "workspace-tree-item";
    group.innerHTML = `<span class="workspace-tree-icon">○</span><span class="workspace-tree-label"></span><span class="workspace-tree-meta"></span>`;
    group.querySelector(".workspace-tree-label").textContent = t("workspace.kompas_operations", "KOMPAS operations");
    group.querySelector(".workspace-tree-meta").textContent = String(externalOperations.length);
    workspaceTree.append(group);
  }
  if (!(entry.blocks || []).length && !externalOperations.length) {
    const empty = document.createElement("div");
    empty.className = "workspace-empty";
    empty.textContent = t("workspace.no_blocks", "No managed Studio blocks recognized");
    workspaceTree.append(empty);
  }
  if (selectedWorkspaceBlock) selectWorkspaceBlock(selectedWorkspaceBlock);
}

function requestCloseDecision(documentInfo) {
  workspaceCloseDialogTitle.textContent = t(
    "workspace.close_dialog_title",
    `Close “${documentInfo.name}”?`,
    { name: documentInfo.name },
  );
  workspaceCloseDialogMessage.textContent = documentInfo.changed
    ? t("workspace.close_changed", "This document has unsaved changes. Save them before closing?")
    : t("workspace.close_unchanged", "The document is saved and can be closed without additional changes.");
  workspaceCloseDiscardButton.textContent = t(
    documentInfo.changed ? "workspace.discard" : "workspace.close_without_save",
  );
  workspaceCloseSaveButton.hidden = !documentInfo.changed;
  return new Promise((resolve) => {
    workspaceCloseDialog.addEventListener("close", () => resolve(workspaceCloseDialog.returnValue), { once: true });
    workspaceCloseDialog.returnValue = "cancel";
    workspaceCloseDialog.showModal();
  });
}

async function closeWorkspaceDocument(entry = currentWorkspaceDocument()) {
  if (!entry || workspaceActionActive) return;
  const info = entry.document;
  const decision = info.changed ? await requestCloseDecision(info) : "discard";
  if (!decision || decision === "cancel") return;

  let savePath = null;
  if (decision === "save" && !info.path) {
    setWorkspaceBusy("workspace.choosing_save_file");
    try {
      const selection = await requestJson("/workspace/pick-save-file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ suggested_name: info.name }),
      });
      if (selection.cancelled) return;
      savePath = selection.path;
    } catch (error) {
      workspaceStatus.textContent = t("workspace.error", error.message, { message: error.message });
      return;
    } finally {
      clearWorkspaceBusy();
    }
  }

  const operationKey = decision === "save" ? "workspace.saving_closing" : "workspace.closing";
  setWorkspaceBusy(operationKey, { name: info.name });
  workspaceStatus.textContent = t(operationKey, operationKey, { name: info.name });
  try {
    const response = await requestJson("/workspace/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document_id: info.runtime_id,
        action: decision,
        save_path: savePath,
      }),
    });
    workspaceSnapshot = response.workspace;
    selectedWorkspaceDocumentId = workspaceSnapshot.active_runtime_id
      || workspaceSnapshot.documents?.[0]?.document.runtime_id
      || null;
    workspaceStatus.textContent = t("workspace.ready", "KOMPAS documents synchronized");
    renderWorkspace();
  } catch (error) {
    workspaceStatus.textContent = t("workspace.error", error.message, { message: error.message });
  } finally {
    clearWorkspaceBusy();
  }
}

async function saveWorkspaceDocument(documentInfo = currentWorkspaceDocument()?.document, { saveAs = false } = {}) {
  if (!documentInfo || workspaceActionActive) return false;
  const savingFromEditor = !editorShell.hidden;
  let savePath = null;
  if (saveAs || !documentInfo.path) {
    if (savingFromEditor) {
      editorSaveDocumentButton.disabled = true;
      editorSaveAsDocumentButton.disabled = true;
      cadResult.textContent = t("workspace.choosing_save_file");
    } else {
      setWorkspaceBusy("workspace.choosing_save_file");
    }
    try {
      const selection = await requestJson("/workspace/pick-save-file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ suggested_name: documentInfo.name }),
      });
      if (selection.cancelled) return false;
      savePath = selection.path;
    } catch (error) {
      workspaceStatus.textContent = t("workspace.error", error.message, { message: error.message });
      return false;
    } finally {
      if (savingFromEditor) {
        editorSaveDocumentButton.disabled = false;
        editorSaveAsDocumentButton.disabled = false;
      }
      else clearWorkspaceBusy();
    }
  }
  if (savingFromEditor) {
    editorSaveDocumentButton.disabled = true;
    editorSaveAsDocumentButton.disabled = true;
    cadResult.textContent = t("workspace.saving", undefined, { name: documentInfo.name });
  } else {
    setWorkspaceBusy("workspace.saving", { name: documentInfo.name });
  }
  try {
    const response = await requestJson(saveAs ? "/workspace/save-as" : "/workspace/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_id: documentInfo.runtime_id, save_path: savePath }),
    });
    workspaceSnapshot = response.workspace;
    const previousDocumentId = documentInfo.runtime_id;
    selectedWorkspaceDocumentId = response.saved?.document?.runtime_id
      || response.saved?.document?.path
      || workspaceSnapshot.active_runtime_id
      || selectedWorkspaceDocumentId;
    if (editorContext?.documentId === previousDocumentId) {
      editorContext.documentId = selectedWorkspaceDocumentId;
    }
    workspaceStatus.textContent = t("workspace.saved_ready", "Document saved", { name: documentInfo.name });
    if (savingFromEditor) {
      cadResult.dataset.state = "ready";
      cadResult.textContent = t("workspace.saved_ready", "Document saved", { name: documentInfo.name });
    }
    renderWorkspace();
    return true;
  } catch (error) {
    workspaceStatus.textContent = t("workspace.error", error.message, { message: error.message });
    return false;
  } finally {
    if (savingFromEditor) {
      editorSaveDocumentButton.disabled = false;
      editorSaveAsDocumentButton.disabled = false;
    }
    else clearWorkspaceBusy();
  }
}

function renderWorkspace() {
  workspaceDocumentList.replaceChildren();
  const documents = workspaceSnapshot?.documents || [];
  for (const [documentIndex, entry] of documents.entries()) {
    const info = entry.document;
    const card = document.createElement("div");
    card.className = "workspace-document-card";
    card.classList.toggle("active", info.runtime_id === selectedWorkspaceDocumentId);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "workspace-document-select";
    const strong = document.createElement("strong");
    strong.textContent = info.path ? info.name : `${info.name} ${documentIndex + 1}`;
    const small = document.createElement("small");
    small.textContent = info.path || `${info.active ? `${t("workspace.active", "Active")} · ` : ""}${t("workspace.unsaved", "Unsaved")} · ${(entry.blocks || []).length} Studio`;
    button.append(strong, small);
    button.addEventListener("click", async () => {
      selectedWorkspaceDocumentId = info.runtime_id;
      renderWorkspace();
      if (!info.active) {
        workspaceStatus.textContent = t("workspace.activating", "Activating document in KOMPAS…");
        try {
          const response = await requestJson("/workspace/activate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ document_id: info.runtime_id }),
          });
          workspaceSnapshot = response.workspace;
          workspaceStatus.textContent = t("workspace.ready", "KOMPAS documents synchronized");
          renderWorkspace();
        } catch (error) {
          workspaceStatus.textContent = t("workspace.error", error.message, { message: error.message });
        }
      }
    });
    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "icon-button danger-icon-button";
    closeButton.title = t("workspace.close");
    closeButton.setAttribute("aria-label", t("workspace.close"));
    closeButton.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19"/></svg>`;
    closeButton.addEventListener("click", () => closeWorkspaceDocument(entry));
    card.append(button, closeButton);
    workspaceDocumentList.append(card);
  }
  renderWorkspaceDocument();
}

async function refreshWorkspace({ followActive = false } = {}) {
  workspaceStatus.textContent = t("workspace.loading", "Reading KOMPAS documents…");
  try {
    workspaceSnapshot = await requestJson("/workspace");
    if (workspaceSnapshot.connected === false) {
      selectedWorkspaceDocumentId = null;
      selectedWorkspaceBlock = null;
      workspaceStatus.textContent = t("workspace.disconnected", "Start KOMPAS-3D; Studio will connect automatically.");
      renderWorkspace();
      window.clearTimeout(workspaceReconnectTimer);
      workspaceReconnectTimer = window.setTimeout(() => refreshWorkspace(), 1500);
      return;
    }
    window.clearTimeout(workspaceReconnectTimer);
    workspaceReconnectTimer = null;
    const ids = new Set((workspaceSnapshot.documents || []).map((item) => item.document.runtime_id));
    if (!selectedWorkspaceDocumentId || !ids.has(selectedWorkspaceDocumentId)) {
      selectedWorkspaceDocumentId = workspaceSnapshot.active_runtime_id
        || workspaceSnapshot.documents?.[0]?.document.runtime_id
        || null;
    }
    workspaceStatus.textContent = t("workspace.ready", "KOMPAS documents synchronized");
    renderWorkspace();
  } catch (error) {
    workspaceStatus.textContent = t("workspace.error", error.message, { message: error.message });
  }
}

function showEditor({ locked = false } = {}) {
  workspaceShell.hidden = true;
  editorShell.hidden = false;
  moduleHeading.classList.toggle("locked", locked);
  moduleHeading.dataset.lockedName = locked ? moduleName(currentModule) : "";
  moduleSelect.disabled = locked;
  document.querySelector(".cad-controls").hidden = !currentModule.capabilities.build;
  editorModePill.title = t(currentModule.capabilities.build ? "app.managed_cad_title" : "app.preview_only_title");
  editorModeText.textContent = t(currentModule.capabilities.build ? "app.managed_cad" : "app.preview_only");
  cadTitle.textContent = t(locked ? "cad.update_title" : "cad.title");
  cadDescription.textContent = t(locked ? "cad.update_description" : "cad.description");
  cadCreateButton.textContent = t(locked ? "cad.update" : "cad.create");
  editorDocumentActions.hidden = !locked;
  window.dispatchEvent(new Event("resize"));
}

async function openSelectedBlockEditor() {
  if (!selectedWorkspaceBlock) return;
  editorContext = {
    documentId: selectedWorkspaceDocumentId,
    block: selectedWorkspaceBlock,
  };
  await selectModule(selectedWorkspaceBlock.module, false);
  baselinePayload = { ...baselinePayload, ...(selectedWorkspaceBlock.profile || {}) };
  baselinePayloadKey = payloadKey(baselinePayload);
  renderFields();
  showEditor({ locked: true });
  await runPreview({ force: true });
}

function showWorkspace() {
  editorShell.hidden = true;
  workspaceShell.hidden = false;
  editorContext = null;
  refreshWorkspace();
}

async function selectModule(kind, autoPreview = true) {
  const revision = ++selectionRevision;
  invalidatePreviewRequest();
  clearTimeout(previewTimer);
  const module = moduleCatalog.find((item) => item.kind === kind);
  if (!module) throw new Error(t("error.unknown_module", `Unknown module: ${kind}`, { kind }));

  const wasModuleSelectDisabled = moduleSelect.disabled;
  moduleSelect.disabled = true;
  try {
    const spec = await requestJson(module.spec_url);
    if (revision !== selectionRevision) return;

    currentModule = module;
    currentSpec = spec;
    baselinePayload = JSON.parse(JSON.stringify(spec.defaults));
    baselinePayloadKey = payloadKey(baselinePayload);
    lastSuccessfulPayloadKey = null;
    lastPreviewResult = null;
    customProfileDraft = null;
    customProfileBase = null;
    customProfileBaseValues = null;
    displayedWarnings = [];
    cadPlanKey = null;
    cadPlanController?.abort();
    cadPlanController = null;
    cadCreateButton.disabled = true;
    cadResult.textContent = "";
    moduleSelect.value = kind;
    moduleDescription.textContent = moduleDescriptionText(module);
    standardBadge.textContent = moduleStandard(module);
    document.querySelector(".cad-controls").hidden = !module.capabilities.build;
    editorModePill.title = t(module.capabilities.build ? "app.managed_cad_title" : "app.preview_only_title");
    editorModeText.textContent = t(module.capabilities.build ? "app.managed_cad" : "app.preview_only");
    renderFields();
    renderSummary({});
    renderWarnings([]);
    updateDirtyState();
    setStatus("status.module_ready", "idle", { module: moduleName(module) });
    if (autoPreview) await runPreview({ force: true });
  } finally {
    if (revision === selectionRevision) moduleSelect.disabled = wasModuleSelectDisabled;
  }
}

async function prepareCadPlan(payload, key = payloadKey(payload)) {
  if (!currentModule.capabilities.build) {
    cadPlanKey = null;
    cadCreateButton.disabled = true;
    cadResult.textContent = "";
    return;
  }
  cadPlanController?.abort();
  const controller = new AbortController();
  cadPlanController = controller;
  cadCreateButton.disabled = true;
  cadResult.dataset.state = "";
  cadResult.textContent = t("cad.plan_calculating");
  const planStartedAt = performance.now();
  try {
    const plan = await requestJson(currentModule.cad_plan_url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (controller !== cadPlanController) return;
    cadPlanKey = key;
    cadCreateButton.disabled = cadBuildActive || (Boolean(editorContext) && !currentDirtyState());
    cadResult.dataset.state = "ready";
    const planDimensions = cadPlanDisplayDimensions(plan);
    cadResult.textContent = t("cad.plan_ready", "CAD plan ready", {
      elapsed: formatPlanElapsed(performance.now() - planStartedAt),
      diameter: formatNumber(planDimensions.outerDiameter),
      width: formatNumber(planDimensions.faceWidth),
    });
  } catch (error) {
    if (error.name === "AbortError" || controller !== cadPlanController) return;
    cadPlanKey = null;
    cadResult.dataset.state = "error";
    cadResult.textContent = t("cad.error", error.message, { message: error.message });
  } finally {
    if (controller === cadPlanController) cadPlanController = null;
  }
}

function cadPlanDisplayDimensions(plan) {
  const target = plan?.target;
  if (target && Number.isFinite(target.outer_diameter)
      && Number.isFinite(target.axial_min) && Number.isFinite(target.axial_max)) {
    return {
      outerDiameter: target.outer_diameter,
      faceWidth: target.axial_max - target.axial_min,
    };
  }
  const derived = plan?.profile_preview?.derived || {};
  if (Number.isFinite(derived.outer_diameter) && Number.isFinite(derived.face_width)) {
    return {
      outerDiameter: derived.outer_diameter,
      faceWidth: derived.face_width,
    };
  }
  throw new Error(t("error.cad_plan_dimensions_missing"));
}

function formatElapsed(milliseconds) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function formatPlanElapsed(milliseconds) {
  if (milliseconds < 1000) {
    return Math.max(1, Math.round(milliseconds)).toLocaleString(getLocale(), {
      style: "unit",
      unit: "millisecond",
      unitDisplay: "short",
    });
  }
  return (milliseconds / 1000).toLocaleString(getLocale(), {
    maximumFractionDigits: 2,
    style: "unit",
    unit: "second",
    unitDisplay: "short",
  });
}

function cadOperationText(job) {
  const progress = job.progress || {};
  const variables = (progress.names || []).join(", ");
  return t(`cad.operation.${progress.operation || "queued"}`, progress.operation || "", {
    name: progress.name || "",
    variables,
  });
}

async function waitForCadJob(job, startedAt) {
  cadProgress.hidden = false;
  const updateProgress = () => {
    const progress = Number(job.progress?.percent ?? 0);
    cadProgressBar.setAttribute("aria-valuenow", String(progress));
    cadProgressFill.style.width = `${progress}%`;
    cadProgressPercent.textContent = `${progress}%`;
    cadProgressStage.textContent = cadOperationText(job);
    cadProgressTime.textContent = formatElapsed(Date.now() - startedAt);
  };
  const timer = window.setInterval(updateProgress, 250);
  try {
    while (true) {
      updateProgress();
      if (["completed", "failed", "cancelled"].includes(job.status)) return job;
      await new Promise((resolve) => setTimeout(resolve, 500));
      job = await requestJson(`/cad/jobs/${job.id}`);
    }
  } finally {
    window.clearInterval(timer);
  }
}

async function waitForCreatedBlock(result, moduleKind, timeoutMilliseconds = 15000, previousDocumentIds = new Set()) {
  const runtimeId = result?.document?.runtime_id || result?.document?.id;
  const deadline = Date.now() + timeoutMilliseconds;
  do {
    const snapshot = await requestJson("/workspace");
    const entry = (snapshot.documents || []).find(
      (item) => item.document.runtime_id === runtimeId,
    ) || (snapshot.documents || []).find(
      (item) => !previousDocumentIds.has(item.document.runtime_id)
        && item.blocks?.some((block) => block.module === moduleKind),
    );
    const block = entry?.blocks?.find((item) => item.module === moduleKind);
    if (entry && block) return { snapshot, entry, block };
    await new Promise((resolve) => setTimeout(resolve, 400));
  } while (Date.now() < deadline);
  return null;
}

async function createManagedPulley() {
  const profile = collectPayload();
  if (cadPlanKey !== payloadKey(profile)) {
    await prepareCadPlan(profile);
    return;
  }
  const updating = Boolean(editorContext);
  let documentsBeforeCreate = new Set();
  if (!updating) {
    workspaceSnapshot = await requestJson("/workspace");
    documentsBeforeCreate = new Set(
      (workspaceSnapshot.documents || []).map((item) => item.document.runtime_id),
    );
  }
  const modelName = editorContext?.block?.name || "Geomwright pulley";
  if (!window.confirm(t(updating ? "cad.update_confirm" : "cad.confirm", undefined, { name: modelName }))) return;
  cadBuildActive = true;
  cadCancelButton.hidden = false;
  cadCreateButton.disabled = true;
  cadResult.dataset.state = "";
  cadResult.textContent = "";
  const startedAt = Date.now();
  try {
    const jobUrl = updating
      ? `/modules/${currentModule.kind}/cad/update-jobs`
      : currentModule.cad_job_url;
    const startedJob = await requestJson(jobUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        profile,
        previous_profile: editorContext?.block?.profile,
        confirm_write: true,
        document_id: editorContext?.documentId,
        block_id: editorContext?.block?.id,
        name: modelName,
      }),
    });
    activeCadJobId = startedJob.id;
    const job = await waitForCadJob(startedJob, startedAt);
    if (job.status === "failed") throw new Error(job.error || "CAD job failed");
    if (job.status === "cancelled") throw new Error(t("cad.cancelled"));
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const elapsed = formatElapsed(Date.now() - startedAt);
    cadResult.dataset.state = "ready";
    cadResult.textContent = t(
      updating ? "cad.updated" : "cad.created",
      updating ? "Model rebuilt and verified" : "Pulley created and verified",
      { elapsed },
    );
    if (updating) {
      baselinePayload = { ...profile };
      baselinePayloadKey = payloadKey(profile);
      updateDirtyState();
      const response = await requestJson("/workspace");
      workspaceSnapshot = response;
      const refreshedEntry = (workspaceSnapshot.documents || []).find(
        (item) => item.document.runtime_id === editorContext.documentId,
      );
      const refreshedBlock = refreshedEntry?.blocks?.find((item) => item.module === currentModule.kind);
      if (refreshedBlock) editorContext.block = refreshedBlock;
      const activeEntry = (workspaceSnapshot.documents || []).find((item) => item.document.active);
      if (activeEntry) editorContext.documentId = activeEntry.document.runtime_id;
      editorSaveDocumentButton.disabled = false;
      editorSaveAsDocumentButton.disabled = false;
    } else {
      const created = await waitForCreatedBlock(job.result, currentModule.kind, 15000, documentsBeforeCreate);
      if (!created) {
        throw new Error(t("cad.created_block_missing", "The created managed block was not found in KOMPAS readback."));
      }
      workspaceSnapshot = created.snapshot;
      const createdEntry = created.entry;
      const createdBlock = created.block;
      selectedWorkspaceDocumentId = createdEntry.document.runtime_id;
      selectedWorkspaceBlock = createdBlock;
      editorContext = { documentId: createdEntry.document.runtime_id, block: createdBlock };
      baselinePayload = { ...profile };
      baselinePayloadKey = payloadKey(profile);
      renderFields();
      showEditor({ locked: true });
      updateDirtyState();
    }
  } catch (error) {
    cadResult.dataset.state = "error";
    cadResult.textContent = t("cad.error", error.message, { message: error.message });
  } finally {
    cadBuildActive = false;
    activeCadJobId = null;
    cadCancelButton.hidden = true;
    cadProgress.hidden = true;
    cadProgressBar.setAttribute("aria-valuenow", "0");
    cadProgressFill.style.width = "0%";
    cadProgressPercent.textContent = "0%";
    cadProgressStage.textContent = "";
    cadProgressTime.textContent = "0:00";
    cadCreateButton.disabled = cadPlanKey !== payloadKey(profile)
      || (Boolean(editorContext) && !currentDirtyState());
  }
}

async function cancelActiveCadJob() {
  if (!activeCadJobId) return;
  cadCancelButton.disabled = true;
  cadProgressStage.textContent = t("cad.cancelling");
  try {
    await requestJson(`/cad/jobs/${activeCadJobId}/cancel`, { method: "POST" });
  } catch (error) {
    cadResult.dataset.state = "error";
    cadResult.textContent = t("cad.error", error.message, { message: error.message });
  } finally {
    cadCancelButton.disabled = false;
  }
}

function updateLanguageButtons() {
  for (const button of languageButtons) {
    const active = button.dataset.language === getLocale();
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
}

function refreshLanguage() {
  applyStaticTranslations();
  updateLanguageButtons();
  renderModuleCatalogText();
  if (currentSpec) {
    customProfileDraft = readCustomProfileDraft();
    const customMode = fieldsContainer.querySelector("[name='designation']")?.value === "CUSTOM";
    localizeFields();
    if (customMode) {
      fieldsContainer.querySelector("[data-custom-profile-editor]")?.replaceWith(createCustomProfileEditor());
    }
  }
  if (lastPreviewResult) renderSummary(lastPreviewResult.summary);
  renderWarnings(displayedWarnings, false);
  if (currentModule) {
    editorModePill.title = t(currentModule.capabilities.build ? "app.managed_cad_title" : "app.preview_only_title");
    editorModeText.textContent = t(currentModule.capabilities.build ? "app.managed_cad" : "app.preview_only");
  }
  refreshStatusLanguage();
  if (workspaceActionActive) updateWorkspaceBusy();
}

async function initialize() {
  applyStaticTranslations();
  updateLanguageButtons();
  try {
    const catalog = await requestJson("/modules");
    moduleCatalog = catalog.items;
    moduleSelect.replaceChildren();
    for (const module of moduleCatalog) {
      const option = document.createElement("option");
      option.value = module.kind;
      option.textContent = moduleName(module);
      moduleSelect.append(option);
    }
    if (!moduleCatalog.length) throw new Error(t("error.no_modules"));
    await selectModule(moduleCatalog[0].kind, false);
    editorShell.hidden = true;
    workspaceShell.hidden = false;
    await refreshWorkspace({ followActive: true });
  } catch (error) {
    setStatus("status.initialization_error", "error", { message: error.message });
    renderWarnings([{ message: error.message }]);
  }
}

moduleSelect.addEventListener("change", async () => {
  if (moduleSelect.disabled) return;
  try {
    await selectModule(moduleSelect.value);
  } catch (error) {
    setStatus("status.error", "error", { message: error.message });
    renderWarnings([{ message: error.message }]);
  }
});
form.addEventListener("input", () => schedulePreview());
form.addEventListener("wheel", (event) => {
  const input = event.target.closest("input[type='number']");
  if (!input || input.disabled || input.readOnly || event.deltaY === 0) return;
  event.preventDefault();

  const configuredStep = Number(input.step);
  const step = Number.isFinite(configuredStep) && configuredStep > 0 ? configuredStep : 1;
  const minimum = Number(input.min);
  const maximum = Number(input.max);
  const current = Number.isFinite(input.valueAsNumber)
    ? input.valueAsNumber
    : (Number.isFinite(minimum) ? minimum : 0);
  let next = current + (event.deltaY < 0 ? step : -step);
  if (Number.isFinite(minimum)) next = Math.max(minimum, next);
  if (Number.isFinite(maximum)) next = Math.min(maximum, next);
  const precision = String(step).split(".")[1]?.length || 0;
  input.value = precision ? next.toFixed(precision) : String(next);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}, { passive: false });
form.addEventListener("change", (event) => {
  if (event.target.name === "designation") {
    customProfileDraft = readCustomProfileDraft();
    syncConditionalFields();
  }
  if (event.target.matches("select, input[type='checkbox']")) schedulePreview({ immediate: true });
});
form.addEventListener("click", (event) => {
  if (event.target.closest("[data-restore-custom]") && customProfileBaseValues) {
    customProfileDraft = { ...customProfileBaseValues };
    fieldsContainer.querySelector("[data-custom-profile-editor]")?.replaceWith(createCustomProfileEditor());
    schedulePreview({ immediate: true });
    return;
  }
  const toggle = event.target.closest("[data-toggle-custom-advanced]");
  if (toggle) {
    const editor = toggle.closest("[data-custom-profile-editor]");
    const expanded = editor.classList.toggle("show-advanced");
    toggle.textContent = t(expanded ? "custom.hide_advanced" : "custom.show_advanced");
  }
});
form.addEventListener("submit", (event) => {
  event.preventDefault();
  runPreview();
});
resetButton.addEventListener("click", () => {
  customProfileDraft = customProfileBaseValues ? { ...customProfileBaseValues } : null;
  renderFields();
  updateDirtyState();
  schedulePreview({ immediate: true });
});
cadCreateButton.addEventListener("click", createManagedPulley);
cadCancelButton.addEventListener("click", cancelActiveCadJob);
workspaceRefreshButton.addEventListener("click", () => refreshWorkspace({ followActive: true }));
workspaceNewButton.addEventListener("click", async () => {
  editorContext = null;
  await selectModule(moduleCatalog[0].kind, true);
  showEditor({ locked: false });
});
workspaceOpenButton.addEventListener("click", async () => {
  setWorkspaceBusy("workspace.choosing_file");
  workspaceStatus.textContent = t("workspace.choosing_file", "Choosing an .m3d file…");
  try {
    const selection = await requestJson("/workspace/pick-file", {
      method: "POST",
    });
    if (selection.cancelled) {
      workspaceStatus.textContent = t("workspace.ready", "KOMPAS documents synchronized");
      return;
    }
    const name = selection.path.split(/[\\/]/).pop();
    workspaceBusyStartedAt = Date.now();
    workspaceBusyDescriptor = { key: "workspace.opening_named", variables: { name } };
    workspaceStatus.textContent = t(
      "workspace.opening_named",
      "Opening and recognizing “{name}” in KOMPAS…",
      { name },
    );
    updateWorkspaceBusy();
    const response = await requestJson("/workspace/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: selection.path }),
    });
    workspaceSnapshot = response.workspace;
    selectedWorkspaceDocumentId = workspaceSnapshot.active_runtime_id;
    workspaceStatus.textContent = t("workspace.ready", "KOMPAS documents synchronized");
    renderWorkspace();
  } catch (error) {
    workspaceStatus.textContent = t("workspace.error", error.message, { message: error.message });
  } finally {
    clearWorkspaceBusy();
  }
});
workspaceEditBlockButton.addEventListener("click", openSelectedBlockEditor);
workspaceCloseDocumentButton.addEventListener("click", () => closeWorkspaceDocument());
workspaceSaveDocumentButton.addEventListener("click", () => saveWorkspaceDocument());
workspaceSaveAsDocumentButton.addEventListener("click", () => saveWorkspaceDocument(undefined, { saveAs: true }));
editorSaveDocumentButton.addEventListener("click", async () => {
  if (!editorContext) return;
  const entry = (workspaceSnapshot?.documents || []).find(
    (item) => item.document.runtime_id === editorContext.documentId,
  );
  if (entry) await saveWorkspaceDocument(entry.document);
});
editorSaveAsDocumentButton.addEventListener("click", async () => {
  if (!editorContext) return;
  const entry = (workspaceSnapshot?.documents || []).find(
    (item) => item.document.runtime_id === editorContext.documentId,
  );
  if (entry) await saveWorkspaceDocument(entry.document, { saveAs: true });
});
editorBackButton.addEventListener("click", showWorkspace);
window.addEventListener("focus", () => {
  if (!workspaceShell.hidden && !cadBuildActive && !workspaceActionActive) {
    refreshWorkspace({ followActive: true });
  }
});
for (const button of languageButtons) {
  button.addEventListener("click", () => setLocale(button.dataset.language));
}
window.addEventListener("geomwright-language", refreshLanguage);

initialize();
