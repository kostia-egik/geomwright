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
const moduleCurrentName = document.querySelector("#module-current-name");
const form = document.querySelector("#preview-form");
const fieldsContainer = document.querySelector("#dynamic-fields");
const resetButton = document.querySelector("#reset-button");
const liveIndicator = document.querySelector("#live-indicator");
const summary = document.querySelector("#summary");
const standardBadge = document.querySelector("#standard-badge");
const warningsSection = document.querySelector("#warnings-section");
const warningsList = document.querySelector("#status-warnings") || document.querySelector("#warnings");
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
const moduleShell = document.querySelector("#module-shell");
const moduleSelectorRows = document.querySelector("#module-selector-rows");
const moduleShellWorkspaceButton = document.querySelector("#module-shell-workspace");
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
const workspaceBlockReadonly = document.querySelector("#workspace-block-readonly");
const workspaceEditBlockButton = document.querySelector("#workspace-edit-block");
const workspaceStatus = document.querySelector("#workspace-status");
const workspaceBusy = document.querySelector("#workspace-busy");
const workspaceBusyText = document.querySelector("#workspace-busy-text");
const workspaceBusyTime = document.querySelector("#workspace-busy-time");
const editorModulesButton = document.querySelector("#editor-modules");
const editorWorkspaceButton = document.querySelector("#editor-workspace");
const editorDocumentActions = document.querySelector("#editor-document-actions");
const editorSaveDocumentButton = document.querySelector("#editor-save-document");
const editorSaveAsDocumentButton = document.querySelector("#editor-save-as-document");
const moduleHeading = document.querySelector("#module-heading");
const editorModePill = document.querySelector("#editor-mode-pill");
const editorModeText = document.querySelector("#editor-mode-text");
const editorTitle = document.querySelector("#editor-shell .topbar h1");
const selectionNote = document.querySelector("#selection-note");

let currentModule = null;
let currentSpec = null;
let moduleCatalog = [];
let selectorGroup = null;
let selectorSubgroup = null;
let camshaftStep = "phases";
let camshaftModuleKind = null;
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
let lastCadPlanReady = null;
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
      : (detail && typeof detail === "object" ? localizeWarning(detail) : detail) || `HTTP ${response.status}`;
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
  // A fixed value belongs to the request, not to the user's choice of inputs.
  if (input.tagName === "SELECT" && input.options.length === 1) wrapper.hidden = true;

  const help = localizedFieldHelp(name, schema);
  if (help) {
    const description = document.createElement("small");
    description.dataset.fieldHelp = "";
    description.textContent = help;
    wrapper.append(description);
  }
  return wrapper;
}

function chainSelectionLabel(level, item) {
  const value = typeof item === "string" ? item : item?.value;
  if (typeof item === "object" && item) {
    const localizedLabel = getLocale() === "ru" ? item.label_ru : item.label_en;
    if (localizedLabel) return localizedLabel;
  }
  return t(`chain.selection.${value}`, humanize(value));
}

function updateChainSelectionDetails() {
  const context = document.createElement("canvas").getContext("2d");
  for (const select of fieldsContainer.querySelectorAll("[data-chain-selection]")) {
    const text = select.selectedOptions[0]?.textContent || "";
    select.title = text;
    const detail = select.parentElement.querySelector("[data-chain-selection-detail]");
    if (!detail) continue;
    detail.textContent = text;
    if (context) context.font = getComputedStyle(select).font;
    detail.hidden = !text || !select.clientWidth || (context && context.measureText(text).width <= select.clientWidth - 40);
  }
}

window.addEventListener("resize", updateChainSelectionDetails);

function createChainProfileSelector() {
  const fieldset = document.createElement("fieldset");
  fieldset.className = "chain-profile-selector";
  fieldset.dataset.chainProfileSelector = "";
  const legend = document.createElement("legend");
  legend.textContent = t(currentModule.kind === "silent_chain_sprocket" ? "silent.selection.title" : "chain.selection.title", "Профиль цепи");
  fieldset.append(legend);

  const standards = currentSpec?.module?.selection?.standards || [];
  const currentDesignation = baselinePayload.designation || currentModule.defaults.designation;
  const selectedStandard = standards.find((standard) => standard.value === baselinePayload.standard)
    || standards.find((standard) => standard.families.some((family) => family.profiles.some((profile) => profile.value === currentDesignation)))
    || standards[0];
  const selectedFamily = selectedStandard?.families.find((family) => family.value === baselinePayload.family)
    || selectedStandard?.families.find((family) => family.profiles.some((profile) => profile.value === currentDesignation))
    || selectedStandard?.families[0];
  const selectors = {};
  for (const level of ["standard", "family", "profile"]) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const heading = document.createElement("span");
    heading.className = "field-heading";
    const title = document.createElement("span");
    title.className = "field-title";
    title.dataset.chainSelectionLabel = level;
    title.textContent = t(`${currentModule.kind === "silent_chain_sprocket" ? "silent" : "chain"}.selection.${level}`, humanize(level));
    heading.append(title);
    wrapper.append(heading);
    const select = document.createElement("select");
    select.dataset.chainSelection = level;
    select.name = `chain_${level}`;
    wrapper.append(select);
    const detail = document.createElement("small");
    detail.className = "chain-selection-detail";
    detail.dataset.chainSelectionDetail = "";
    detail.hidden = true;
    wrapper.append(detail);
    fieldset.append(wrapper);
    selectors[level] = select;
  }
  const hint = document.createElement("p");
  hint.className = "chain-selection-hint";
  hint.dataset.chainSelectionHint = "";
  hint.hidden = true;
  fieldset.append(hint);
  const fill = (select, items, selected, level) => {
    select.replaceChildren();
    for (const item of items || []) {
      const option = document.createElement("option");
      option.value = item.value;
      option.textContent = chainSelectionLabel(level, item);
      if (item.label_ru) option.dataset.chainLabelRu = item.label_ru;
      if (item.label_en) option.dataset.chainLabelEn = item.label_en;
      option.disabled = item.available === false;
      if (level === "profile" && item.chain_type !== undefined) option.dataset.chainType = item.chain_type;
      if (level === "profile" && item.nominal_row_count) option.dataset.nominalRowCount = item.nominal_row_count;
      option.selected = item.value === selected;
      select.append(option);
    }
    select.parentElement.hidden = (items || []).filter(item => item.available !== false).length <= 1;
  };
  const sync = (standardValue, familyValue, profileValue) => {
    const standard = standards.find((item) => item.value === standardValue) || standards[0];
    fill(selectors.standard, standards, standard?.value, "standard");
    const family = standard?.families.find((item) => item.value === familyValue) || standard?.families[0];
    fill(selectors.family, standard?.families, family?.value, "family");
    const profile = family?.profiles.find((item) => item.value === profileValue) || family?.profiles[0];
    fill(selectors.profile, family?.profiles, profile?.value, "profile");
    const standardField = fieldsContainer.querySelector("[name='standard']");
    if (standardField) standardField.value = standard?.value || "";
    const familyField = fieldsContainer.querySelector("[name='family']");
    if (familyField) familyField.value = family?.value || "";
    const typeField = fieldsContainer.querySelector("[name='chain_type']");
    if (profile?.chain_type && typeField) typeField.value = profile.chain_type;
    const rowField = fieldsContainer.querySelector("[name='row_count']");
    if (profile?.nominal_row_count && rowField) rowField.value = profile.nominal_row_count;
    syncSilentToothCount(profile, standard?.value);
    syncConditionalFields();
    requestAnimationFrame(updateChainSelectionDetails);
  };
  sync(selectedStandard?.value, selectedFamily?.value, currentDesignation);
  selectors.standard.addEventListener("change", () => sync(selectors.standard.value, null, null));
  selectors.family.addEventListener("change", () => sync(selectors.standard.value, selectors.family.value, null));
  selectors.profile.addEventListener("change", () => {
    const standard = standards.find((item) => item.value === selectors.standard.value);
    const family = standard?.families.find((item) => item.value === selectors.family.value);
    const standardField = fieldsContainer.querySelector("[name='standard']");
    if (standardField) standardField.value = selectors.standard.value;
    const familyField = fieldsContainer.querySelector("[name='family']");
    if (familyField) familyField.value = selectors.family.value;
    const chainType = selectors.profile.selectedOptions[0]?.dataset.chainType;
    const typeField = fieldsContainer.querySelector("[name='chain_type']");
    if (chainType && typeField) typeField.value = chainType;
    const nominalRowCount = selectors.profile.selectedOptions[0]?.dataset.nominalRowCount;
    const rowField = fieldsContainer.querySelector("[name='row_count']");
    if (nominalRowCount && rowField) rowField.value = nominalRowCount;
    syncSilentToothCount({ chain_type: chainType }, selectors.standard.value);
    syncConditionalFields();
    updateChainSelectionDetails();
  });
  return fieldset;
}

function syncSilentToothCount(profile, standardValue = fieldsContainer.querySelector("[data-chain-selection='standard']")?.value) {
  if (currentModule?.kind !== "silent_chain_sprocket") return;
  const input = fieldsContainer.querySelector("[name='physical_tooth_count']");
  if (!input) return;
  const type = Number(profile?.chain_type || 1);
  if (standardValue === "gost_13552_81_13576_81") {
    input.min = type === 1 ? 17 : 11;
    input.max = type === 1 ? 96 : 48;
  } else {
    input.min = standardValue === "din_8190_8191_open" ? 15 : 17;
    input.max = 114;
  }
  if (input.value && (input.valueAsNumber < Number(input.min) || input.valueAsNumber > Number(input.max))) {
    input.value = input.min;
  }
}

function syncConditionalFields() {
  const gostVariantWrapper = fieldsContainer.querySelector("[data-field-name='gost_profile_variant']");
  if (gostVariantWrapper) {
    const applies = currentModule?.kind === "chain_sprocket";
    const input = gostVariantWrapper.querySelector("input, select, textarea");
    gostVariantWrapper.hidden = !applies;
    if (input) input.disabled = !applies;
  }
  if (currentModule?.kind === "silent_chain_sprocket") {
    const standardValue = fieldsContainer.querySelector("[data-chain-selection='standard']")?.value;
    const familyValue = fieldsContainer.querySelector("[data-chain-selection='family']")?.value;
    const toothHelp = fieldsContainer.querySelector("[data-field-name='physical_tooth_count'] [data-field-help]");
    if (toothHelp) {
      const helpKey = standardValue === "gost_13552_81_13576_81"
        ? `silent.tooth_count.${familyValue === "type_2" ? "gost_2" : "gost_1"}`
        : standardValue === "din_8190_8191_open" ? "silent.tooth_count.din" : "silent.tooth_count.asme";
      toothHelp.textContent = t(helpKey);
    }
    const accuracy = fieldsContainer.querySelector("[data-field-name='accuracy_class']");
    if (accuracy) {
      const applies = standardValue === "gost_13552_81_13576_81";
      accuracy.hidden = !applies;
      const control = accuracy.querySelector("input, select, textarea");
      if (control) control.disabled = !applies;
    }
    const faceWidth = fieldsContainer.querySelector("[data-field-name='face_width_mm']");
    if (faceWidth) faceWidth.hidden = standardValue !== "asme_b29_2m_open";
    const tipShape = fieldsContainer.querySelector("[data-field-name='tooth_tip_shape']");
    const standard = currentSpec?.module?.selection?.standards?.find((item) => item.value === standardValue);
    const family = standard?.families.find((item) => item.value === familyValue);
    const profileValue = fieldsContainer.querySelector("[data-chain-selection='profile']")?.value;
    const profile = family?.profiles.find((item) => item.value === profileValue);
    const asme = standardValue === "asme_b29_2m_open";
    const axialSource = fieldsContainer.querySelector("[data-field-name='axial_source']");
    if (axialSource) axialSource.hidden = !asme;
    const gbAxial = axialSource?.querySelector("select")?.value === "gb_10855_2016";
    const smallPitch = asme && Number(profile?.pitch_mm) === 4.7625;
    if (tipShape) tipShape.hidden = !asme || smallPitch;
    const hint = fieldsContainer.querySelector("[data-chain-selection-hint]");
    if (hint) {
      const missingAxial = asme && ((smallPitch && profile?.chain_type === "two_center_guide")
        || (!gbAxial && Number(profile?.pitch_mm) === 31.75 && ["center_guide", "two_center_guide"].includes(profile?.chain_type))
        || (gbAxial && Number(profile?.pitch_mm) > 12.7 && profile?.chain_type === "side_guide"));
      hint.textContent = [smallPitch ? t("silent.small_pitch_tip_hint") : "", missingAxial ? t("silent.missing_axial_hint") : ""].filter(Boolean).join(" ");
      hint.hidden = !hint.textContent;
    }
    selectionNote.textContent = getLocale() === "ru"
      ? (standard?.warning_ru || t("silent.preview_note_gost"))
      : (standard?.warning_en || t("silent.preview_note_gost"));
  }
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

function createCamshaftFieldsPanel(names) {
  const panel = document.createElement("div");
  panel.className = "camshaft-fields";
  const properties = currentSpec.schema.properties || {};
  const required = new Set(currentSpec.schema.required || []);
  for (const name of names) {
    if (properties[name]) panel.append(createField(name, properties[name], required.has(name)));
  }
  return panel;
}

function createCamshaftPhaseFields() {
  const layout = document.createElement("div");
  layout.className = "camshaft-layout";
  const properties = currentSpec.schema.properties || {};
  const required = new Set(currentSpec.schema.required || []);
  if (properties.active_lobe) {
    const activeField = createField("active_lobe", properties.active_lobe, required.has("active_lobe"));
    activeField.classList.add("camshaft-active");
    layout.append(activeField);
  }
  const columns = document.createElement("div");
  columns.className = "camshaft-columns";
  const groups = [
    {
      tone: "intake",
      legendKey: "camshaft.column.intake",
      legend: "Впуск",
      fields: ["intake_open_deg", "intake_close_deg"],
    },
    {
      tone: "exhaust",
      legendKey: "camshaft.column.exhaust",
      legend: "Выпуск",
      fields: ["exhaust_open_deg", "exhaust_close_deg"],
    },
  ];
  for (const group of groups) {
    const fieldset = document.createElement("fieldset");
    fieldset.className = "camshaft-column";
    fieldset.dataset.tone = group.tone;
    const legend = document.createElement("legend");
    legend.textContent = t(group.legendKey, group.legend);
    legend.dataset.i18n = group.legendKey;
    fieldset.append(legend);
    for (const name of group.fields) {
      if (properties[name]) fieldset.append(createField(name, properties[name], required.has(name)));
    }
    columns.append(fieldset);
  }
  layout.append(columns);
  return layout;
}

function createCamshaftWizard() {
  const wizard = document.createElement("div");
  wizard.className = "camshaft-wizard";

  const stepInput = document.createElement("input");
  stepInput.type = "hidden";
  stepInput.name = "step";
  stepInput.dataset.schemaType = "string";
  stepInput.value = camshaftStep;

  const steps = [
    { key: "phases", labelKey: "camshaft.step.phases", label: "Фазы" },
    { key: "kinematics", labelKey: "camshaft.step.kinematics", label: "Кинематика" },
    { key: "cam", labelKey: "camshaft.step.cam", label: "Кулачок" },
  ];
  const content = {
    phases: createCamshaftPhaseFields(),
    kinematics: createCamshaftKinematicsFields(),
    cam: createCamshaftFieldGroups([
      {
        key: "law",
        legendKey: "camshaft.group.law",
        legend: "Закон движения",
        fields: ["law"],
      },
      {
        key: "curvature",
        legendKey: "camshaft.group.curvature",
        legend: "Кривизна профиля",
        fields: ["min_curvature_radius", "nose_radius"],
      },
      {
        key: "limits",
        legendKey: "camshaft.group.limits",
        legend: "Ограничения движения",
        fields: ["max_acceleration", "max_jerk"],
      },
      {
        key: "ramps",
        legendKey: "camshaft.group.ramps",
        legend: "Подъём и рампы",
        fields: ["max_lift", "ramp_open_deg", "ramp_close_deg"],
      },
      {
        key: "cad",
        legendKey: "camshaft.group.cad",
        legend: "CAD: один кулачок",
        fields: ["cam_width", "cam_rotation_deg", "cad_tolerance"],
      },
    ]),
  };

  const nav = document.createElement("div");
  nav.className = "camshaft-steps";
  const buttons = {};
  const panels = {};
  for (const step of steps) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "camshaft-step-button";
    button.textContent = t(step.labelKey, step.label);
    button.dataset.i18n = step.labelKey;
    button.addEventListener("click", () => {
      camshaftStep = step.key;
      applyStep();
    });
    buttons[step.key] = button;
    nav.append(button);

    const panel = document.createElement("div");
    panel.className = "camshaft-panel";
    panel.dataset.step = step.key;
    panel.append(content[step.key]);
    panels[step.key] = panel;
  }

  function applyStep(trigger = true) {
    stepInput.value = camshaftStep;
    document.querySelector(".cad-controls").hidden = camshaftStep !== "cam";
    cadPlanKey = null;
    cadCreateButton.disabled = true;
    if (camshaftStep !== "cam") window.dispatchEvent(new Event("geomwright-cam-motion-reset"));
    for (const step of steps) {
      panels[step.key].hidden = step.key !== camshaftStep;
      buttons[step.key].classList.toggle("selected", step.key === camshaftStep);
      buttons[step.key].setAttribute("aria-pressed", String(step.key === camshaftStep));
    }
    if (trigger) runPreview({ force: true });
  }

  wizard.append(stepInput, nav);
  for (const step of steps) wizard.append(panels[step.key]);
  const syncProfile = () => {
    const direct = wizard.querySelector("[name='mechanism']")?.value === "direct";
    const law = wizard.querySelector("[name='law']");
    const curvature = wizard.querySelector("[data-group='curvature']");
    if (curvature) curvature.hidden = !["curvature_spline", "motion_spline", "bounded_auto"].includes(law?.value);
    const nose = wizard.querySelector("[data-field-name='nose_radius']");
    if (nose) nose.hidden = !direct || law?.value !== "curvature_spline";
    const contextualOption = law?.querySelector("option[value='curvature_spline']");
    if (contextualOption) contextualOption.disabled = !direct;
  };
  wizard.querySelector("[name='law']")?.addEventListener("change", syncProfile);
  wizard.querySelector("[name='mechanism']")?.addEventListener("change", syncProfile);
  syncProfile();
  applyStep(false);
  return wizard;
}

function createCamshaftFieldGroups(groups) {
  const layout = document.createElement("div");
  layout.className = "camshaft-groups";
  const properties = currentSpec.schema.properties || {};
  const required = new Set(currentSpec.schema.required || []);
  for (const group of groups) {
    const fieldset = document.createElement("fieldset");
    fieldset.className = "camshaft-group";
    fieldset.dataset.group = group.key;
    const legend = document.createElement("legend");
    legend.textContent = t(group.legendKey, group.legend);
    legend.dataset.i18n = group.legendKey;
    const body = document.createElement("div");
    body.className = "camshaft-fields";
    for (const name of group.fields) {
      if (properties[name]) body.append(createField(name, properties[name], required.has(name)));
    }
    fieldset.append(legend, body);
    layout.append(fieldset);
  }
  return layout;
}

function createCamshaftKinematicsFields() {
  const panel = createCamshaftFieldGroups([
    {
      key: "mechanism",
      legendKey: "camshaft.group.mechanism",
      legend: "Механизм",
      fields: ["mechanism", "base_diameter", "lash", "tappet_diameter", "tappet_edge_margin"],
    },
    {
      key: "cam",
      legendKey: "camshaft.group.cam",
      legend: "Кулачок",
      fields: ["cam_x", "cam_y", "offset"],
    },
    {
      key: "valve",
      legendKey: "camshaft.group.valve",
      legend: "Клапан",
      fields: ["valve_tip_x", "valve_tip_y", "valve_pad_radius"],
    },
    {
      key: "roller",
      legendKey: "camshaft.group.roller",
      legend: "Ролик",
      fields: ["roller_arm", "roller_radius"],
    },
  ]);
  const update = () => {
    const mechanism = panel.querySelector("[name='mechanism']")?.value || "rocker";
    const rocker = mechanism === "rocker";
    const show = (name, visible) => {
      const element = panel.querySelector(`[data-field-name='${name}']`);
      if (element) element.hidden = !visible;
    };
    show("offset", !rocker);
    show("tappet_diameter", !rocker);
    show("tappet_edge_margin", !rocker);
    for (const name of ["cam_x", "cam_y", "roller_arm", "valve_tip_x", "valve_tip_y", "valve_pad_radius", "roller_radius"]) {
      show(name, rocker);
    }
    for (const fieldset of panel.querySelectorAll(".camshaft-group")) {
      const fields = Array.from(fieldset.querySelectorAll("[data-field-name]"));
      fieldset.hidden = !fields.some((field) => !field.hidden);
    }
  };
  panel.querySelector("[name='mechanism']")?.addEventListener("change", () => {
    update();
    runPreview({ force: true });
  });
  update();
  return panel;
}


function gearSelectionMetadata() {
  return currentModule?.selection || {};
}

function gearStandardMetadata(value) {
  return (gearSelectionMetadata().standards || []).find((item) => item.value === value) || null;
}

function createGearModuleSelect(currentValue, moduleSystem, rangeMeta = {}) {
  const select = document.createElement("select");
  select.name = "module_mm";
  select.dataset.schemaType = "number";
  const catalog = gearSelectionMetadata().module_rows || {};
  const rows = catalog[moduleSystem] || catalog[Object.keys(catalog)[0]] || {};
  const min = rangeMeta.min ?? null;
  const max = rangeMeta.max ?? null;
  const exclusive = Boolean(rangeMeta.exclusive);
  const inRange = (value) => {
    if (min != null && value < min - 1e-9) return false;
    if (max != null) {
      if (exclusive ? value >= max - 1e-9 : value > max + 1e-9) return false;
    }
    return true;
  };
  const avoidValues = new Set((rows.avoid || []).map(Number));
  const groups = [
    { key: "row_1", labelKey: "gear.module_row_1" },
    { key: "row_2", labelKey: "gear.module_row_2" },
    { key: "exceptions", labelKey: "gear.module_exceptions" },
  ];
  const available = [];
  for (const group of groups) {
    const values = (rows[group.key] || []).map(Number).filter(inRange);
    if (!values.length) continue;
    available.push(...values);
    const optgroup = document.createElement("optgroup");
    optgroup.label = t(group.labelKey, humanize(group.key));
    for (const value of values) {
      const option = document.createElement("option");
      option.value = String(value);
      option.dataset.rawValue = String(value);
      if (avoidValues.has(value)) option.dataset.avoid = "true";
      option.textContent = formatNumber(value, 6)
        + (avoidValues.has(value) ? ` · ${t("gear.module_avoid", "не рекомендуется")}` : "");
      optgroup.append(option);
    }
    select.append(optgroup);
  }
  const numericCurrent = Number(currentValue);
  if (available.length) {
    const match = Number.isFinite(numericCurrent)
      ? available.find((value) => Math.abs(value - numericCurrent) <= 1e-9)
      : undefined;
    const chosen = match != null
      ? match
      : available.reduce(
        (best, value) => (
          Math.abs(value - numericCurrent) < Math.abs(best - numericCurrent) ? value : best
        ),
        available[0],
      );
    select.value = String(chosen);
  } else if (Number.isFinite(numericCurrent)) {
    const option = document.createElement("option");
    option.value = String(numericCurrent);
    option.dataset.rawValue = String(numericCurrent);
    option.textContent = formatNumber(numericCurrent, 6);
    select.append(option);
    select.value = String(numericCurrent);
  }
  return select;
}

function createGearStandardSelect(currentValue) {
  const select = document.createElement("select");
  select.name = "standard";
  select.dataset.schemaType = "string";
  for (const item of gearSelectionMetadata().standards || []) {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = (getLocale() === "ru" ? item.label_ru : item.label_en) || item.value;
    option.title = (getLocale() === "ru" ? item.scope_ru : item.scope_en) || item.edition || "";
    option.selected = item.value === currentValue;
    select.append(option);
  }
  return select;
}

function createGearModificationSelect(currentValue, standardValue) {
  const select = document.createElement("select");
  select.name = "modification";
  select.dataset.schemaType = "string";
  const system = gearStandardMetadata(standardValue || "gost_13755_2015");
  for (const item of system?.modifications || []) {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = t(`enum.modification.${item.value}`, (getLocale() === "ru" ? item.label_ru : item.label_en) || item.value);
    option.selected = item.value === currentValue;
    select.append(option);
  }
  return select;
}

function createGearPinList() {
  const list = document.createElement("datalist");
  list.id = "gear-pin-diameters";
  const seen = new Set();
  for (const source of gearSelectionMetadata().pin_sources || []) {
    for (const value of source.diameters || []) {
      const key = String(value);
      if (seen.has(key)) continue;
      seen.add(key);
      const option = document.createElement("option");
      option.value = key;
      option.label = getLocale() === "ru" ? source.label_ru : source.label_en;
      list.append(option);
    }
  }
  return list;
}

function gearEffectiveRange(standardMeta, modificationMeta) {
  const override = Boolean(
    modificationMeta
    && (modificationMeta.module_min != null || modificationMeta.module_max != null)
  );
  return {
    min: override ? modificationMeta.module_min : (standardMeta?.module_min ?? null),
    max: override ? modificationMeta.module_max : (standardMeta?.module_max ?? null),
    exclusive: override
      ? Boolean(modificationMeta.module_max_exclusive)
      : Boolean(standardMeta?.module_max_exclusive),
  };
}

function formatGearRange(range) {
  if (!range || (range.min == null && range.max == null)) return "";
  const minText = range.min == null ? "" : formatNumber(range.min, 6);
  const maxText = range.max == null ? "" : formatNumber(range.max, 6);
  let text;
  if (range.min == null) text = `≤ ${maxText}`;
  else if (range.max == null) text = `≥ ${minText}`;
  else text = `${minText}…${maxText}`;
  if (range.exclusive && range.max != null) {
    text += ` (${t("gear.range_excluding", "не включая {value}", { value: maxText })})`;
  }
  return text;
}

function gearCoefficientSummary(modificationMeta) {
  if (!modificationMeta) return "";
  if (modificationMeta.value === "custom") {
    return t("gear.custom_coefficients", "Пользовательские коэффициенты контура");
  }
  const parts = [];
  if (modificationMeta.pressure_angle_deg != null) {
    parts.push(`α=${formatNumber(modificationMeta.pressure_angle_deg, 3)}°`);
  }
  if (modificationMeta.addendum_coefficient != null) {
    parts.push(`h*ₐ=${formatNumber(modificationMeta.addendum_coefficient, 3)}`);
  }
  if (modificationMeta.clearance_coefficient != null) {
    parts.push(`c*=${formatNumber(modificationMeta.clearance_coefficient, 5)}`);
  }
  parts.push(
    modificationMeta.root_fillet_coefficient != null
      ? `ρ_f*=${formatNumber(modificationMeta.root_fillet_coefficient, 5)}`
      : t("gear.fillet_not_tabulated", "ρ_f* не нормирован"),
  );
  return parts.join(" · ");
}

function refreshGearDynamicText() {
  if (!["gear_spur", "gear_internal", "gear_bevel"].includes(currentModule?.kind) || !currentSpec) return;
  const standardSelect = fieldsContainer.querySelector("select[name='standard']");
  const modificationSelect = fieldsContainer.querySelector("select[name='modification']");
  const moduleSelect = fieldsContainer.querySelector("[data-field-name='module_mm'] select");
  const standardMeta = gearStandardMetadata(standardSelect?.value);
  const locale = getLocale();
  for (const option of standardSelect?.options || []) {
    const item = gearStandardMetadata(option.value);
    if (!item) continue;
    option.textContent = (locale === "ru" ? item.label_ru : item.label_en) || item.value;
    option.title = (locale === "ru" ? item.scope_ru : item.scope_en) || item.edition || "";
  }
  for (const option of modificationSelect?.options || []) {
    const item = standardMeta?.modifications.find((modification) => modification.value === option.value);
    option.textContent = t(
      `enum.modification.${option.value}`,
      (locale === "ru" ? item?.label_ru : item?.label_en) || option.value,
    );
  }
  for (const option of moduleSelect?.options || []) {
    const raw = option.dataset.rawValue;
    if (raw == null) continue;
    option.textContent = formatNumber(Number(raw), 6)
      + (option.dataset.avoid === "true" ? ` · ${t("gear.module_avoid", "не рекомендуется")}` : "");
  }
  const standardHelp = fieldsContainer.querySelector("[data-gear-standard-help]");
  if (standardHelp) {
    const scope = (locale === "ru" ? standardMeta?.scope_ru : standardMeta?.scope_en) || "";
    const edition = standardMeta?.edition
      ? t("gear.help_edition", "Редакция: {value}", { value: standardMeta.edition })
      : "";
    const range = formatGearRange(gearEffectiveRange(standardMeta, null));
    standardHelp.textContent = [
      scope,
      edition,
      range ? t("gear.help_module", "Модуль: {value}", { value: range }) : "",
    ].filter(Boolean).join(" · ");
  }
  const moduleHelp = fieldsContainer.querySelector("[data-gear-module-help]");
  if (moduleHelp) {
    const rowsEdition = gearSelectionMetadata().module_rows?.[standardMeta?.module_system]?.edition || "";
    moduleHelp.textContent = rowsEdition
      ? t("gear.help_module_rows", "Ряды: {value}", { value: rowsEdition })
      : "";
  }
  const modificationHelp = fieldsContainer.querySelector("[data-gear-modification-help]");
  if (modificationHelp) {
    const modificationMeta = standardMeta?.modifications.find(
      (item) => item.value === modificationSelect?.value,
    ) || null;
    const range = formatGearRange(gearEffectiveRange(standardMeta, modificationMeta));
    const standardRange = formatGearRange(gearEffectiveRange(standardMeta, null));
    const coefficients = gearCoefficientSummary(modificationMeta);
    modificationHelp.textContent = [
      coefficients,
      range && range !== standardRange
        ? t("gear.help_module", "Модуль: {value}", { value: range })
        : "",
    ].filter(Boolean).join(" · ");
  }
}

function createGearFieldGroup(key, legendKey, fallback, { collapsible = false, open = false } = {}) {
  const root = document.createElement(collapsible ? "details" : "fieldset");
  root.className = collapsible ? "gear-group gear-collapsible" : "gear-group";
  root.dataset.gearGroup = key;
  const title = document.createElement(collapsible ? "summary" : "legend");
  title.dataset.i18n = legendKey;
  title.textContent = t(legendKey, fallback);
  const body = document.createElement("div");
  body.className = "gear-fields";
  root.append(title, body);
  if (collapsible) root.open = open;
  return { root, body };
}

function createGearFields() {
  const isBevel = currentModule?.kind === "gear_bevel";
  const properties = currentSpec.schema.properties || {};
  const required = new Set(currentSpec.schema.required || []);
  // Blocks follow the operator's importance order: what defines the gear,
  // how the tooth runs, the main dimensions, then the secondary groups.
  // Derived coefficients and the over-pin pin are collapsed while they are
  // not in play. Each block uses the thin gray frame of the chain selector.
  const groups = {
    standard: createGearFieldGroup("standard", "gear.group.standard_modification", "Стандарт и модификация"),
    tooth: createGearFieldGroup("tooth", "gear.group.tooth", "Направление и угол зуба"),
    main: createGearFieldGroup("main", "gear.group.main", "Основные параметры"),
    coefficients: createGearFieldGroup("coefficients", "gear.group.coefficients", "Производные коэффициенты", { collapsible: true }),
    chamfer: createGearFieldGroup("chamfer", "gear.group.chamfer", "Фаска"),
    measurement: createGearFieldGroup("measurement", "gear.group.measurement", "Измерение по роликам", { collapsible: true }),
  };
  const append = (group, element) => group.body.append(element);
  const standardField = createField("standard", properties.standard, required.has("standard"));
  const modificationField = createField("modification", properties.modification, required.has("modification"));
  const standardInput = standardField.querySelector("input, select");
  if (standardInput && standardInput.tagName !== "SELECT") {
    standardField.replaceChild(createGearStandardSelect(standardInput.value), standardInput);
  }
  const modificationInput = modificationField.querySelector("input, select");
  if (modificationInput && modificationInput.tagName !== "SELECT") {
    modificationField.replaceChild(createGearModificationSelect(modificationInput.value, standardInput?.value), modificationInput);
  }
  standardField.querySelector("[data-field-help]")?.remove();
  const standardHelp = document.createElement("small");
  standardHelp.dataset.gearStandardHelp = "";
  standardField.append(standardHelp);
  modificationField.querySelector("[data-field-help]")?.remove();
  const modificationHelp = document.createElement("small");
  modificationHelp.dataset.gearModificationHelp = "";
  modificationField.append(modificationHelp);
  const moduleField = createField("module_mm", properties.module_mm, required.has("module_mm"));
  moduleField.querySelector("[data-field-help]")?.remove();
  const moduleHelpElement = document.createElement("small");
  moduleHelpElement.dataset.gearModuleHelp = "";
  moduleField.append(moduleHelpElement);
  const moduleNumber = moduleField.querySelector("input");
  const coefficientNames = ["pressure_angle_deg", "addendum_coefficient", "clearance_coefficient", "root_fillet_coefficient"];
  const coefficientFields = {};
  for (const name of coefficientNames) {
    coefficientFields[name] = createField(name, properties[name], required.has(name));
  }
  const note = document.createElement("p");
  note.className = "gear-note";
  note.dataset.gearNote = "";
  note.dataset.i18n = "gear.standard_note";

  append(groups.standard, standardField);
  append(groups.standard, modificationField);
  append(groups.main, moduleField);
  append(groups.main, createField("tooth_count", properties.tooth_count, required.has("tooth_count")));
  if (isBevel) {
    append(groups.main, createField(
      "pitch_cone_angle_deg",
      properties.pitch_cone_angle_deg,
      required.has("pitch_cone_angle_deg"),
    ));
  }
  append(groups.main, createField("profile_shift", properties.profile_shift, required.has("profile_shift")));
  const faceWidthField = createField("face_width_mm", properties.face_width_mm, required.has("face_width_mm"));
  if (currentModule?.kind === "gear_internal") {
    const faceWidthHelp = faceWidthField.querySelector("[data-field-help]");
    if (faceWidthHelp) {
      faceWidthHelp.dataset.i18n = "field.face_width_mm.help_internal";
      faceWidthHelp.textContent = t(
        "field.face_width_mm.help_internal",
        "Функциональная ширина зубчатого венца; расточка на диаметр вершин входит в модуль.",
      );
    }
  } else if (isBevel) {
    const faceWidthHelp = faceWidthField.querySelector("[data-field-help]");
    if (faceWidthHelp) {
      faceWidthHelp.dataset.i18n = "field.face_width_mm.help_bevel";
      faceWidthHelp.textContent = t(
        "field.face_width_mm.help_bevel",
        "Ширина венца вдоль делительного конуса; пусто — рекомендация ГОСТ 19624-74 b = 0,285 R_e.",
      );
    }
  }
  append(groups.main, faceWidthField);
  if (properties.ring_outside_diameter_mm) {
    append(groups.main, createField(
      "ring_outside_diameter_mm",
      properties.ring_outside_diameter_mm,
      required.has("ring_outside_diameter_mm"),
    ));
  }
  let applyToothType = () => {};
  if (isBevel) {
    const typeField = createField("tooth_type", properties.tooth_type, required.has("tooth_type"));
    const typeSelect = typeField.querySelector("select");
    typeSelect.removeAttribute("name");
    typeSelect.dataset.gearToothType = "";
    const typeCode = typeField.querySelector("code");
    if (typeCode) typeCode.textContent = "tooth_type";
    typeSelect.replaceChildren();
    for (const [value, key, fallback, disabled] of [
      ["straight", "gear.tooth_straight", "Прямозубая", false],
      ["circular", "gear.tooth_circular_next", "С круговым зубом · следующий этап", true],
    ]) {
      const option = document.createElement("option");
      option.value = value;
      option.dataset.i18n = key;
      option.textContent = t(key, fallback);
      option.disabled = disabled;
      typeSelect.append(option);
    }
    const bevelTypeNote = document.createElement("small");
    bevelTypeNote.dataset.i18n = "gear.bevel_type_note";
    bevelTypeNote.textContent = t(
      "gear.bevel_type_note",
      "Первый этап реализует прямозубую модификацию; круговой зуб получит отдельную именованную методику.",
    );
    typeField.append(bevelTypeNote);
    append(groups.tooth, typeField);
  } else {
    const typeField = createField("hand", properties.hand, required.has("hand"));
    const typeSelect = typeField.querySelector("select");
    typeSelect.removeAttribute("name");
    typeSelect.dataset.gearToothType = "";
    const typeCode = typeField.querySelector("code");
    if (typeCode) typeCode.textContent = "tooth_type";
    typeSelect.replaceChildren();
    for (const [value, key, fallback] of [
      ["spur", "gear.tooth_spur", "Прямозубая"],
      ["right", "gear.tooth_right", "Правое направление"],
      ["left", "gear.tooth_left", "Левое направление"],
    ]) {
      const option = document.createElement("option");
      option.value = value;
      option.dataset.i18n = key;
      option.textContent = t(key, fallback);
      typeSelect.append(option);
    }
    const initialHand = baselinePayload.hand === "left" ? "left" : "right";
    const initialHelix = Number(baselinePayload.helix_angle_deg || 0);
    typeSelect.value = initialHelix > 1e-9 ? initialHand : "spur";
    const helixField = createField("helix_angle_deg", properties.helix_angle_deg, required.has("helix_angle_deg"));
    const helixNumber = helixField.querySelector("input");
    applyToothType = () => {
      const spur = typeSelect.value === "spur";
      helixNumber.disabled = spur;
      helixField.classList.toggle("derived", spur);
      let hint = helixField.querySelector("[data-gear-angle-hint]");
      if (spur) {
        if (!hint) {
          hint = document.createElement("small");
          hint.dataset.gearAngleHint = "";
          hint.dataset.i18n = "gear.angle_spur_hint";
          helixField.append(hint);
        }
        hint.textContent = t("gear.angle_spur_hint", "Для прямозубого колеса угол не задаётся");
        return;
      }
      if (hint) hint.remove();
      if (!(Number(helixNumber.value) > 0)) {
        helixNumber.value = String(initialHelix > 0 ? initialHelix : 20);
      }
    };
    typeSelect.addEventListener("change", applyToothType);
    append(groups.tooth, typeField);
    append(groups.tooth, helixField);
  }
  append(groups.coefficients, note);
  for (const name of coefficientNames) append(groups.coefficients, coefficientFields[name]);
  if (isBevel) {
    delete groups.measurement;
  } else {
  const pinField = createField("pin_diameter_mm", properties.pin_diameter_mm, required.has("pin_diameter_mm"));
  const pinNumber = pinField.querySelector("input");
  pinNumber.setAttribute("list", "gear-pin-diameters");
  const pinMode = document.createElement("select");
  pinMode.dataset.customProfileField = "pin_mode";
  for (const [value, key, fallback] of [
    ["auto", "gear.pin_auto", "Автоматически (стандартный ролик)"],
    ["custom", "gear.pin_custom", "Пользовательский размер…"],
  ]) {
    const option = document.createElement("option");
    option.value = value;
    option.dataset.i18n = key;
    option.textContent = t(key, fallback);
    pinMode.append(option);
  }
  const initialPin = baselinePayload.pin_diameter_mm;
  pinMode.value = initialPin != null ? "custom" : "auto";
  pinField.insertBefore(pinMode, pinNumber);
  const pinNote = document.createElement("small");
  pinNote.dataset.i18n = "gear.pin_note";
  pinNote.textContent = t(
    "gear.pin_note",
    "Пусто — ближайший стандартный ролик из кэшированных рядов, который помещается под вершинами. Диаметр влияет только на измерение по роликам.",
  );
  pinField.append(pinNote, createGearPinList());
  const applyPinMode = () => {
    const custom = pinMode.value === "custom";
    pinNumber.disabled = !custom;
    pinNumber.hidden = !custom;
    pinNumber.required = custom;
    if (custom && !pinNumber.value.trim() && initialPin != null) {
      pinNumber.value = String(initialPin);
    }
  };
  pinMode.addEventListener("change", applyPinMode);
  append(groups.measurement, pinField);
  applyPinMode();
  // A stored explicit pin is unusual enough that the block opens to show it.
  groups.measurement.root.open = initialPin != null;
  }

  if (properties.tip_chamfer_mm) {
    const chamferField = createField("tip_chamfer_mm", properties.tip_chamfer_mm, required.has("tip_chamfer_mm"));
    const chamferAngleField = createField("tip_chamfer_angle_deg", properties.tip_chamfer_angle_deg, required.has("tip_chamfer_angle_deg"));
    const chamferNumber = chamferField.querySelector("input");
    const chamferAngleNumber = chamferAngleField.querySelector("input");
    const chamferNote = document.createElement("small");
    chamferNote.dataset.i18n = "gear.chamfer_off";
    chamferField.append(chamferNote);
    const applyChamferFields = () => {
      const enabled = Number(chamferNumber.value) > 0;
      chamferAngleNumber.disabled = !enabled;
      chamferAngleField.classList.toggle("derived", !enabled);
      chamferNote.textContent = enabled
        ? t("gear.chamfer_note", "Фаска по обоим торцам зубьев; угол — к торцовой плоскости")
        : t("gear.chamfer_off", "0 — без фаски");
    };
    chamferNumber.addEventListener("input", applyChamferFields);
    append(groups.chamfer, chamferField);
    append(groups.chamfer, chamferAngleField);
    applyChamferFields();
  } else {
    delete groups.chamfer;
  }

  const standardSelect = standardField.querySelector("select");
  let modificationSelect = modificationField.querySelector("select");

  function modificationMetadata() {
    const system = gearStandardMetadata(standardSelect.value);
    return system?.modifications.find((item) => item.value === modificationSelect.value) || null;
  }

  function applyModuleField(meta) {
    const custom = modificationSelect.value === "custom";
    const standardMeta = gearStandardMetadata(standardSelect.value);
    const moduleSystem = standardMeta?.module_system;
    const range = gearEffectiveRange(standardMeta, meta);
    const moduleSelect = moduleField.querySelector("select[name='module_mm']");
    if (custom) {
      if (moduleSelect) {
        moduleNumber.value = moduleSelect.value;
        moduleField.replaceChild(moduleNumber, moduleSelect);
      }
      moduleNumber.disabled = false;
      return;
    }
    if (!moduleSelect) {
      moduleField.replaceChild(
        createGearModuleSelect(moduleNumber.value, moduleSystem, range), moduleNumber);
    } else {
      moduleField.replaceChild(
        createGearModuleSelect(moduleSelect.value, moduleSystem, range), moduleSelect);
    }
  }

  function applyCoefficientFields(meta) {
    const custom = modificationSelect.value === "custom";
    for (const name of coefficientNames) {
      const wrapper = coefficientFields[name];
      const input = wrapper.querySelector("input");
      input.disabled = !custom;
      wrapper.classList.toggle("derived", !custom);
      const derived = meta ? meta[name] : null;
      if (!custom) {
        input.value = derived != null ? String(derived) : "";
      }
      let hint = wrapper.querySelector("[data-gear-derived-hint]");
      if (!custom) {
        if (!hint) {
          hint = document.createElement("small");
          hint.dataset.gearDerivedHint = "";
          wrapper.append(hint);
        }
        hint.dataset.i18n = derived != null ? "gear.derived_from_standard" : "gear.derived_not_tabulated";
        hint.textContent = derived != null
          ? t("gear.derived_from_standard", "Автоматически из стандарта")
          : t("gear.derived_not_tabulated", "Не нормирован для этой модификации");
      } else if (hint) {
        hint.remove();
      }
    }
  }

  function syncGearFields() {
    const meta = modificationMetadata();
    applyModuleField(meta);
    applyCoefficientFields(meta);
    applyToothType();
    groups.coefficients.root.open = modificationSelect.value === "custom";
    note.textContent = t(
      "gear.standard_note",
      "Коэффициенты контура берутся из выбранного стандарта и модификации. Для прямого ввода выберите пользовательскую модификацию.",
    );
    note.hidden = modificationSelect.value === "custom";
    refreshGearDynamicText();
  }

  standardSelect.addEventListener("change", () => {
    const system = gearStandardMetadata(standardSelect.value);
    const keeps = system?.modifications.some((item) => item.value === modificationSelect.value);
    const nextValue = keeps
      ? modificationSelect.value
      : (system?.modifications?.[0]?.value || "a");
    const nextSelect = createGearModificationSelect(nextValue, standardSelect.value);
    nextSelect.addEventListener("change", syncGearFields);
    modificationField.replaceChild(nextSelect, modificationSelect);
    modificationSelect = nextSelect;
    syncGearFields();
  });
  modificationSelect.addEventListener("change", syncGearFields);

  const layout = document.createElement("div");
  layout.className = "gear-groups";
  for (const { root } of Object.values(groups)) layout.append(root);
  fieldsContainer.append(layout);
  syncGearFields();
}


function renderFields() {
  fieldsContainer.replaceChildren();
  const properties = currentSpec.schema.properties || {};
  const required = new Set(currentSpec.schema.required || []);
  if (currentModule?.kind === "camshaft_lobe") {
    if (camshaftModuleKind !== currentModule.kind) {
      camshaftStep = "phases";
      camshaftModuleKind = currentModule.kind;
    }
    fieldsContainer.append(createCamshaftWizard());
    return;
  }
  if (["gear_spur", "gear_internal", "gear_bevel"].includes(currentModule?.kind)) {
    createGearFields();
    syncConditionalFields();
    return;
  }
  if (["chain_sprocket", "silent_chain_sprocket"].includes(currentModule?.kind)) fieldsContainer.append(createChainProfileSelector());
  for (const [name, schema] of Object.entries(properties)) {
    if (name === "custom_profile" || name === "profile_overrides") continue;
    if (currentModule?.kind === "silent_chain_sprocket" && ["standard", "family"].includes(name)) continue;
    if (["chain_sprocket", "silent_chain_sprocket"].includes(currentModule?.kind) && name === "designation") continue;
    if (currentModule?.kind === "chain_sprocket" && name === "chain_type") continue;
    if (currentModule?.kind === "chain_sprocket" && name === "row_count") continue;
    fieldsContainer.append(createField(name, schema, required.has(name)));
  }
  if (currentModule?.kind === "silent_chain_sprocket") {
    createSilentCompletionPanel();
    const profile = currentSpec.module.selection.standards[0].families
      .flatMap((family) => family.profiles)
      .find((item) => item.value === fieldsContainer.querySelector("[data-chain-selection='profile']")?.value);
    syncSilentToothCount(profile);
  }
  syncConditionalFields();
  syncSilentCompletion();
}

const silentCompletionNames = new Set([
  "body_depth_mm", "guide_depth_mm", "guide_bottom_radius_mm",
  "guide_width_mm", "guide_spacing_mm", "entrance_height_mm", "axial_round_radius_mm",
  "tool_root_radius_mm", "tool_floor_depth_mm", "din_rack_resolution", "square_tip_resolution", "square_tip_diameter_mm",
]);
let silentCompletionEpoch = 0;
let silentCompletionStale = false;

function createSilentCompletionPanel() {
  const panel = document.createElement("details");
  panel.className = "silent-completion";
  panel.dataset.silentCompletion = "";
  const summary = document.createElement("summary");
  summary.textContent = t("silent.completion_title");
  panel.append(summary);
  const body = document.createElement("div");
  body.className = "silent-completion-fields";
  panel.append(body);
  for (const name of silentCompletionNames) {
    const wrapper = fieldsContainer.querySelector(`[data-field-name='${name}']`);
    if (wrapper) body.append(wrapper);
  }
  const button = document.createElement("button");
  button.type = "button"; button.dataset.silentPropose = "";
  button.textContent = t("silent.completion_propose");
  button.addEventListener("click", async () => {
    button.disabled = true;
    const epoch = silentCompletionEpoch;
    const moduleKind = currentModule.kind;
    try {
      // Obtain proposals for the CURRENT source inputs, even after an invalid
      // edited construction. Old successful preview values are not a fallback.
      const payload = collectPayload({ withoutCompletion: true });
      for (const name of silentCompletionNames) delete payload[name];
      const result = await requestJson(currentModule.preview_url, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      if (!panel.isConnected || currentModule.kind !== moduleKind || epoch !== silentCompletionEpoch) return;
      for (const [name, field] of Object.entries(result.completion.fields)) {
        const input = panel.querySelector(`[name='${name}']`);
        if (input) input.value = field.suggested;
      }
      panel.open = true;
      silentCompletionStale = true;
      syncSilentCompletion(result);
      schedulePreview({ immediate: true });
    } catch (error) {
      renderWarnings([{ message: error.message }]);
    } finally { button.disabled = false; }
  });
  const note = document.createElement("p");
  note.className = "field-help"; note.dataset.silentCompletionNote = "";
  body.prepend(button);
  body.append(note);
  fieldsContainer.append(panel);
  const hint = document.createElement("p");
  hint.className = "silent-completion-hint";
  hint.dataset.silentCompletionHint = "";
  fieldsContainer.append(hint);
}

function syncSilentCompletion(result = lastPreviewResult) {
  if (currentModule?.kind !== "silent_chain_sprocket") return;
  const panel = fieldsContainer.querySelector("[data-silent-completion]");
  if (!panel) return;
  const report = result?.family === "silent_chain_sprocket" ? result.completion : null;
  const applicable = new Set(Object.keys(report?.fields || {}));
  if (applicable.has("square_tip_resolution")) {
    if (panel.querySelector("[name='square_tip_resolution']")?.value === "custom_diameter") applicable.add("square_tip_diameter_mm");
    else applicable.delete("square_tip_diameter_mm");
  }
  for (const name of silentCompletionNames) {
    const wrapper = panel.querySelector(`[data-field-name='${name}']`);
    if (!wrapper) continue;
    const input = wrapper.querySelector("input,select");
    // Restored form values must reach the first preview. With no report yet,
    // disabling all completion fields would turn a complete recipe into a
    // source-only request and leave its CAD action disabled.
    const visible = report ? applicable.has(name)
      : input.value !== "" && input.value !== "unresolved";
    wrapper.hidden = !visible;
    input.disabled = !visible;
  }
  panel.hidden = !!report && applicable.size === 0;
  const hint = fieldsContainer.querySelector("[data-silent-completion-hint]");
  hint.hidden = panel.hidden;
  hint.textContent = t("silent.completion_hint");
  panel.querySelector("summary").textContent = t("silent.completion_title");
  panel.querySelector("[data-silent-propose]").textContent = t("silent.completion_propose");
  const missing = (report?.missing_fields || []).map(name => localizedFieldName(name, {})).join("; ");
  panel.querySelector("[data-silent-completion-note]").textContent = t("silent.completion_explanation")
    + (report ? ` ${t(`silent.completion_status.${silentCompletionStale ? "pending_changes" : report.status}`)}` : "")
    + (missing ? ` ${t("silent.completion_missing", "", { fields: missing })}` : "");
}

function invalidateSilentGeometry(event) {
  if (currentModule?.kind !== "silent_chain_sprocket") return;
  // A number input can emit change on blur after input was already previewed.
  // Keep the accepted result when that event carries exactly the same payload.
  try {
    if (lastPreviewResult && payloadKey(collectPayload()) === lastSuccessfulPayloadKey) {
      silentCompletionStale = false;
      syncSilentCompletion();
      renderSummary(lastPreviewResult.summary);
      return;
    }
  } catch (_) { /* Incomplete input must follow the normal stale path. */ }
  silentCompletionEpoch += 1;
  silentCompletionStale = true;
  if (lastPreviewResult?.family === "silent_chain_sprocket") {
    renderSummary({ ...lastPreviewResult.summary, construction_status: "pending_changes" });
  }
  if (event.target.dataset.chainSelection || event.target.name === "axial_source") {
    for (const name of silentCompletionNames) {
      const input = fieldsContainer.querySelector(`[name='${name}']`);
      if (input) input.value = input.tagName === "SELECT" ? "unresolved" : "";
    }
    fieldsContainer.querySelector("[data-silent-completion]").open = false;
  }
  if (event.target.name === "tooth_tip_shape") {
    fieldsContainer.querySelector("[name='square_tip_resolution']").value = "unresolved";
    fieldsContainer.querySelector("[name='square_tip_diameter_mm']").value = "";
  }
  syncSilentCompletion();
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
  const selector = fieldsContainer.querySelector("[data-chain-profile-selector]");
  if (selector) {
    selector.querySelector("legend").textContent = t(currentModule.kind === "silent_chain_sprocket" ? "silent.selection.title" : "chain.selection.title", "Профиль цепи");
    for (const label of selector.querySelectorAll("[data-chain-selection-label]")) {
      const level = label.dataset.chainSelectionLabel;
      label.textContent = t(`${currentModule.kind === "silent_chain_sprocket" ? "silent" : "chain"}.selection.${level}`, humanize(level));
    }
    for (const select of selector.querySelectorAll("[data-chain-selection]")) {
      const level = select.dataset.chainSelection;
      for (const option of select.options) {
        option.textContent = getLocale() === "ru"
          ? (option.dataset.chainLabelRu || chainSelectionLabel(level, option.value))
          : (option.dataset.chainLabelEn || chainSelectionLabel(level, option.value));
      }
    }
  }
  if (currentModule?.kind === "silent_chain_sprocket") { syncConditionalFields(); syncSilentCompletion(); }
  if (["gear_spur", "gear_internal", "gear_bevel"].includes(currentModule?.kind)) refreshGearDynamicText();
  updateChainSelectionDetails();
}

function collectPayload({ withoutCompletion = false } = {}) {
  const payload = {};
  for (const input of fieldsContainer.querySelectorAll("input:not(:disabled), select:not(:disabled), textarea:not(:disabled)")) {
    if (withoutCompletion && silentCompletionNames.has(input.name)) continue;
    if (input.dataset.customProfileField) continue;
    if (input.dataset.chainSelection) continue;
    if (!input.name) continue;
    const type = input.dataset.schemaType;
    if (type === "boolean") {
      payload[input.name] = input.checked;
      continue;
    }
    const raw = input.value.trim();
    if (!raw) continue;
    if (type === "number" || type === "integer") {
      const value = input.tagName === "SELECT" ? Number(raw) : input.valueAsNumber;
      if (!Number.isFinite(value)) throw new Error(`${localizedFieldName(input.name, {})}: ${t("error.invalid_number")}`);
      if (type === "integer" && !Number.isInteger(value)) {
        throw new Error(`${localizedFieldName(input.name, {})}: ${t("error.integer_required")}`);
      }
      payload[input.name] = value;
    }
    else if (type === "object" || type === "array") payload[input.name] = JSON.parse(raw);
    else payload[input.name] = raw;
  }
  const chainProfile = fieldsContainer.querySelector("[data-chain-selection='profile']");
  if (chainProfile) {
    if (currentModule?.kind === "silent_chain_sprocket") {
      payload.standard = fieldsContainer.querySelector("[data-chain-selection='standard']")?.value;
      payload.family = fieldsContainer.querySelector("[data-chain-selection='family']")?.value;
    }
    payload.designation = chainProfile.value;
    const chainType = chainProfile.selectedOptions[0]?.dataset.chainType;
    if (chainType && currentModule.kind === "chain_sprocket") payload.chain_type = chainType;
    const nominalRowCount = chainProfile.selectedOptions[0]?.dataset.nominalRowCount;
    if (nominalRowCount) payload.row_count = Number(nominalRowCount);
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
  if (["gear_spur", "gear_internal", "gear_bevel"].includes(currentModule?.kind)) {
    if (currentModule?.kind === "gear_bevel") {
      payload.tooth_type = fieldsContainer.querySelector("[data-gear-tooth-type]")?.value || "straight";
    } else {
      const toothType = fieldsContainer.querySelector("[data-gear-tooth-type]")?.value || "spur";
      if (toothType === "spur") {
        payload.helix_angle_deg = 0;
        payload.hand = "right";
      } else {
        const angleInput = fieldsContainer.querySelector("[name='helix_angle_deg']");
        const angle = angleInput ? angleInput.valueAsNumber : Number.NaN;
        payload.helix_angle_deg = Number.isFinite(angle) && angle > 0 ? angle : 20;
        payload.hand = toothType;
      }
    }
    const properties = currentSpec?.schema?.properties || {};
    const ordered = {};
    for (const key of Object.keys(properties)) {
      if (key in payload) ordered[key] = payload[key];
    }
    for (const key of Object.keys(payload)) {
      if (!(key in ordered)) ordered[key] = payload[key];
    }
    return ordered;
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

function summaryLabelKey(key) {
  if (["gear_spur", "gear_internal"].includes(currentModule?.kind)) {
    const gearKeys = {
      pitch_diameter_mm: "gear_pitch_diameter_mm",
      outside_diameter_mm: "gear_outside_diameter_mm",
      root_diameter_mm: "gear_root_diameter_mm",
    };
    if (gearKeys[key]) return `summary.${gearKeys[key]}`;
  }
  if (currentModule?.kind === "gear_bevel") {
    const bevelKeys = {
      outer_pitch_diameter_mm: "gear_bevel_pitch_diameter_mm",
      outer_tip_diameter_mm: "gear_bevel_tip_diameter_mm",
      outer_root_diameter_mm: "gear_bevel_root_diameter_mm",
      pitch_cone_angle_deg: "gear_bevel_pitch_cone_angle_deg",
      face_cone_angle_deg: "gear_bevel_face_cone_angle_deg",
      root_cone_angle_deg: "gear_bevel_root_cone_angle_deg",
      outer_cone_distance_mm: "gear_bevel_outer_cone_distance_mm",
      virtual_tooth_count: "gear_bevel_virtual_tooth_count",
    };
    if (bevelKeys[key]) return `summary.${bevelKeys[key]}`;
  }
  return `summary.${key}`;
}

function renderSummary(values) {
  if (currentModule?.kind === "silent_chain_sprocket" && silentCompletionStale) values = { ...values, construction_status: "pending_changes" };
  summary.replaceChildren();
  for (const [key, value] of Object.entries(values || {})) {
    if (value === null || value === undefined) continue;
    if (key === "tooth_tip_shape" && currentModule?.kind === "silent_chain_sprocket"
      && fieldsContainer.querySelector("[data-field-name='tooth_tip_shape']")?.hidden) continue;
    const dt = document.createElement("dt");
    renderReadableSubscripts(dt, t(summaryLabelKey(key), humanize(key)));
    const dd = document.createElement("dd");
    if (typeof value === "number") dd.textContent = formatNumber(value, key === "chain_pitch_mm" ? 4 : 2);
    else if (typeof value === "boolean") dd.textContent = t(value ? "value.yes" : "value.no");
    else if (key === "selected_law") dd.textContent = localizedEnumValue("law", value);
    else if (["standard_system", "standard", "profile", "designation", "profile_shape", "chain_type", "family", "gost_profile_variant", "profile_construction", "profile_mechanics", "tooth_tip_shape", "profile_status", "axial_status", "construction_status", "hand", "over_pin_source", "tooth_type", "face_width_source"].includes(key)) dd.textContent = localizedEnumValue(key, value);
    else dd.textContent = String(value);
    summary.append(dt, dd);
  }
}

function renderSelectionSummary() {
  const designation = fieldsContainer.querySelector("[data-chain-selection='profile']")?.value;
  const standardValue = fieldsContainer.querySelector("[data-chain-selection='standard']")?.value;
  const familyValue = fieldsContainer.querySelector("[data-chain-selection='family']")?.value;
  const standard = currentSpec.module.selection.standards.find((item) => item.value === standardValue);
  const family = standard?.families.find((item) => item.value === familyValue);
  const profile = (family?.profiles || [])
    .find((item) => item.value === designation);
  if (!profile) return;
  renderSummary({
    silent_standard: getLocale() === "ru" ? standard.label_ru : standard.label_en,
    silent_family: getLocale() === "ru" ? family.label_ru : family.label_en,
    silent_designation: profile.designation_available === false
      ? t("silent.no_designation")
      : (getLocale() === "ru" ? profile.label_ru : profile.label_en),
    silent_type: standardValue === "gost_13552_81_13576_81"
      ? t(`silent.type_${profile.chain_type}`)
      : t(`silent.guide_${profile.chain_type}`, String(profile.chain_type || familyValue).replaceAll("_", " ")),
    silent_pitch_mm: profile.pitch_mm,
    silent_working_width_mm: profile.working_width_mm,
    silent_overall_width_mm: profile.overall_width_mm,
    silent_min_breaking_load_kn: profile.min_breaking_load_kn,
    silent_breaking_load_n: profile.breaking_load_n,
    silent_physical_tooth_count: fieldsContainer.querySelector("[name='physical_tooth_count']")?.value || "—",
    silent_accuracy_class: standardValue === "gost_13552_81_13576_81"
      ? fieldsContainer.querySelector("[name='accuracy_class']")?.value || "—"
      : null,
    silent_data_source: getLocale() === "ru"
      ? (profile.source_ru || (standardValue === "gost_13552_81_13576_81" ? "ГОСТ 13552-81" : profile.source))
      : (profile.source || null),
    silent_confidence: profile.confidence === "open_reconstruction" ? t("silent.open_reconstruction") : (profile.confidence || null),
  });
}

function renderWarnings(items, remember = true) {
  if (remember) displayedWarnings = items || [];
  warningsList.replaceChildren();
  warningsList.hidden = !displayedWarnings.length;
  if (warningsSection) warningsSection.hidden = true;
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
  if (!currentModule?.capabilities.preview) {
    updateDirtyState();
    renderSelectionSummary();
    setStatus(form.checkValidity() ? "silent.selection_ready" : "status.incomplete", form.checkValidity() ? "ready" : "error");
    return;
  }
  const revision = ++previewRevision;
  cadPlanController?.abort();
  cadPlanController = null;
  cadPlanKey = null;
  cadCreateButton.disabled = true;
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
    silentCompletionStale = false;
    syncSilentCompletion();
    renderSummary(lastPreviewResult?.summary);
    renderWarnings(previewResultWarnings(lastPreviewResult));
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
    silentCompletionStale = false;
    syncSilentCompletion(result);
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
  if (!currentModule?.capabilities.preview) {
    runPreview();
    return;
  }
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
    moduleCurrentName.textContent = moduleName(currentModule);
    moduleDescription.textContent = moduleDescriptionText(currentModule);
    standardBadge.textContent = moduleStandard(currentModule);
    setStatus(statusDescriptor.key, statusDescriptor.state, statusDescriptor.variables);
  }
}

function setModulePickerDisabled(disabled) {
  moduleSelect.disabled = disabled;
}

function selectorLabel(kind, value) {
  return t(`selector.${kind}.${value}`, humanize(value));
}

const selectorIcons = {
  group: {
    mechanical_transmissions: "/static/icons/transmission.svg",
    valvetrain: "/static/icons/valvetrain.svg",
  },
  subgroup: {
    belt_drives: "/static/icons/frictional.svg",
    chain_drives: "/static/icons/chain-drive.svg",
    gear_drives: "/static/icons/transmission.svg",
    valvetrain: "/static/icons/cam.svg",
  },
};

function selectorButton({ label, selected, description, onClick, icon }) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `selector-button${selected ? " selected" : ""}`;
  button.setAttribute("aria-pressed", String(selected));
  button.title = description || label;
  if (icon) {
    const iconElement = document.createElement("span");
    iconElement.className = "selector-icon";
    iconElement.style.setProperty("--icon-url", `url("${icon}")`);
    iconElement.setAttribute("aria-hidden", "true");
    button.append(iconElement);
  }
  const text = document.createElement("span");
  text.textContent = label;
  button.append(text);
  button.addEventListener("click", onClick);
  return button;
}

function uniqueValues(items, key) {
  return [...new Set(items.map((item) => item[key]).filter(Boolean))];
}

function renderModuleSelector() {
  moduleSelectorRows.replaceChildren();
  const groups = uniqueValues(moduleCatalog, "group");
  if (!selectorGroup || !groups.includes(selectorGroup)) selectorGroup = groups[0];
  const groupModules = moduleCatalog.filter((item) => item.group === selectorGroup);
  const subgroups = uniqueValues(groupModules, "subgroup");
  if (!selectorSubgroup || !subgroups.includes(selectorSubgroup)) selectorSubgroup = subgroups[0];
  const levels = [
    { key: "group", values: groups, selected: selectorGroup },
    { key: "subgroup", values: subgroups, selected: selectorSubgroup },
  ];
  for (const level of levels) {
    const row = document.createElement("div");
    row.className = "selector-row";
    row.dataset.level = level.key;
    row.style.setProperty("--selector-button-count", Math.max(1, level.values.length));
    const heading = document.createElement("p");
    heading.className = "selector-row-label";
    heading.textContent = t(`selector.level.${level.key}`, humanize(level.key));
    const buttons = document.createElement("div");
    buttons.className = "selector-row-buttons";
    for (const value of level.values) {
      buttons.append(selectorButton({
        label: selectorLabel(level.key, value),
        selected: value === level.selected,
        icon: selectorIcons[level.key]?.[value],
        onClick: () => {
          if (level.key === "group") {
            selectorGroup = value;
            selectorSubgroup = null;
          } else {
            selectorSubgroup = value;
          }
          renderModuleSelector();
        },
      }));
    }
    row.append(heading, buttons);
    moduleSelectorRows.append(row);
  }
  const moduleRow = document.createElement("div");
  moduleRow.className = "selector-row";
  moduleRow.dataset.level = "module";
  const selectedModules = groupModules.filter((item) => item.subgroup === selectorSubgroup);
  moduleRow.style.setProperty("--selector-button-count", Math.max(1, selectedModules.length));
  const moduleHeading = document.createElement("p");
  moduleHeading.className = "selector-row-label";
  moduleHeading.textContent = t("selector.level.module", "Модуль");
  const moduleButtonsRow = document.createElement("div");
  moduleButtonsRow.className = "selector-row-buttons module-selector-buttons";
  for (const module of selectedModules) {
    moduleButtonsRow.append(selectorButton({
      label: moduleName(module),
      selected: currentModule?.kind === module.kind,
      description: moduleDescriptionText(module),
      icon: module.icon,
      onClick: async () => {
        try {
          await selectModule(module.kind);
          showEditor({ locked: false });
        } catch (error) {
          setStatus("status.error", "error", { message: error.message });
          renderWarnings([{ message: error.message }]);
        }
      },
    }));
  }
  moduleRow.append(moduleHeading, moduleButtonsRow);
  moduleSelectorRows.append(moduleRow);
}

function showModuleSelector() {
  workspaceShell.hidden = true;
  editorShell.hidden = true;
  moduleShell.hidden = false;
  editorContext = null;
  renderModuleSelector();
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
    gear_spur: "block.gear_spur",
    gear_internal: "block.gear_internal",
    gear_bevel: "block.gear_bevel",
    silent_chain_sprocket: "block.silent_chain_sprocket",
    camshaft_lobe: "block.camshaft_lobe",
  }[block.module] || "block.generic";
  return t(family, block.name || block.module, {
    designation: profile.designation || "",
    count: profile.groove_count || profile.tooth_count || profile.physical_tooth_count || "",
    crown: formatNumber(profile.crown_height || 0),
    module: profile.module_mm != null ? formatNumber(profile.module_mm) : "",
  });
}

function selectWorkspaceBlock(block) {
  selectedWorkspaceBlock = block;
  workspaceInspectorEmpty.hidden = true;
  workspaceInspectorContent.hidden = false;
  workspaceBlockName.textContent = managedBlockName(block);
  renderWorkspaceBlockSummary(block);
  workspaceEditBlockButton.disabled = !block.editable && !block.recreatable;
  workspaceEditBlockButton.dataset.i18n = block.recreatable
    ? (block.module === "camshaft_lobe" ? "camshaft.cad.recreate" : "app.recreate_block")
    : "workspace.edit";
  workspaceEditBlockButton.textContent = t(workspaceEditBlockButton.dataset.i18n);
  workspaceBlockReadonly.hidden = !["camshaft_lobe", "silent_chain_sprocket", "chain_sprocket"].includes(block.module) || block.editable;
  workspaceBlockReadonly.dataset.i18n = block.module === "silent_chain_sprocket" ? "silent.cad.readonly"
    : block.module === "chain_sprocket" ? "chain.cad.readonly"
    : block.status === "partial" ? "camshaft.cad.partial"
    : block.status === "legacy_unverified" ? "camshaft.cad.legacy"
    : block.recipe_error ? "camshaft.cad.recipe_unavailable" : "camshaft.cad.readonly";
  workspaceBlockReadonly.textContent = t(workspaceBlockReadonly.dataset.i18n);
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
  moduleShell.hidden = true;
  editorShell.hidden = false;
  moduleHeading.classList.toggle("locked", locked);
  moduleHeading.dataset.lockedName = locked ? moduleName(currentModule) : "";
  setModulePickerDisabled(locked);
  document.querySelector(".cad-controls").hidden = !currentModule.capabilities.build
    || (currentModule.kind === "camshaft_lobe" && camshaftStep !== "cam");
  updateEditorPresentation();
  cadTitle.textContent = t(locked ? "cad.update_title" : "cad.title");
  cadDescription.dataset.i18n = currentModule.kind === "camshaft_lobe"
    ? "camshaft.cad.description" : currentModule.kind === "silent_chain_sprocket"
    ? "silent.cad.description" : locked ? "cad.update_description" : "cad.description";
  cadDescription.textContent = t(cadDescription.dataset.i18n);
  cadCreateButton.textContent = t(locked ? "cad.update" : "cad.create");
  editorDocumentActions.hidden = !locked;
  window.dispatchEvent(new Event("resize"));
}

function updateEditorPresentation() {
  if (!currentModule) return;
  const selectionOnly = !currentModule.capabilities.preview;
  editorShell.classList.toggle("selection-only", selectionOnly);
  selectionNote.hidden = !selectionOnly;
  document.querySelector('[data-i18n="controls.preview_note"]').hidden = !currentModule.capabilities.build;
  document.querySelector("#editor-shell .preview-panel").setAttribute("aria-label", t(selectionOnly ? "silent.selection.title" : "app.preview_region"));
  document.querySelector("#editor-shell .controls-panel").setAttribute("aria-label", t(selectionOnly ? "silent.selection.title" : "app.parameters_region"));
  const mode = selectionOnly ? "app.selection_only" : currentModule.capabilities.build ? "app.managed_cad" : "app.preview_only";
  editorModePill.title = t(`${mode}_title`);
  editorModeText.textContent = t(mode);
  editorTitle.textContent = moduleName(currentModule);
}

async function openSelectedBlockEditor() {
  if (!selectedWorkspaceBlock) return;
  const block = selectedWorkspaceBlock;
  if (!block.editable && !block.recreatable) return;
  editorContext = block.recreatable ? null : {
    documentId: selectedWorkspaceDocumentId,
    block: selectedWorkspaceBlock,
  };
  await selectModule(selectedWorkspaceBlock.module, false);
  baselinePayload = { ...baselinePayload, ...(block.recreatable ? block.recipe.studio_profile : block.profile || {}) };
  if (block.recreatable && block.module === "camshaft_lobe") camshaftStep = "cam";
  baselinePayloadKey = payloadKey(baselinePayload);
  renderFields();
  showEditor({ locked: !block.recreatable });
  await runPreview({ force: true });
}

function showWorkspace() {
  editorShell.hidden = true;
  moduleShell.hidden = true;
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
  setModulePickerDisabled(true);
  try {
    const spec = await requestJson(module.spec_url);
    if (revision !== selectionRevision) return;

    currentModule = module;
    currentSpec = spec;
    baselinePayload = JSON.parse(JSON.stringify(spec.defaults));
    baselinePayloadKey = payloadKey(baselinePayload);
    lastSuccessfulPayloadKey = null;
    lastPreviewResult = null;
    window.dispatchEvent(new Event("geomwright-cam-motion-reset"));
    customProfileDraft = null;
    customProfileBase = null;
    customProfileBaseValues = null;
    displayedWarnings = [];
    cadPlanKey = null;
    lastCadPlanReady = null;
    cadPlanController?.abort();
    cadPlanController = null;
    cadCreateButton.disabled = true;
    cadResult.textContent = "";
    moduleSelect.value = kind;
    moduleCurrentName.textContent = moduleName(module);
    moduleDescription.textContent = moduleDescriptionText(module);
    standardBadge.textContent = moduleStandard(module);
    document.querySelector(".cad-controls").hidden = !module.capabilities.build
      || (module.kind === "camshaft_lobe" && camshaftStep !== "cam");
    updateEditorPresentation();
    renderFields();
    if (!module.capabilities.preview) baselinePayloadKey = payloadKey(collectPayload());
    renderSummary({});
    renderWarnings([]);
    updateDirtyState();
    setStatus("status.module_ready", "idle", { module: moduleName(module) });
    if (autoPreview || !module.capabilities.preview) await runPreview({ force: true });
  } finally {
    if (revision === selectionRevision) setModulePickerDisabled(wasModuleSelectDisabled);
  }
}

function renderCadPlanReady(plan, elapsed) {
  cadResult.dataset.state = "ready";
  if (currentModule.kind === "camshaft_lobe") {
    cadResult.textContent = t("camshaft.cad.ready", undefined, {
      width: formatNumber(plan.width),
      error: Number(plan.fit.max_sampled_error_mm).toLocaleString(getLocale(), {maximumSignificantDigits: 3}),
    });
    if (plan.verification.curvature_shortfall_mm > 0) {
      cadResult.textContent += " " + t("camshaft.cad.curvature", undefined, {
        radius: plan.verification.min_sampled_curvature_radius_mm.toLocaleString(getLocale(), {maximumSignificantDigits: 4}),
        shortfall: plan.verification.curvature_shortfall_mm.toLocaleString(getLocale(), {maximumSignificantDigits: 3}),
      });
    }
    return;
  }
  const planDimensions = cadPlanDisplayDimensions(plan);
  cadResult.textContent = t("cad.plan_ready", "CAD plan ready", {
    elapsed: formatPlanElapsed(elapsed),
    diameter: formatNumber(planDimensions.outerDiameter),
    width: formatNumber(planDimensions.faceWidth),
  });
}

async function prepareCadPlan(payload, key = payloadKey(payload)) {
  if (currentModule.kind === "camshaft_lobe" && payload.step !== "cam") return;
  if (currentModule.kind === "silent_chain_sprocket" && lastPreviewResult?.completion
      && !lastPreviewResult.completion.geometry_complete) {
    cadPlanController?.abort();
    cadPlanController = null;
    cadPlanKey = null;
    cadCreateButton.disabled = true;
    cadResult.dataset.state = "pending";
    cadResult.textContent = t("silent.cad.incomplete");
    return;
  }
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
    lastCadPlanReady = { plan, elapsed: performance.now() - planStartedAt };
    renderCadPlanReady(plan, lastCadPlanReady.elapsed);
  } catch (error) {
    if (error.name === "AbortError" || controller !== cadPlanController) return;
    cadPlanKey = null;
    lastCadPlanReady = null;
    cadResult.dataset.state = "error";
    cadResult.textContent = currentModule.kind === "camshaft_lobe" && error.message.includes("cam build rejected:")
      ? t("camshaft.cad.rejected")
      : t("cad.plan_error", error.message, { message: error.message });
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
  const geometry = plan?.geometry || {};
  if (Number.isFinite(geometry.outer_tip_diameter_mm) && Number.isFinite(geometry.face_width_mm)) {
    return {
      outerDiameter: geometry.outer_tip_diameter_mm,
      faceWidth: geometry.face_width_mm,
    };
  }
  if (Number.isFinite(geometry.ring_outside_radius) && Number.isFinite(geometry.face_width)) {
    return {
      outerDiameter: 2 * geometry.ring_outside_radius,
      faceWidth: geometry.face_width,
    };
  }
  if (Number.isFinite(geometry.outside_radius) && Number.isFinite(geometry.face_width)) {
    return {
      outerDiameter: 2 * geometry.outside_radius,
      faceWidth: geometry.face_width,
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
  const buildModule = currentModule;
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
  const isCam = buildModule.kind === "camshaft_lobe";
  const isSilent = buildModule.kind === "silent_chain_sprocket";
  const isGear = ["gear_spur", "gear_internal", "gear_bevel"].includes(buildModule.kind);
  const isBevel = buildModule.kind === "gear_bevel";
  const modelName = editorContext?.block?.name || (isCam ? "Geomwright cam" : isSilent ? "Geomwright silent sprocket" : isGear ? "Geomwright gear" : "Geomwright pulley");
  if (!window.confirm(t(isCam ? "camshaft.cad.confirm" : isSilent ? "silent.cad.confirm" : isBevel ? "gear.cad.confirm_bevel" : isGear ? "gear.cad.confirm" : updating ? "cad.update_confirm" : "cad.confirm", undefined, { name: modelName }))) return;
  cadBuildActive = true;
  cadCancelButton.hidden = false;
  cadCreateButton.disabled = true;
  cadResult.dataset.state = "";
  cadResult.textContent = "";
  const startedAt = Date.now();
  try {
    const jobUrl = updating
      ? `/modules/${buildModule.kind}/cad/update-jobs`
      : buildModule.cad_job_url;
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
    if (["failed", "cancelled"].includes(job.status)) {
      const error = new Error(job.status === "cancelled" ? t("cad.cancelled") : (job.error || "CAD job failed").split(" | partial_result=")[0]);
      error.partialResult = job.partial_result;
      throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const elapsed = formatElapsed(Date.now() - startedAt);
    cadResult.dataset.state = "ready";
    cadResult.textContent = t(
      isCam ? "camshaft.cad.created" : isSilent ? "silent.cad.created" : isGear ? "gear.cad.created" : updating ? "cad.updated" : "cad.created",
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
      const created = await waitForCreatedBlock(job.result, buildModule.kind, 15000, documentsBeforeCreate);
      if (!created) {
        throw new Error(t("cad.created_block_missing", "The created managed block was not found in KOMPAS readback."));
      }
      workspaceSnapshot = created.snapshot;
      const createdEntry = created.entry;
      const createdBlock = created.block;
      selectedWorkspaceDocumentId = createdEntry.document.runtime_id;
      selectedWorkspaceBlock = createdBlock;
      // Cam and silent-chain blocks are create-only, and gear blocks are
      // read-only/recreatable: in-place update is not part of their contract.
      // Present the workspace with the new block instead of an update panel.
      if (isCam || isSilent || !createdBlock.editable) {
        editorContext = null;
        if (currentModule.kind === buildModule.kind) {
          baselinePayload = { ...profile };
          baselinePayloadKey = payloadKey(profile);
          updateDirtyState();
        }
        renderWorkspace();
        showWorkspace();
        return;
      }
      currentModule = buildModule;
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
    if (error.partialResult) {
      const partial = error.partialResult;
      const target = partial.document?.runtime_id || partial.document_id;
      cadResult.textContent += ` ${t("camshaft.cad.partial")} ${target || t("camshaft.cad.partial_unknown")}`;
    }
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
  if (!moduleShell.hidden) renderModuleSelector();
  if (currentSpec) {
    customProfileDraft = readCustomProfileDraft();
    const customMode = fieldsContainer.querySelector("[name='designation']")?.value === "CUSTOM";
    localizeFields();
    if (customMode) {
      fieldsContainer.querySelector("[data-custom-profile-editor]")?.replaceWith(createCustomProfileEditor());
    }
  }
  if (lastPreviewResult) renderSummary(lastPreviewResult.summary);
  if (currentModule && !currentModule.capabilities.preview) renderSelectionSummary();
  renderWarnings(displayedWarnings, false);
  if (currentModule) {
    updateEditorPresentation();
  }
  refreshStatusLanguage();
  if (lastCadPlanReady && cadResult.dataset.state === "ready") {
    renderCadPlanReady(lastCadPlanReady.plan, lastCadPlanReady.elapsed);
  }
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
    showEditor({ locked: false });
  } catch (error) {
    setStatus("status.error", "error", { message: error.message });
    renderWarnings([{ message: error.message }]);
  }
});
form.addEventListener("input", (event) => { invalidateSilentGeometry(event); schedulePreview(); });
form.addEventListener("wheel", (event) => {
  const input = event.target.closest("input[type='number']");
  if (!input || input.disabled || input.readOnly || event.deltaY === 0) return;
  event.preventDefault();

  const configuredStep = Number(input.step);
  const step = Number.isFinite(configuredStep) && configuredStep > 0 ? configuredStep : 1;
  const minimum = input.min === "" ? -Infinity : Number(input.min);
  const maximum = input.max === "" ? Infinity : Number(input.max);
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
  invalidateSilentGeometry(event);
  if (event.target.name === "axial_source") syncConditionalFields();
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
  showModuleSelector();
});
moduleShellWorkspaceButton.addEventListener("click", showWorkspace);
editorModulesButton.addEventListener("click", showModuleSelector);
editorWorkspaceButton.addEventListener("click", showWorkspace);
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
