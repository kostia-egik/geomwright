# External polygon common-interface contract

`external_polygonal_step` connects the existing regular-polygon solid-prism
generator to `get_cad_module_contract` and `run_cad_module`. Preview and plan are
host-only; create builds a new part; inspect recognizes a saved creation recipe.
This is a create-only generator integration, not a completed three-component
Studio module. No new Studio block, internal cut, foreign-body application,
finishing, arbitrary placement or public in-place editor is included in the
standalone module. The separately verified [construction-chain adapter](en/construction-chains.md)
supports own/create and own/add along global-X, explicit core cuts and saved-chain
continuation; it does not change standalone creation policy.

## Inputs and frame / Входы и система координат

The runtime schema is the parameter authority. Required inputs are `diameter`,
`length` (positive finite mm) and `side_count` (integer 3..64). The upper count is
a profile/readback cost bound, not a standard or exhaustive live certification.
`diameter_mode` selects `inscribed_circle` (default, diameter across flats) or
`circumscribed_circle` (diameter through vertices). `rotation_angle_degrees` is
the initial profile orientation, default 0 degrees. `axial_direction` defaults
to `forward`; `backward` reverses the extrusion.

The profile is on global YOZ: local u maps to global Z, local v to global Y,
normal to negative X. Forward occupies X=[-length,0], backward X=[0,length].
The circumradius R is D/(2 cos(pi/n)) for the incircle mode and D/2 for the
circumcircle mode. Volume is n R² sin(2 pi/n) length / 2000 cm³.
All 2n expected native vertices and bounds are calculated from the same profile.

```json
{"module_id":"external_polygonal_step","action":"plan","parameters":{"diameter":30,"length":25,"side_count":6,"diameter_mode":"inscribed_circle","rotation_angle_degrees":0,"axial_direction":"forward"}}
```

РУ: создаётся отдельная сплошная правильная призма. Диаметр задаётся по вписанной
или описанной окружности; длина и диаметр — в мм, угол — в градусах. Профиль YOZ:
u→Z, v→Y; прямое выдавливание идёт вдоль −X, обратное вдоль +X. Диапазон 3..64
ограничивает стоимость построения и чтения, а не обозначает стандарт.

## Parametrization and recognition / Параметризация и распознавание

`POLY_D1`, `POLY_L1`, `POLY_A1` are actual diameter, length and orientation
drivers. Length binds native Distance 1 for forward and Distance 2 for backward.
Orientation binds the first-edge/radius-line angle to offset − POLY_A1, with the
angular branch selected at creation. Crossing that branch requires recreation;
the entire 360-degree manual-edit domain is not certified. Side count, circle
interpretation and axial direction also require recreation.

The adapter removes the legacy horizontal first-edge lock, including at zero
initial rotation. Equal chords and a concentric vertex circle define regularity;
one first-side tangency sets the incircle relation. The other n−1 tangencies are
redundant and can stall the native solver. This correction is local to the common
adapter; the legacy scenario interface is unchanged.

Checksummed versioned `EPOL_RECIPE_*` stores original inputs, not driving state or
a verification stamp. Inspect needs an exact document ID, checks recipe and owned
roots, and returns inputs for a new build. It does not audit current geometry or
manual edits. Missing/incomplete/corrupt recipes cannot substitute defaults.

РУ: POLY_D1/L1/A1 реально управляют диаметром, длиной и ориентацией внутри выбранной
при создании угловой ветви. Изменение числа сторон, трактовки диаметра, направления
или переход через границу ветви требует пересоздания. Inspect восстанавливает
исходные входы из рецепта, но не проверяет заново геометрию и ручные изменения.

## Verification and failure state / Проверка и ошибки

Create requires `confirm_write: true` and the selected CAD session policy. The
shared legacy-body lifecycle checks one solid, positive analytic/native volume,
exact vertex count/positions, bounds, fully defined profile (native state 1,
`ksStateWellConstrained`) and
saved recipe. Coordinate tolerance is 1e−5 mm; volume tolerance is the larger of
1e−7 cm³ and 1e−5 relative. These are readback tolerances, not manufacturing ones.

Interactive mode retains the saved visible document: its result explicitly
reports deferred fresh reopen, not a completed reopen. Hidden mode's lifecycle
performs actual save/reopen. Hidden-instance isolation remains a separate
verification task; the evidence below concerns interactive KOMPAS only.
Errors retain partial-document information; no automatic retry, rollback or
closure of user documents is claimed. Follow the shared session guard on unknown
outcomes before any further COM request.

Full-definition evidence caveat: the original live reports used a reversed native
state decoder. Their raw code 2 is under-constrained, not fully defined. The shared
decoder and gate are corrected; the older polygon models need a separate fresh
solver-state review. Their geometric/driver readback is not erased by this finding.
See [SKETCH-011](../CAD_PATTERNS.md#sketch-011-decode-sketch-state-from-the-native-enum-not-an-assumed-numeric-scale).

The common builder now applies the canonical profile name and fixed sketch placement
before its first Update and parameterization. It no longer renames/fixes the sketch
after construction or unconditionally enters its editor as a solver-settle attempt.
Fresh D30/L10 incircle hexagon, D32/L22/17-degree backward incircle pentagon and
D24/L17/23-degree circumcircle triangle pass geometry/volume checks and native state1
without manual UI activation. Real close/reopen preserves state1 on the first two.
This is representative construction evidence, not a general repair of KOMPAS's
API/UI refresh limitation or fresh certification of manual driver edits.

Live interactive geometry checks passed for a rotated backward incircle pentagon (D32,
L22,17°), zero-angle forward incircle hexagon (D30,L25), and rotated forward
circumcircle triangle (D24,L17,23°). Each passed exact native vertices, volume,
historically reported solver state and explicit save/reopen. Each also passed diameter/length/angle
driver changes and restoration with geometry readback. This is representative
evidence, not certification of every count, angle or manual edit.

РУ: проверяются одно тело, вершины, габариты, объём и полностью определённый
профиль (native code 1). Старые отчёты ошибочно трактовали code 2 как полную
определённость; эти выводы требуют новой живой проверки. В интерактивном режиме сохранённый документ остаётся открыт: повторное
открытие не подменяется чтением из той же вкладки. Отдельные живые проверки
треугольника, пятиугольника и шестиугольника включали настоящее save/reopen и
изменение трёх driving-переменных с восстановлением. Автоматического отката,
повтора и закрытия пользовательских документов нет; нового блока Studio нет.
