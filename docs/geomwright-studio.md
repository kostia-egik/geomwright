# Geomwright Studio

Geomwright Studio is the standalone local UI for Geomwright modules. It does not
require an AI agent: modules expose deterministic schemas and operations that
the UI can invoke directly. An agent is an optional client of the same contracts,
not a required intermediary between the UI and CAD.

The current experimental slice supports V-belt, Poly-V, flat-belt, and two
shape-specific timing-pulley preview modules through one schema-driven form and
one HTML5 Canvas renderer.
For the flat-belt pulley, Studio exposes one continuous `crown_height` parameter:
zero means a cylindrical rim and a positive value means a crowned rim. The
internal CAD plan still records the inferred profile kind for ownership/readback.

The implemented CAD vertical slice creates a new unsaved KOMPAS part, builds its
own parameterized member, applies family geometry (grooves or a flat rim), and
verifies the result. It will not modify an arbitrary existing body. CAD planning is
read-only and runs automatically after each valid preview; only execution
requires an explicit confirmation.

The flat-belt slice is complete: cylindrical and circular-crown sketches are
fully constrained through formula-bound driving dimensions, and create, inspect,
update, save, and reopen behavior has been verified in live KOMPAS.

The timing-belt slice has managed CAD build for both trapezoidal T/AT and
curvilinear HTD. Both modules use a cropped end view of three grooves and two teeth, short reference
arcs, a lower-and-side wavy break boundary, tangent tip/root fillets, and
distributed outside/root diameter, pitch, and radius dimensions. T/AT exposes
`build=true` after live create, variable update, pattern readback, rollback, and
save/reopen acceptance. HTD uses its own three-arc one-groove mechanics and was
accepted through fully-defined sketch, designation/tooth-count/width update,
rollback, and save/reopen checks. Module descriptors carry group/subgroup/family
metadata; the module selector remains a compact catalog list while the catalog
grows, separating wedge, friction, and synchronous pulleys.

The intended module lifecycle is `preview -> inspect -> create -> edit ->
rebuild -> verify`. Later Studio slices may call deterministic CAD workflows
directly, including structural rebuilds that replace managed sketches or
features when a change cannot be expressed by editing variables. Those write
capabilities must use the same preflight, explicit-target, readback, and
save/reopen checks as the existing MCP workflows. Internet access and an AI
agent remain optional for this lifecycle.

## Workspace direction

Document navigation is a Studio responsibility, not part of an individual
transmission module. The workspace will provide one compact shell for:

- discovering the active and other open KOMPAS documents automatically;
- opening a saved `.m3d` file or starting a new managed part;
- showing recognized Studio blocks in the context of surrounding unmanaged
  KOMPAS operations;
- routing a recognized block to its editor with the module family locked;
- returning from editing to the same document and tree context.

Recognized timing-pulley blocks display their timing designation and tooth count in
the tree and inspector. Pattern-generated invalid helper sketches are marked as
owned internal operations, so a clean managed block does not acquire a generic
“KOMPAS operations” group; valid or unrelated operations remain visible as context.

Studio attaches only to an already running KOMPAS COM object and makes that
registered instance visible before document work. Starting Studio first is
supported: the workspace remains disconnected and retries automatically after
KOMPAS starts instead of creating a hidden process.

The first implementation targets one managed block per document. Multi-block
cascade creation and dependency editing are deferred until the module catalog is
large enough to justify them. Nevertheless, workspace APIs return a `blocks`
list and stable identities instead of a single hard-coded pulley field. Mixed
models are in scope now: unmanaged KOMPAS features remain visible as context but
Studio never claims ownership of or silently edits them.

Pulley recognition and editing are ownership-based. A managed pulley must remain
discoverable after users or other modules append hubs, bores, keyways, chamfers,
or other downstream features. Editing updates the owned blank and groove
operations, then verifies the complete KOMPAS rebuild cascade instead of
requiring the managed groove to be the last feature in the tree.

## One-click Windows launch

Double-click `start-geomwright-studio.cmd` in the repository root. The launcher:

1. uses the repository `.venv`, or creates it with Python 3.11 on first launch;
2. installs the local editable `geomwright` package with its `ui` extra only
   when the package or UI dependencies are missing;
3. starts the server on `http://127.0.0.1:8765` and opens the default browser.

Keep the console window open while using the UI. Close it or press `Ctrl+C` to
stop the server. Starting the launcher again while the UI is already running
opens another browser tab instead of starting a second server.

If the default port `8765` belongs to an older Studio process or another local
application, the one-click launcher selects the next free port and reports the
chosen URL. An explicit `--port` remains strict: if that exact port is occupied,
Studio stops and asks for a different value instead of silently changing it.

Python 3.11 or newer must be installed and available through `py` or `python`.
The first launch may require internet access to install dependencies.

## Manual launch

From a PowerShell prompt in the repository virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ui]"
.\.venv\Scripts\python.exe -m geomwright.studio --port 8765
```

The browser opens after the health endpoint becomes ready. Pass `--no-browser`
for a headless or supervised launch. The server binds only to localhost.

During the naming migration, `start-mechanics-ui.cmd`,
`kompas-mechanics-ui`, and `python -m kompas_mcp.mechanics.ui` remain supported
compatibility aliases. New automation should use the Geomwright Studio names.
The launcher checks for the `geomwright` distribution metadata, so an existing
environment created under the former package name receives the new entry points
on its next launch.

## Working with the preview

- Parameter edits trigger a new preview automatically after a short debounce.
  If inputs change again while a request is running, the old request is
  cancelled and its response cannot replace the newer result.
- The status bar distinguishes calculation, changed values, successful refresh,
  incomplete input, and an error that leaves the last valid profile visible.
- **Сбросить изменения / Reset changes** restores the module defaults. Creating
  a pulley is a separate confirmed action and does not silently change this form
  baseline.
- The RU/EN switch changes the interface language and persists it in browser
  local storage. Stable parameter identifiers such as `groove_count` remain
  visible in English under the localized field labels.
- Numeric fields support native arrows, direct entry, and wheel stepping. While a
  pointer is over a numeric field, the wheel changes that field by its step and is
  consumed by the editor, so the controls panel does not scroll at the same time.
- The canvas shows face width `B`, groove pitch `e`, groove depth `h`, the
  groove-entry width `b₀`, angle `α`, and outer, datum/effective, and root
  diameters. Poly-V previews also identify transition radius `Rₜ` and maximum
  root radius `Rᵣ` on the first groove. The drawing uses symbols only; the
  summary expands each symbol in parentheses beside its name.
- When the normalized V-belt profile carries a top-edge fillet, the canvas
  overlays both post-cut fillet arcs on every groove and dimensions the first
  one as `Rₖ`. Catalog radii are highlighted separately from explicit profile
  overrides. The straight-sided closed polygon remains visible because it is
  the functional cut sketch; the highlighted arcs represent the separate CAD
  fillet operation that follows the cut. Current DIN/ISO catalog rows have no
  configured top-edge fillet, while GOST 20889-88 Z/A/B/C/D/E rows use their
  catalog radii.
- A truncated pulley body provides scale and material context without implying
  a hub, bore, web, or other geometry outside the groove module. Its sides are
  phantom lines, its fragment edge is wavy, and diameter leaders use a standard
  break mark.
- Timing-pulley fragments omit the straight-line tooth-pitch dimension and the
  pitch circle. They show radial outside/root diameter leaders, a thin
  tooth-tip reference arc, center-groove width `s` and depth `h`, and separated
  tooth-tip/root-fillet radius leaders.
- The desktop parameter panel scrolls independently when the screen is short.
  Narrow viewports stack the preview and form into one page; the canvas keeps
  compact diameter symbols so annotations remain within the available width.
- The canvas supports wheel zoom, drag pan, and double-click view reset.

### Custom profiles

Studio presents `custom_profile` through an inline numeric editor. Choose
**Свой профиль… / Custom profile…** to open it.
The editor starts from the last successfully previewed catalog profile and
labels the result as non-standard. It exposes separate required fields for
datum width, datum-line offset, groove pitch, edge distance, groove depth, and
groove angle; less common dimensions are collapsed under an additional-fields
control. **Вернуть размеры основы / Restore base dimensions** discards edits and
copies the catalog values again.

The browser still submits the existing `custom_profile` request object, so this
presentation change does not alter the deterministic transmission contract.
Raw `profile_overrides` are intentionally hidden from the ordinary Studio form;
they remain part of the programmatic API and are preserved when Studio edits a
model that already contains them.

## HTTP contract

| Route | Purpose |
| --- | --- |
| `GET /health` | Report managed-CAD mode and registered module count |
| `GET /modules` | List module descriptors and capabilities |
| `GET /modules/{kind}/spec` | Return the request JSON Schema and UI defaults |
| `POST /modules/{kind}/preview` | Validate input and return normalized canvas geometry |
| `POST /modules/{kind}/cad/plan` | Build the owned-blank and groove plan without COM or document changes |
| `POST /modules/{kind}/cad/create` | Create and verify a new unsaved managed pulley after explicit confirmation |
| `POST /modules/{kind}/cad/jobs` | Start confirmed creation as a serialized background CAD job |
| `GET /cad/jobs/{job_id}` | Read the job stage, elapsed timestamps, result, or actionable error |
| `GET /workspace` | Discover open KOMPAS documents and return recognized blocks plus compact mixed-operation context |
| `POST /workspace/activate` | Activate an exact runtime document, including one of several unsaved `Untitled` models |
| `POST /workspace/pick-file` | Show the native Windows `.m3d` picker without starting KOMPAS file I/O |
| `POST /workspace/pick-save-file` | Show the native Windows Save As picker for an unsaved `.m3d` model |
| `POST /workspace/open` | Open a selected `.m3d` path in KOMPAS and refresh workspace state |
| `POST /workspace/open-dialog` | Show the native Windows `.m3d` picker, open the selected model in KOMPAS, and refresh workspace state |
| `POST /workspace/close` | Save or discard one exact runtime document, close it, verify removal, and refresh workspace state |
| `POST /workspace/save` | Save one exact runtime document without closing it; untitled models require an explicit Save As path |
| `POST /workspace/save-as` | Save one exact runtime document to an explicitly selected path without closing it |
| `POST /modules/{kind}/cad/update-jobs` | Rebuild a recognized managed block in place as a background job with progress and readback |

The browser requests the plan automatically after a valid preview, so there is
no separate planning button, and reports the measured planning time. It polls
the job endpoint while KOMPAS is building and shows a compact progress bar,
the latest bridge checkpoint percentage, the exact current operation and model
object name, and elapsed time. Percentages change only when bridge execution
enters a concrete COM step; successful final readback sets the bar to 100%.
Completion remains visible for one second, then the progress block is removed
from the layout and the total execution time remains in the result message.
File selection and opening are separate browser requests: after the native
picker closes, the workspace blocks repeat actions and displays the selected
file name plus elapsed time while KOMPAS opens and Studio recognizes the model.
Closing is likewise explicit and document-scoped. A changed model offers
Save/Don't save/Cancel; an unchanged saved model closes immediately. Saving an
untitled model first opens the native Save As picker. Save, Save As, and Close
are document-level icon actions in workspace headers; Save and Save As are also
available in an existing-block editor header, outside the block rebuild panel.
Every document card has its own Close action. Cancel never reaches the bridge.
Lifecycle writes use strict runtime-ID resolution, so a stale workspace
selection fails instead of falling back to the currently active KOMPAS document.

After successful creation Studio reads back the new document and recognized
managed block, then converts the creation form into that block's fixed-family
editor. The primary action changes from `Create in KOMPAS` to `Rebuild model`.
The editor applies the current profile to that exact block, then verifies
rebuild, ownership readback, one solid body, positive volume, and requested
profile metadata. Parameter-only changes rebuild through variables. Groove
count, V-belt catalog variant, standard, and standard-fillet topology changes
replace only the owned groove branch after a strict downstream-operation
preflight. On failure the bridge recreates the previous owned branch from the
rollback plan.

Every preview returns the same UI-facing geometry keys:

- `closed_points`: one or more closed profile polylines;
- `guide_paths`: optional non-cut reference paths;
- `reference_paths`: datum or effective-diameter construction lines;
- `phantom_bodies`: presentation-only, truncated pulley-body context;
- `bounds`: world-coordinate limits used to fit the canvas;
- `dimensions`: linear and diameter annotations derived from the existing
  preview result;
- `summary`: stable English keys with values localized only in the browser;
- `warnings`: original messages retained for compatibility;
- `warning_items`: stable warning codes plus original fallback messages for
  RU/EN rendering.

The request schemas remain owned by `transmission_tools.py`, and the calculations
remain owned by the existing functions in `transmissions/`. UI registration and
response adaptation live in `src/geomwright/studio/registry.py`; they must not duplicate
profile formulas or CAD execution logic.

## Verification

Run the focused host-side contract checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_geomwright_studio.py
```

The command should complete with all checks passing. The create operation
performs live build/readback verification and leaves the new document open and
unsaved. Explicit save and reopen verification remain a separate workflow.
Managed-pulley inspection scans all part variables, sketches, and rotational
features and does not assume that the groove operation is last.
