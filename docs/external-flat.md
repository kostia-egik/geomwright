# External flat-step common-interface contract

`external_flat_step` connects the existing standalone cylinder-with-flats
generator to `get_cad_module_contract` and `run_cad_module`. Preview/plan run
without CAD; create builds a new part; inspect restores original creation inputs.
This is a create-only generator integration, not a complete three-component Studio
module. No new Studio block, foreign-body application, internal cut, finishing,
threads, arbitrary placement or public in-place editing is included in standalone
creation. The separate [construction-chain adapter](en/construction-chains.md)
supports own/create and own/add along ±global-X, numeric axial placement and core
cuts in one shared body; standalone creation policy is unchanged.

## Inputs and geometry / Входы и геометрия

`ExternalFlatParameters` and the runtime schema own fields/defaults/ranges.
Required inputs are positive finite `diameter`, `length`, `flat_depth` in mm.
Depth must satisfy 0 < flat_depth < diameter/2. `flats_count` selects one flat
or two opposing flats; `axial_direction` selects forward/backward extrusion.
Extra fields, invalid counts, non-finite geometry and profiles unrepresentable
at native seed precision are rejected before CAD. This is engineering geometry,
not a standards selector or manufacturing certification.

With R=D/2, s=R-F, h=sqrt(F(2R-F)), let H=s h+R² asin(s/R). One-flat profile
area is pi R²/2+H; two-flat area is 2H. These forms avoid subtracting almost equal
circle/cap areas for deep two-flat profiles. Volume is area*length/1000 cm³.
Legacy starting chord lines are deliberately shortened for parameterization;
expected finished endpoints are analytic, not copied from those seeds.

The construction axis is global X, with profile on YOZ at the origin. Forward
occupies X=[-length,0], backward X=[0,length]. The first flat lies on
Y=-(diameter/2-flat_depth); the second, if selected, on the opposite positive Y
level. Both profiles span Z=[-R,R]. Do not copy the polygon builder's local frame:
native flat readback confirms the positive local flat offset maps to negative Y.
The sign of the local chord axis is not inferred from symmetric endpoints alone.

```json
{"module_id":"external_flat_step","action":"plan","parameters":{"diameter":30,"length":25,"flat_depth":4,"flats_count":1,"axial_direction":"forward"}}
```

РУ: модуль создаёт собственное цилиндрическое тело с одной или двумя
противоположными лысками. D/L/F задаются в мм; 0<F<D/2. Прямое выдавливание идёт
вдоль −X, обратное вдоль +X. Первая лыска находится на Y=−(D/2−F), вторая — на
противоположной плоскости. Это инженерная геометрия без заявления о соответствии
стандарту; операции над чужими телами и новый блок Studio не добавлены.

## Driving inputs and recipe / Driving-входы и рецепт

`FLAT_D1`, `FLAT_L1`, `FLAT_F1` drive diameter, extrusion length and flat depth.
Profile diameter binds FLAT_D1; flat offset binds FLAT_D1/2−FLAT_F1. Extrusion
length binds native Distance 1 for forward and Distance 2 for backward (with
Russian aliases). Flats count and direction require recreation.

Checksummed versioned `EFLT_RECIPE_*` retains all original independent inputs
and owned sketch/extrusion root names. Recipe fields are metadata, not driving
variables or verification stamps. Inspect requires an exact opened document ID,
recognizes valid unique owned roots and the recipe, and returns inputs for a new
build. It does not audit current geometry or manual driving edits. Incomplete or
corrupt recipes cannot substitute defaults. Older raw scenario/probe files without
this recipe are not automatically upgraded or recreatable through this contract.

РУ: FLAT_D1/L1/F1 реально управляют диаметром, длиной и глубиной лыски. Число
лысок и направление требуют пересоздания. Inspect читает исходный рецепт и
принадлежащие модулю операции, а не выполняет новый аудит геометрии или ручных
изменений. Старым файлам без полного рецепта значения по умолчанию не подставляются.

## Verification and evidence / Проверка и доказательства

Create requires `confirm_write: true` and the selected CAD session policy. It
saves a unique export and uses the shared legacy-body lifecycle. Readback checks
one positive-volume solid, final trimmed cylindrical/flat/end faces, radius,
axial intervals, all chord endpoints, bounds and analytic/native volume. Profile
must be fully defined: API7 `ISketch` native code 1, not code 2; see
[SKETCH-011](../CAD_PATTERNS.md#sketch-011-decode-sketch-state-from-the-native-enum-not-an-assumed-numeric-scale).
Coordinate tolerance is 1e−5 mm; volume tolerance is max(1e−7 cm³,1e−5 relative).
The legacy chord comparison's 1e−9 relative bound rejects lost seed precision;
it is a host representability check, not a geometric/manufacturing tolerance.

Interactive mode retains the saved visible document and reports deferred fresh
reopen. Hidden mode performs actual lifecycle save/reopen; hidden-instance
isolation is a separate verification task. Failed/unknown outcomes preserve
partial-document evidence and follow the session guard; no automatic retry,
rollback or closure of user documents is claimed.

Representative live evidence covers D30/L25/F4 one-flat forward and two-flat
backward bodies, exact native bounds/chord vertices/radius/volume, separate D/L/F
changes, restoration and explicit actual close/reopen. Volumes are approximately
16.270757442 and 14.870056208 cm³. All successful final and driving states use the
verified full-definition enum. This does not certify every numeric boundary.

The common EFLT path also passed actual fresh stdio-MCP create/inspect and explicit
close/reopen for both representative variants. Checksum-validated complete recipe,
unique valid sketch/extrusion roots, native geometry and well-constrained code 1
survived reopening; foreign documents were unchanged. This is interactive evidence,
not hidden-isolation or exhaustive numeric-domain certification.

Canonical sketch name is assigned before its initial Update and geometry creation.
A late Name assignment initially read correctly in memory but reverted on reopen;
late rename+Update preserved the name but left native state 2. That diagnostic
candidate is not accepted evidence. The corrected early-name path passed fresh
creation and reopen without numeric fixing; see `OP-003` in CAD patterns.

РУ: обе формы проверены живыми пробами, включая изменение D/L/F, восстановление
и настоящее повторное открытие. Общий интерфейс с EFLT-рецептом также проверен
через настоящий stdio-MCP: create/inspect и explicit close/reopen сохранили
полный рецепт, owned roots, геометрию и code 1. Canonical name задаётся до
параметризации; неудачная проба с поздним переименованием не считается подтверждением.
Интерактивное чтение сохранённой открытой вкладки не называется fresh reopen.
Автоматического отката, повтора и закрытия пользовательских документов нет.
