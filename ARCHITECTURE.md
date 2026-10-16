# Архитектура Geomwright

Этот документ определяет владельцев runtime-логики и границу между рабочим MCP,
CAD-side bridge, параметрическими модулями и исследовательскими прототипами.

Краткий обзор для разработчика: [English](docs/en/architecture.md) /
[Русский](docs/ru/architecture.md). Этот файл остаётся каноническим источником
подробного ownership и границ runtime.

## Runtime-топология

```text
MCP client
    │ JSON/MCP
    ▼
src/geomwright/server.py
    │ default application facade
    ▼
src/geomwright/kompas/server.py
    │ tool registration
    ▼
src/kompas_mcp/*_tools.py + KompasAdapter implementation
    │ JSON request/result files
    ▼
BridgeRunner
    │ launches the configured modern Windows Python with pywin32
    ▼
bridge/kompas_bridge.py
    │ API7/API5 COM
    ▼
KOMPAS-3D document/model
```

MCP host работает на Python, указанном в `pyproject.toml`. Bridge запускается
отдельным интерпретатором с `pywin32` и доступом к KOMPAS COM. Явный аргумент и
`KOMPAS_PYTHON` имеют приоритет; source checkout затем выбирает существующий
`.venv/cad-bridge`, иначе используется SDK fallback. Production bridge проходит
ограниченный compile/import preflight без COM до tracked CAD launch; локальный
`CAD_RUNTIME_INVALID` не создаёт quarantine. Custom bridge contract не меняется.
Его синтаксис должен поддерживаться выбранным интерпретатором. Старый встроенный
Python 3.2 не поддерживает текущий bridge; настройка современного runtime описана
в README. `KOMPAS_REQUIRE_VISIBLE=1` задаёт attach-only режим для MCP так же, как
Studio: отсутствие работающего КОМПАС — ошибка подключения, не создание скрытой копии.

Продукт, Python distribution и публичный application namespace называются
Geomwright. `geomwright.server` предоставляет MCP entry point,
`geomwright.kompas.server` владеет KOMPAS MCP bootstrap и единым реестром
инструментов, а `geomwright.studio` владеет presentation layer. Публичные фасады
адаптера и tool catalog находятся в `geomwright.kompas`; остальные
KOMPAS-specific implementation modules временно сохраняются в namespace
`kompas_mcp`. Их массовая замена затронула бы внутренние импорты, packaged bridge
и пользовательские интеграции без добавления runtime-возможностей.
`kompas_mcp.server` делегирует каноническому bootstrap и возвращает те же объекты
`mcp` и `adapter`; старые CLI и import aliases остаются доступными на переходный
период.

Экспериментальный Geomwright Studio — отдельный host-side presentation adapter.
Entry point `geomwright.studio` вызывает существующие Layer 2
preview-функции и адаптирует их результат для HTML5 Canvas. Он не регистрируется
в MCP tool catalog. Preview-only модули не запускают bridge; managed-CAD модули
вызывают ограниченные workflows адаптера с явным подтверждением записи.
Старые entry points `kompas_mcp.studio` и `kompas_mcp.mechanics.ui` сохранены
только как compatibility aliases.

Канонический исходник bridge находится в `bridge/kompas_bridge.py`. Его packaged
копия — `src/kompas_mcp/assets/bridge/kompas_bridge.py`. Эти файлы обязаны быть
byte-identical.

`BridgeRunner` является Layer 1 process boundary. Штатный `normal` режим имеет
ограниченный timeout и удаляет временный transport state; явный `diagnostic`
режим сохраняет request/response/progress/stdout/stderr как внешние артефакты.
Progress callbacks получают единый компактный envelope, а timeout/cancellation
ошибки содержат последний доступный checkpoint. Это реализует `SESSION-002` без
изменения публичных CAD-result schemas. Bridge dispatch дополнительно публикует
bounded start/completed/failed checkpoints вокруг каждой action.

`session_guard.py` — host-side часть этой Layer 1 границы: устойчивый маркер
занятости создаётся до запуска bridge. Production bridge публикует completion
receipt, привязанный к token/action, только после завершения handler и выхода из
mutex. Подтверждённый receipt исхода `no_cad` (отказ до отправки CAD-операции,
включая read-only выбор экземпляра до активации controller и доступа к модели) снимает
guard; завершённая ошибка с исходом `settled` оставляет маркер `settled_failure`.
Timeout, cancellation, malformed response, crash и ошибки custom scripts без доверенного
receipt остаются строгим `unknown_outcome`: завершение процесса не доказывает
отмену COM. Успешные custom scripts сохраняют прежний контракт; production-успех
тоже требует корректного receipt. Маркер блокирует обычные вызовы, включая readback. MCP и
Studio используют один default timeout (300 секунд), в том числе для
noninterruptible cleanup.

`get_cad_session_guard` читает состояние без COM.
`recover_cad_session(token, reason, confirm_idle=False)` требует свежего token:
для `settled_failure` выполняет эксклюзивный аудит с лимитом 15 секунд только уже
привязанного экземпляра KOMPAS, без создания экземпляра, активации controller или
документа, edit/rebuild/save/close. Аудит проверяет native responsive/enabled frame,
видимые стандартные диалоги, COM-список документов и API5 blockers: graphical
process, возможный sketch editor и in-place component edit. Результат содержит
ограниченный список документов и `model_verified=False`. Успех снимает маркер с
basis `completed_handler_and_session_audit`, но `cad_readiness_verified=False`:
до записи агент обязан проверить затронутый документ и partial changes, без
слепого повтора операции. Blocker сохраняет settled-маркер; пользователь разрешает
неустранённое UI-состояние. Если привязанный CAD-процесс уже завершился, settled-маркер
снимается без COM с basis `bound_session_exited`; перед новым CAD-вызовом требуется
явный выбор экземпляра, без автоматического подключения замены.
Для `unknown_outcome` восстановление остаётся без COM
и требует свежего явного пользовательского `confirm_idle=True` после подтверждения
idle UI и разбора partial documents. Это не общее решение асинхронной отмены и не
гарантия idle UI. Общая
папка задаётся `KOMPAS_MCP_SESSION_GUARD_DIR`; все клиенты одного KOMPAS должны
использовать одну папку. См. [порядок восстановления](docs/low-level-runtime.md#timeout-and-session-recovery).

`cad_session_policy.py` хранит общий host-контракт режимов `interactive`/`hidden`
рядом с guard. Native Layer 1 реализация — общий
`assets/bridge/cad_session_runtime.py`: selected HWND/PID/process creation time,
проверка отдельного owned process перед скрытием, единая видимость Documents.Add/
Open. Нет fallback Dispatch/DispatchEx при отказе выбранного документа. Host
закрепляет context token: смена режима другим клиентом между шагами workflow
останавливает следующий вызов, а не переключает его незаметно. Studio требует
interactive; hidden выбирается отдельно через host-only `set_cad_work_mode`.

Interactive сохраняет тот же видимый документ без Close/replace/reopen. Обычное
автоматическое закрытие подавляется; отдельная пользовательская команда закрытия
остаётся явной. Legacy конструкторы различают current saved readback и настоящее
save/reopen: при сохранённом открытом документе `recipe_reopened=false` и
`save_reopen_deferred=true`. Hidden сохраняет staged lifecycle только внутри
owned-сеанса. Отсутствие owned-сеанса в ROT — ошибка, не разрешение создать новый.
Реализация режимов проверяется fake-COM контрактами; native изоляция, ROT reattach
и interactive direct save требуют отдельной live-проверки. Per-entity animation
и pauses внутри одного построения не входят в этот контракт.

## Четыре слоя

### Layer 1 — атомарные инструменты и readback

Один вызов выполняет одну ограниченную операцию или чтение состояния.

Владельцы:

- `*_tools.py` — MCP schemas и регистрация инструментов;
- `adapter.py` — host-side orchestration и нормализация ответа;
- `bridge_runner.py` — изолированный запуск bridge;
- `bridge/kompas_bridge.py` — COM-вызов и непосредственный CAD readback.

Примеры: открыть документ, получить список features, создать sketch entity,
прочитать ограничения, сохранить модель.

Layer 1 не выбирает семейство детали и не строит длинную последовательность.

`body_geometry_tools.py` exposes read-only final-body inspection and measurement.
`body_geometry.py` owns selector validation and deterministic infinite-axis/plane
distance calculations (Layer 2). `assets/bridge/body_geometry_runtime.py` owns
Layer 1 COM readback from final `ResultBodies`, topology, component coordinate
transforms, face shape snapshots and the ephemeral native measurement calculator.
The checkout and packaged bridge load this one shared runtime file; it is shipped
by the existing bridge-assets package-data rule. Construction recipes are not
required. Explicit document/geometry selectors are strict; native, analytic and
sampled representations remain distinguishable. See [the user contract](docs/finished-geometry.md).

Bridge `dispatch` holds a named Windows mutex before accessing COM. Overlapping
MCP/Studio requests fail with `CAD_BUSY` rather than entering KOMPAS concurrently.
This is a process-level gate, not a workflow transaction or control over manual UI
actions/direct COM scripts. Geometry selectors include component/document update
stamps; readback checks do not silently rebuild or repair the inspected model.

### Layer 2 — детерминированная геометрия и проверки

Этот слой переводит пользовательские размеры в однозначную геометрию и
проверяет локальные инварианты до COM-вызова.

Владельцы:

- `sketch_runtime/` — сущности, frame mapping, topology, constraints и
  diagnostics;
- `sketch.py` — параметрические sketch plans и variable/dimension plans;
- `connect_curve.py` и `trimmed_curve.py` — правила составных кривых;
- `parametric.py` и `parametric_extension_legacy.py` — schema normalization,
  preview и геометрические ограничения;
- `rules/default.json` — текущие статические правила для существующих batch и
  quality workflows, но не универсальный Rule Engine.

Layer 2 не владеет документом КОМПАС и не должен сам выполнять COM.

Пилот общего CAD-контракта: `src/kompas_mcp/cad_modules.py` владеет
Layer 2 metadata registry (schemas, defaults, examples, units/frame, limitations)
и Layer 3 dispatch для `preview|plan|create|inspect`; поддержаны `gear_spur`,
`gear_internal`, `gear_bevel`, `chain_sprocket`, `cam` и `silent_chain_sprocket`.
Каждый descriptor ссылается на
существующие schema/preview/plan и семейные callbacks; новые семейства не добавляют
ветки в dispatcher. `cad_module_bindings.py` нормализует различия существующих API:
Пять ременных семейств (`v_belt`, `poly_v`, `flat_belt`, `timing_trapezoidal`,
`timing_curvilinear`) подключены через `cad_pulley_bindings.py`; используются
существующие Layer 4 managed plans и typed request models. Shared interface
остаётся create-only, без изменения существующих apply/update возможностей.
`GWP_RECIPE_*` — checksummed bounded creation metadata, не driving parameters и
не geometry-verification stamp. Полные входы сохраняются также при обычном создании
через adapter/Studio; старые блоки без полного рецепта не получают defaults.
Фактический объём плоского шкива читается из native body, а зубчатый массив
проверяется по объёму снятого материала. Ременные зубчатые шкивы занимают negative X;
V/Poly-V/flat — positive X. Detection changed inputs не заменяет новый geometry audit.
звёздочка использует prepared plan через `create_managed_pulley`, сохраняя его
post-build constraint verification, и проецирует managed inspection в общий формат.
Для кулачка `cams/module_contract.py` описывает типизированные входы, делегируя
инженерные проверки `cams/spec.py`; `cams/cad.py:execute_cam_plan` исполняет уже
рассчитанный план с прежней host verification/finalization цепочкой. Saved numeric
recipe доступен общему MCP независимо от наличия сохранённой формы Studio.
Зубчатая цепь использует существующий `SilentChainSelectionRequest` и план:
preview сохраняет completion, а `ModuleInputRequired` возвращает недостающие
инженерные входы без COM и автоматического принятия предложений. Discovery defaults
не заполняют обязательное обозначение/число зубьев. Проверка снятого массивом
материала остаётся в native runtime (`PATTERN-001`); source warnings доступны и
при распознавании сохранённой модели, без утверждения о новой geometry verification.
`src/kompas_mcp/module_tools.py` публикует MCP-адаптеры
`get_cad_module_contract` / `run_cad_module`, а `geomwright.model` и
`geomwright-model` используют тот же dispatcher без MCP-сервера.
Построение и проверка остаются у существующих Layer 4 family runtimes:
Новых CAD-алгоритмов, update/apply, общей композиции и новых блоков Studio нет.
Конические сечения используют существующий C2-интерполятор с одиночными узлами;
Studio fingerprint учитывает gear sources, чтобы не переиспользовать старый генератор.
`inspect` читает сохранённое распознавание, а не выполняет новый geometry audit;
recreate передаёт возвращённые parameters в новый create-only build только при
`data.recreatable=true`; без восстановимого рецепта parameters равен null.

Экспериментальная интеграция легаси-пружин: `cad_spring_bindings.py` владеет typed
compression inputs и Layer 3 adapter для цилиндра, двух зон и конуса. Расчёт и CAD
остаются в `parametric.py`/legacy preview и `_build_compression_spring_feature`.
У этого descriptor `creation_policy=saved_unique_export_then_open`: новый файл в
export directory, прежняя post-save anchor finalization, затем строгое открытие
результата. На bridge стороне сохраняется bounded checksummed `CSPR_RECIPE_*`;
private `inspect_compression_module` проверяет рецепт и профиль/sweep roots без
новой публичной атомарной команды. Creation readback дополнительно сверяет фактический
объём после reopen с объёмом до save/bindings; обычный inspect не является geometry audit.
Axis — global X; нового Studio блока нет. Рассогласование фаз левовитых сегментов
исправлено и проверено на двухзонной пружине с начальной фазой30. Дополнительно
до save проверяется `IFeature7.Valid`: `ObjectError=31` возвращается как
`CAD_SELF_INTERSECTION`, даже если Update и cached volume успешны. Новый общий
контракт явно задаёт `end_pitch_gap=0.01`: driving `EG1`, derived `EP1=WD1+EG1`,
формулы длины концов и шлифовки. Проволока не уменьшается; legacy без поля и старые
рецепты сохраняют нулевое значение. Переход0.01→0.02 проверен rebuild/save/reopen.
`standard_length` — физическая длина в legacy-модели, `height`/legacy `free_length`
— осевой размах центров. Интеграция общего генератора проверена; без нового Studio
блока это не завершённый трёхкомпонентный модуль.

`cad_extension_bindings.py` подключает существующий legacy `extension_spring`
как Layer 2 typed planning adapter и Layer 3 callbacks. Общая saved-create цепочка
используется совместно с compression; native recipe helper сохраняет отдельные
`ESPR_RECIPE_*` и private `inspect_extension_module`. Проверяются native coil
diameter/pitch/height/hand, wire parameter, valid sweep, positive solid и recipe/
volume после reopen. Поддержан существующий composer восьми семейств с независимым
left/right выбором, включая завершённые self-wrapping/bent-ring конструкции.
Повторная bent-нормализация не заменяет уже собранные side fragments. Генератор
по-прежнему владеет эскизами и driving-формулами; новый Studio блок не добавлен.

`cad_torsion_bindings.py` подключает уже реализованный torsion workflow через
Layer 2 typed planning и Layer 3 saved-create callbacks, используя общую цепочку
пружин и отдельный `TSPR_RECIPE_*`. Private `inspect_torsion_module` читает
рецепт/roots, а creation readback дополнительно проверяет native coil и исходные
координаты прямых плеч. Existing legacy API неизменён; нового Studio блока нет.

`cad_disc_bindings.py` подключает legacy rotational `disc_spring` через typed
Layer 2 plan и Layer 3 saved-create callback. `DSPR_RECIPE_*` отделён от других
семейств; private inspect проверяет sketch/rotation roots. Creation readback
сверяет native диаметры, bounds и объём с аналитическим профилем после reopen.
Legacy driving-связи радиусов/высоты не гарантируют корректное редактирование:
контракт create-only требует пересоздания по входным параметрам, а рецепт не
сертифицирует driving-параметризацию. Нового Studio блока нет.

`cad_diaphragm_bindings.py` подключает завершённую legacy diaphragm цепочку:
Layer 2 typed inputs/plan делегируют существующим previews; Layer 3 saved-create
исполняет workflow базы, tangent plane, опорных точек, slot/relief cuts и массива.
`DIAPR_RECIPE_*` хранит входы отдельно от других пружин. Ownership исходных cuts
читается из `ICircularPattern.InitialObjects`, а не из всей коллекции Extrusions,
содержащей одноимённые копии. Проверяются снятый массивом материал, bounds и
native volume/recipe после reopen. Общий result допускает семейные `diagnostics`;
здесь они содержат фактические состояния каждого эскиза. Нового Studio блока и
in-place editing нет; полная определённость всех сохранённых эскизов не заявлена.

`cad_shaft_bindings.py` подключает legacy stepped_shaft как Layer 2 typed plan и
Layer 3 saved-create adapter. Общий checksum helper `_creation_module_recipe`
используется через сохранённые spring compatibility wrappers; shaft имеет
отдельный `SHFT_RECIPE_*`. Проверяются каждый цилиндр по trimmed boundaries,
объём, bounds, полная определённость нового профиля и save/reopen. Existing
fix_sketch_placement фиксирует положение эскиза, не driving-геометрию.
Текущий этап включает только конструкторы собственных тел: stepped shaft,
external conical/polygonal/flat bodies. Операции над внешним телом и резьбовые
цепочки отложены до отдельного рефакторинга construction chains; legacy APIs
не удаляются. Новый Studio блок и общий apply/update контракт не добавлены.

`cad_cone_bindings.py` подключает external_conical_step через тот же saved-create
rotational adapter, сохраняя пять способов задания входов в `ECON_RECIPE_*`.
Расчёт и builder остаются legacy; native readback сверяет радиусы обоих trimmed
торцов и длину. Общий адаптер локально заменяет некорректный axial circle_diameter
на driving line_length осевой; старый scenario API не меняется. Input angle/
conicity вычисляют resolved D1/D2/L1, но не заявлены как отдельные CAD driving
variables. Все пять corrected modes проходят создание и save/reopen, включая
one-diameter conicity после перезапуска; см. family contract.

`cad_polygon_bindings.py` подключает legacy external_polygonal_step: Layer 2 typed
inputs/plan и Layer 3 callbacks общей `create_legacy_body_module` цепочки; Layer 4
builder остаётся существующим legacy generator. `EPOL_RECIPE_*` хранит исходные
входы. План сверяет native YOZ→global vertices, bounds и аналитический объём.
Локальная коррекция убирает horizontal lock и избыточные касания, добавляет driving
POLY_A1 и связывает длину с native Distance 1/2. Число сторон, трактовка диаметра,
направление и переход угловой ветви требуют пересоздания. Interactive saved-readback
не называется fresh reopen; inspect не является новым geometry audit.
См. [family contract](docs/external-polygon.md). Нового блока Studio и общего
in-place/apply API нет; это интеграция генератора, не полный трёхкомпонентный модуль.

`cad_flat_bindings.py` подключает external_flat_step: Layer 2 typed inputs и
аналитический retained-strip plan; Layer 3 использует общий legacy-body lifecycle.
Layer 4 остаётся legacy builder. Private bridge сохраняет `EFLT_RECIPE_*`, читает
уникальные sketch/extrusion roots и bounded final cylinder/plane boundary points.
Host verifier сверяет радиус, плоскости лысок/торцов, chord vertices, bounds и объём.
Одно-/двухлысочная геометрия и D/L/F drivers проверены отдельно; общий stdio-MCP
create/inspect и explicit reopen проверили полный EFLT recipe, roots и code1 для
одно-/двухлысочной формы. Sketch canonical name применяется до initial Update и
параметризации, а не переименовывается после построения; см. OP-003.
См. [family contract](docs/external-flat.md). Новых Studio/apply/in-place возможностей нет.

`kompas_mcp/cams/` owns host-only lift laws, fixed-arm rocker kinematics,
contact envelopes, timing conversion, and sampled geometric diagnostics.
Its contact-aware `curvature_spline` is a direct-flat-only Layer 2 synthesis:
positive piecewise-linear curvature integrates the support ODE analytically,
enforcing C2 flank/nose matching and a bounded monotone family search with
optional analytic acceleration/jerk limits. Tappet
edge reach is a separate finite-face check; no dynamics optimizer or COM is involved.
Its separate `motion_spline` family integrates piecewise-linear valve acceleration
into cubic C2 spans, solving lift/velocity endpoint conditions with a shared nose
acceleration. A fixed 48-shape budget is filtered by exact angular derivative
limits, then by the actual follower/contact geometry; promising candidates receive
a denser sampled contact check. This is bounded host-only synthesis, not a global
optimizer or an application of the flat support ODE to rockers. `bounded_auto`
compares standard laws and these eligible synthesis families without relaxing inputs.
`geomwright/studio/camshaft.py` owns the three-step presentation adapter.
The kinematics view is an explicitly labelled illustrative layout, not the
calculated manufacturing contour. The separate Cam view uses the Layer 2
profile. Its create-only Layer 4 CAD family uses the same Layer 2 calculation
for Studio and the public `create_cam` tool. Host-side `cams/cad.py` owns
preflight, arc-length cubic interpolation and verification; the bridge owns only
the native NURBS/base arc, extrusion and actual curve/body readback. It creates
one new part, not a shaft assembly, and exports sketch/feature references for
subsequent standard operations. The numeric profile is not sketch-parameterized;
changed inputs require a new build. Studio recognizes a persisted `GW_CAM_VERSION`
and `CAM_*` fingerprint with the two root operations as a read-only block.
Version-2 metadata retains a bounded, checksum-verified calculation recipe and
optional Studio form; Studio restores it only into a new-part draft. Read-only
`inspect_cam` exposes the recipe to MCP. Legacy version-1 blocks remain readable
without pretending their original recipe or verification stamp can be recovered. Native creation leaves
`CAM_VERIFIED=0`; after host checks, a strictly targeted finalization verifies curve
identity and body bounds again before publishing `CAM_VERIFIED=1`. Errors carry
owned-document partial-result diagnostics; cancellation is not a rollback.
The final curve is checked against held-out contact samples, base tangency,
cubic stationary curvature points, sampled self-intersection and global
flat/roller contact recovery at sampled follower positions. Contact extrema use
the continuous cubic/base curve; pressure angles use all source-grid positions.
Bounds, extrusion direction, positive single-solid volume and rebuild are read
from KOMPAS; save/reopen acceptance covers direct C2 and rocker examples.
Engineering limits are strict with independent numerical comparison floors;
CAD tolerance only bounds profile/contact accuracy, not curvature or finite-face
slack. Contact-angle and topology checks are sampled rather than a global
manufacturing proof. Studio's Cam view
and CAD preflight use the same 10-samples-per-degree synthesis density.
The Layer 2 preview also returns a complete `motion_chart` command curve including
lash ramps, with sampled S/V/A/J, separate net valve lift, stage windows and
derivative-break metadata. Studio renders it without numerical differentiation;
the chart coordinate is valve-side lift for rockers, not roller-centre motion.
Its graphical view never launches bridge and labels stale data after input errors.
Its user contract and verification limits are in [English](docs/en/camshaft.md) and
[Russian](docs/ru/camshaft.md).

### Layer 3 — управляемые workflows

Layer 3 собирает атомарные операции в последовательность с явными references,
preflight, snapshot/readback и fail-fast поведением.

Владельцы:

- `workflow.py`, `workflow_tools.py`, `composition.py`;
- managed parametric workflow в `parametric.py` и bridge executor;
- `spring_tools.py`, `spring_catalog.py`, `size_catalog.py`;
- scenario-specific orchestration в adapter/bridge.

Базовый цикл:

```text
Plan → Execute → Verify → Correct
```

`Correct` означает ограниченную детерминированную коррекцию либо остановку с
диагностикой. Универсального OperationGraph, транзакционного rollback между MCP
вызовами и автоматической компенсации сейчас нет.

Согласованный план цепочек модулей: [English](docs/en/construction-chains.md) /
[Русский](docs/ru/construction-chains.md). Первый этап — MCP-only последовательность
в одной детали с одним итоговым телом. Layer 3 владеет документом, порядком,
привязками и передачей актуальных участков; семейство — своей геометрией и
поддержанными способами получения основы. Пространства имён и принадлежность
различают экземпляры; 3D-макроэлементы требуют отдельной live-проверки до обязательной
группировки. Валовая цепочка A–C и начальная зубчатая основа с продолжением D
реализованы в `construction_chains.py`:
Layer 2 нормализует участки и размещение, Layer 3 передаёт одно ограниченное
CAD-задание. `assets/bridge/construction_chain_runtime.py` исполняет существующие
rotational builders, проверяет актуальное тело после каждого шага и сохраняет
checksummed рецепт. `gear_spur` использует зарегистрированный семейный план с
C2-интерполяцией (native order 4); последующая обработка выбирает сплошное ядро
до окружности впадин, не зубья. Макроэлементы включают только собственные корни;
группировка, rebuild, save/reopen и Destroy проверены живым CAD. MCP предоставляет
`get_construction_chain_contract` и `run_construction_chain` с действиями
plan/create/inspect/rebuild/continue; create/rebuild создают новую деталь.
Continue адресует точный открытый сохранённый chain-документ, принимает только
новые шаги, перечитывает и проверяет неизменяемый префикс и актуальную геометрию
до записи, затем сохраняет тот же файл. API7 GetObjectId/FindObjectById сохраняют
идентичность корней при смене runtime Reference после reopen; поиск только по имени
не используется, но canonical names проверяются строго. Изменение старых шагов и
standalone-цели отклоняются; inspect распознаёт рецепт, не выполняя новую геометрическую
проверку. Live-приёмка D ограничена прямозубой основой m2/z20/b20, цилиндрической
ступицей, двумя вырезами отверстия и добавленной торцевой проточкой. Первая часть E
подключает `external_polygonal_step` для own/create и own/add через существующий
семейный план и builder. `chain_prism_runtime.py` — общий адаптер polygon/flat guard/build/readback,
не новый движок: численная опорная точка, параллельная YOZ-плоскость и полностью
определённый профиль принадлежат своему макроэлементу. Carrier — вписанное ядро;
проверка актуального тела сопоставляет боковые плоскости, точный поперечный габарит
и объём, а не ищет фиктивную цилиндрическую грань. Проверены вал/шестигранник/осевой
вырез, continue торцевой проточки после reopen, обратный повёрнутый пятиугольник
со смещением и цилиндрическим продолжением. `external_flat_step` использует ту же
принадлежность опор и проверяет реальные плоские и цилиндрические поверхности.
`chain_holes_runtime.py` подключает существующий `bolt_circle_holes` как input/remove
к явному carrier: без пересоздания основы, с локальной осью исходного выреза,
массивом, проверкой всех off-axis цилиндров и root source/count/axis. Native readback
центра использует проверенные управляющие координаты, не информационные смещения.
Скрытие касается только собственных корней, не безымянных производных эскизов массива.
Проверены save/reopen и continue общей shaft/flat/bore/holes цепочки.
`straight_spline` подключает существующий численный план ГОСТ 1139-80 как
начальную наружную основу, не новый генератор. Общий tooth-foundation workflow
исполняет его корни, использует `_verify_straight_spline_metrics`, читает контур
паза и сохраняет fingerprint боковой шлицевой зоны. Последующие цилиндрические
ступени на +X и вырезы внутри сердечника не пересоздают through-all паз;
persistent-root и actual-body проверки сохраняются при continue/reopen.
Каталог и нестандартные размеры остаются у семейства; местный sampled disk-guard
проверяет согласованность плана, но не заменяет точный расчёт и native audit.
Другие резьбовые режимы, шлицевые втулки/более широкая обработка основы и Studio впереди;
rollback частичного результата отсутствует.
Наружные шлицы на входном валу подключены как единственный завершающий
`straight_spline` input/remove шаг. Публичный контракт требует необработанного
rotational prefix, явного одного +X цилиндра диаметра D и положительных гладких
запасов с обеих сторон рабочего span; фаски и выход инструмента не входят.
`connections.cad._plan_straight_spline_input_shaft` переиспользует точный семейный
контур/площадь, исключает blank и фаски, задаёт профильную плоскость в начале
рабочего участка и конечную длину выреза вместо through-all. Layer 2
`construction_chains._straight_spline_input_carrier_guard` связывает канонический
необработанный rotational prefix с одним +X цилиндром и выделяет соседний
защищаемый материал, включая гладкие части выбранного цилиндра. Bridge содержит
частный finite-depth gate для `_execute_workflow_operation`: конечный вырез доступен
только с отдельным аргументом вызывающего кода, тогда как обычный workflow сохраняет
through-all-only. Проверяются выбранная сторона, оба типа окончания и фактическая
глубина operation variable. Применение в отдельном эксперименте на [10,30] внутри
цилиндра длины50 с соседней ступенью прошло mass/pattern/span/protected-face audit,
save и actual reopen. Для назначенной parallel-plane CoordinateSystem нормальная
сторона соответствует +X; отрицательный reverse-пример сохранён отдельно.
Native `_straight_spline_input_carrier_guard` проверяет префикс, смысл ограниченного
source-free плана и контур через общий `_spline_space_guard` начального вала;
каталог и каноническая генерация остаются host-owned. Read-only
`_straight_spline_input_carrier_context` сверяет saved recipe/expectations,
persistent ownership, необработанное тело/объём и переиспользует точное разрешение
цилиндра с его торцевыми гранями. Проверка отдельного сохранённого префикса до и
после actual reopen подтверждает шесть persistent-ID и неизменные байты/Changed=False.
Контекст не годится для уже обработанной модели и не создаёт новые операции.
`chain_spline_runtime` применяет source-free план через этот контекст,
переиспользуя создание сущностей, конечный вырез и круговой массив. Он владеет
семью явно созданными корнями, группирует/скрывает только свои объекты, сохраняет
принадлежность исходных операций и проверяет профиль, источник/ось массива,
материал одного/всех пазов и выборочную границу рабочей оболочки. Реальный драйвер
`CH_<ID>_L1` связан с native Distance1; проверены 20→22→20, сохранение и actual
reopen того же входного файла без пересоздания основы. Числовой поперечный профиль
остаётся create-only. Runtime не сохраняет модель; chain caller сохраняет компактный
поддерживаемый рецепт и `spline_audit`. Versioned spline checkpoint содержит hashes префикса/
входов/guard, original-stock baseline, profile stamp и sampled working-zone hash.
Инвентарь связывает копии extrusion по native OwnerFeature → Exemplar → своему
массиву и persistent-ID; координатные записи без ID проверяются отдельной строгой
политикой, не объявляясь owned roots. Pure checkpoint/refusal проверки и live
prepare → metadata-only save → actual close/reopen прошли на том же обработанном
образце `8x36x40`, X=[10,30], без повторных вырезов. Свежий аудит подтвердил полный
инвентарь, исходные persistent-ID, профиль, драйвер и защищённые грани;
`Changed=False`. Публичные create, добавление к отдельно сохранённому валу через
continue, actual close/reopen с inspect и source-preserving rebuild затем проверены
на новых моделях: стандартный `8x36x40` и нестандартный z8/d35/D40/b6/r0,3.
Inspect этой terminal-ветки всегда выполняет свежий геометрический/ownership/driver
аудит при creation inputs. Старые частные pending-примеры не конвертируются в публичный
рецепт автоматически. Для наружной ветки последующие шаги, открытые торцы и reverse отклоняются.
План не является разрешением исполнять его прежним through-all
executor. Внутренний профиль не используется этой адаптацией. Ошибка отдельной
втулки исправлена в Layer 2 семейства: её паз является номинальным негативом
оставшегося зуба вала с общим корневым переходом у d, а не повторением межзубного
сектора. Проверены совпадение границ/точная площадь пары, стандартный и custom
CAD create/save/reopen с readback. Ревизия hub-профиля 2 хранится в checksummed
рецепте; старые втулки остаются recreatable, но flagged legacy_hub_profile и
verified=false. Это номинальная сопрягаемая геометрия, не профиль инструмента или
проверка предельных посадок. Внутренняя input/remove ветка теперь использует тот же
bounded executor/checkpoint для одного +X цилиндра и его явного полного сквозного
отверстия d. По умолчанию/при exit_mode=through рабочий span равен span отверстия, без offset;
наружный диаметр наследуется из неизменяемой основы, не из default-wall эвристики.
Native guard проверяет шесть сущностей номинального ответного профиля ревизии 2
и связывает длину выреза с драйвером отверстия. Сохраняется наружная цилиндрическая
стенка; торцевые кольца закономерно меняются. Max/min рабочий радиус, точное снятие
материала и полный инвентарь проверяются отдельно. Standard create/continue/inspect/
rebuild и actual reopen, а также custom create/reopen прошли; исходные root ID и
байты источника rebuild сохранены. Ранее сохранённая наружная цепочка прошла свежий
аудит новым runtime. Явный exit_mode=blind поддерживает тот же канонический префикс
с плоскодонным отверстием: вырез от открытого входа короче глубины отверстия,
оставляет положительный гладкий остаток и материал за дном. Независимый native
драйвер длины не связан с глубиной исходного отверстия; flat numeric окончание
проверяется по одному/всем торцевым пазовым граням и точному снятию материала.
Checkpoint защищает наружную стенку, диск дна и задний диск; отдельно проверяются
аналитические свидетели гладкого остатка. Standard create/continue/rebuild/actual
reopen и custom create/reopen прошли, как и изменение длины20→22→20 с восстановлением
исходного checkpoint, save и actual reopen. Это не сбег инструмента и не сертификация
полезной длины изготовления. Последующие операции и произвольные входные тела не поддержаны.

Подготовка физической резьбы разделяет native `_build_helical_thread_feature`
(legacy-создание исходного участка и разрешение граней) и
`_apply_helical_thread_feature` (тот же винтовой вырез по уже разрешённым
base/start/end граням, без пересоздания carrier-а). Вызывающий workflow отвечает
за актуальность граней, span-preflight и установку profile variables. Это внутренняя
граница исполнения, не отдельный MCP-инструмент; ограниченный chain-режим описан ниже.
Наружная M20×2,5 на Ø20×20 даёт одинаковую геометрию в source-free и standalone
прогонах после реального reopen. Фазовая проверка уточнила прежний диагноз code2:
профиль сохраняет code1 до инспекции, а `BeginEditEx(True)` сам меняет native state
на code2 без Changed. Read-only инспекция/подсчёт теперь читают отдельный
`WriteToFragment`-экспорт, закрывают его, удаляют временный файл и восстанавливают
активный документ без открытия определения источника. References сущностей в таком
ответе принадлежат экспортированному фрагменту, не исходному эскизу; coverage явно
отделяет геометрию от недоступных API5-связей. Изменение шага2,5→2→2,5 проверено
геометрией/объёмом и code1 после reopen. Chain-приёмка дополнительно проверяет
винтовой span, выбранный carrier, принадлежность корней и защищённый материал.
Внутренний `_verify_external_metric_thread_geometry` проверяет ограниченный случай
полного наружного цилиндра на +X (2–64 витка): native габариты/объём, оболочку
снятия материала и sampled trimmed edges с фактическим знаковым шагом. Требуется
винтовая граница, достигающая обоих концов; это строгий gate этого случая, не
универсальный критерий любой обрезанной резьбы. Короткий левый вырез исправлен
зеркальным совмещением пути с неизменной XY-плоскостью профиля: `TurningAngle=180`
только для наружного цилиндрического `metric_v60` на +X. Автоматический радиус
скругления корня теперь выражен через текущие width/depth drivers, а не начальное
число; явный радиус остаётся постоянным. Новые правый/левый M20×2,5 на Ø20×20
проходят span/шаг/глубину/code1, изменение шага2,5→2→2,5 и reopen. Частичные участки
остаются неподдержанными; полный carrier составной основы проверяется адаптером
цепочки. Legacy-построение использует те же исправленные фазу/формулу.
Внутренний host `_metric_thread_carrier_guard` потребляет уже проверенный план
цепочки и параметры семейства: явный цилиндрический constructor target целиком
на открытом конце +X, без предыдущих вырезов, только rotational stock; все прочие
секции строго внутри радиуса корня и позади начала резьбы. Диаметр не подменяется
номиналом, основа не пересоздаётся/не изменяет размер. Native-эксперимент на
Ø12×12 + Ø20×20 с левой резьбой второго участка подтверждает full-span и сохранение
площади/радиуса/границ двух защищённых поверхностей после выреза и reopen, с одной
исходной операцией вращения. Это отдельное bounded свидетельство, не exact BREP
и не отдельный способ интеграции: актуальные грани, persistent ownership,
grouping и continue принадлежат общему native-адаптеру.
Его предзаписная часть `_thread_carrier_context` уже использует общий `_validate`,
сравнение сохранённого рецепта/expectations, `_ownership` с persistent-ID и
каноническими именами, `_read_body`/`_verify`. Она разрешает текущий final-body
цилиндр по точному span/radius и оси X, а торцы — по axial plane и trimmed circular
boundary. Контекст содержит свежие COM-грани и проверенный префикс; грани нельзя
сохранять через rebuild/вырез. На реальной двухшаговой цепочке подтверждены четыре
корня и две группы после reopen, отказ при подмене рецепта и отсутствие Changed.
Флаг `thread_executed=false`: установки резьбовых переменных, новых owned roots,
post-cut audit и изменения сохранённого рецепта этот контекст не выполняет.
Следующий внутренний слой `chain_thread_runtime` уже выполняет подтверждённый
source-free вырез по этому контексту: caller-owned `CH_<ID>_*` variables,
повторное разрешение граней после установки переменных, inventory до/после,
строго семь новых корней и группировка только их через общий `_group_step`.
Перед/после группировки проверяются фактические винтовые кромки, глубина, оболочка
снятия материала и аналитические площади/границы защищённых поверхностей; общий
`_ownership` сохраняет префикс и выдаёт persistent-ID новым корням. Read-only
`audit_drivers` проверяет реальные значения/флаги входов и выражения Step/Height,
включая reopen. Правая/левая M20×2,5 на двухшаговой основе подтверждены с изменением
шага2,5→2→2,5, code1 и reopen. Host `_adapt_preview` сохраняет локальный профиль,
перемещает span и удаляет legacy-создание/связывание основы. Исполнитель не сохраняет
документ и не обновляет рецепт сам: это делает общий chain-runtime. Старые
диагностические копии помечены pending и отвергаются распознавателем поддержанных
цепочек; другие CAD-изменения входов не сертифицированы.
Для этой интеграции выделен внутренний `thread_audit` checkpoint: hashes исходного
плана/семейного preview/guard, persistent ownership, компактные габариты и защищённые
поверхности исходной основы, фактически измеренные объём и снятие материала.
Расчётная верхняя граница оболочки не выдаётся за расчётный объём винтового выреза.
`audit_checkpoint` повторно проверяет текущие корни, отсутствие последующих/чужих
корней, геометрию и драйверы при исходных входах; общий чистый `_thread_carrier_guard`
не пытается перечитать обработанное тело как исходную вращательную основу.
Checkpoint сохраняется в финальном checksummed рецепте. Публичный
`ConstructionChain` включает `external_helical_thread`: только завершающий input/remove,
по умолчанию полный явный открытый цилиндр на +X, target start/zero offset, 2–64 витка,
автоматический круглый корень и без предыдущих вырезов. Схема не позволяет
неявно изменить диаметр/длину основы. План хранит None для расчётного объёма резьбы;
native-аудит выдаёт фактически измеренный итог. Общий runtime строит обычный префикс,
записывает его checkpoint только в память перед вырезом, затем сохраняет финальный
рецепт без промежуточного stock-файла. Create/continue, actual reopen/fresh inspect
и rebuild в новую деталь с неизменным источником проверены на правой/левой M20×2,5
на Ø12×12 + Ø20×20. Inspect резьбового рецепта выполняет свежий ownership/geometry/
driver-аудит исходных входов; обычные рецепты по-прежнему только распознаются.
Опциональные `entry_mode="through"` и `exit_mode="blind"` разделяют условия
входа и глухого выхода; отсутствие полей сохраняет прежний рецепт и поведение.
Layer 2 `_plan_metric_thread_end` вычисляет проекцию конечного сечения и
формулу высоты спирали; carrier guard различает полный носитель и рабочий участок.
Native snapshot контролирует исходные вращательные поверхности вне рабочей
оболочки и защищённые грани с обеих сторон. Checkpoint связывает последний след,
проекцию неполного окончания и гладкий остаток, не выдавая их за сертификацию
полного рабочего профиля. Публичные create, same-file continue, reopen/inspect и
source-preserving rebuild проверены для M20×2,5 на Ø12×12 + Ø20×20 + Ø30×12.
Явный `exit_mode="through"` требует полный носитель и свободное пространство
либо основу внутри радиуса корня со стороны выхода. Native-аудит требует две
полные наружные и две корневые касательные границы, без конечного сечения в
материале. Checkpoint связывает эту проверку и расчётную проекцию резца вне
носителя. Публичные create/continue/reopen/inspect/rebuild проверены на M20×2,5
с выходной шейкой и свободным торцом; отсутствие полей сохраняет старые рецепты.
Глухой вход, плавный сбег и канавки не включены.
NewDocument возвращает базовый IKompasDocument: перед чтением TopPart новый документ
явно приводится к 3D-интерфейсу. Первый остановленный префикс сохранён, проверен и
продолжен в том же файле после явного восстановления сессии, без пересоздания основы.

Внутренний Layer 2 `_prepare_internal_metric_through_preview` в `parametric.py`
подготавливает версионированный круглый метрический профиль с номинальным драйвером
диаметра и неизменяемым входным отверстием. Глубина реального реза отделена от
виртуальной вершины боковых сторон (`THREAD-001`); формулы эскиза и высоты спирали
используют те же отношения. Адаптер удаляет создание и связывание исходной основы,
не вызывается прежней standalone-нормализацией. Публичный шаг цепочки
`internal_helical_thread` использует этот метод с явно сохранённым
`method_version=1`, сквозным входом и сквозным либо глухим выходом. Подготовленный план сам по себе
не подтверждает фактическую геометрию.
В изолированных правой/левой моделях подтверждены реальные драйверы: шаг2,5→2,
номинальный диаметр20→20,2 и восстановление20/2,5 при неизменном отверстии.
Фактические выражения Step/Height, геометрия и fully-defined профиль проверены
после сохранения и реального повторного открытия. Изменение шага на фиксированном
отверстии не выдаётся за соответствие стандартному диаметру отверстия нового шага.
Layer 2 `_internal_metric_carrier_guard` сверяет канонический префикс из одного
цилиндра и одного полного цилиндрического выреза, явный bore-target, +X span,
диаметр неизменяемого отверстия, положительную стенку и верхнюю границу снятия.
Native verification flags остаются false: этот preflight не заменяет readback
граней или persistent ownership/checkpoint-аудит будущего внутреннего шага.
Native `_internal_metric_carrier_guard` повторно проверяет смысл префикса и guard
без COM; `_internal_metric_carrier_context` сверяет saved recipe/expectations,
persistent ownership и текущее исходное тело. Общий read-only
`_resolved_cylindrical_thread_faces` выбирает точный цилиндр по радиусу/span/оси и
его торцевые грани; этот выбор переиспользуется внешним контекстом без изменения
его условий допуска. На обычной сохранённой цилиндрической основе со сквозным
отверстием проверены actual reopen, неизменные persistent-ID, dirty state и байты
файла. Контекст не вырезает резьбу, не записывает metadata и не сертифицирует
сохранность материала после будущего реза; ссылки на COM-грани нужно получать
заново после любого перестроения.
Внутренняя ветка `chain_thread_runtime` переиспользует новый carrier context,
namespaced instance inputs, инвентаризацию семи новых корней, группировку и
persistent checkpoint. Отдельный radial shell-аудит требует две полные границы
на радиусе отверстия и две касательные границы корня, положительное снятие,
неизменный внешний цилиндр и отсутствие материального конечного сечения.
Snapshot хранит максимальный радиус внутреннего реза; драйверы и ориентация
проверяются независимо. Старые external checkpoint и внутренние legacy-сценарии
не переключаются на этот метод. Вырез, группировка, сохранение компактного
checkpoint и свежий аудит после реального закрытия/открытия подтверждены live для
правой/левой M20×2,5 в Ø36×20 основе с полным отверстием. Диагностическая упаковка
сохраняет хеши планов и checkpoint в существующем лимите metadata; полные планы
остаются внешним evidence. Первый отказ oversized metadata был восстановлен после
свежего подтверждения idle: готовый вырез перечитан и сохранён без повторного
построения. Pending-метка по-прежнему отвергается публичным распознавателем цепочки.
Публичная `ConstructionChain` теперь включает завершающий внутренний input/remove
шаг с target на полное отверстие, а не наружный конструктор. Общая host/native
terminal-ветка сохраняет префикс и измеренный checkpoint в финальном поддерживаемом
рецепте; прогноз объёма резьбы остаётся None. Создание левой M20×2,5, same-file
continue правой, реальное повторное открытие со свежим inspect и source-preserving
rebuild левой в новую деталь подтверждены на Ø36×20 с отверстием Ø17,29367061317363.
Проверены старые внешние through/blind/omitted рецепты без изменения их файлов.
Обычные внутренние standalone-рецепты и pending-примеры не продвигаются на новый
метод автоматически. Коническое дно сверла, управляемый сбег, многосекционные основы и
последующие операции остаются вне публичного контракта этого этапа.
Внутренний Layer 2 `_plan_internal_metric_end` отдельно вычисляет сквозное либо
глухое окончание из неизменённого full-bore профиля версии1 и явных интервалов
основы/отверстия. Он возвращает формулу Height, последний след, проекцию конечного
сечения, гладкий остаток и материал за дном; input preview не меняется. Сквозной
результат совпадает с прежним значением/выражением, а глухой требует положительного
остатка до конца отверстия. Планы проверены на сохранённых native evidence обеих
рук в сквозном и плоскодонном отверстии. Private host/native guard глухого окончания
внутри полного сквозного отверстия переиспользует канонический through-носитель,
но различает физический span и рабочий участок. Общий snapshot/checkpoint-аудит
проверяет конечное сечение, гладкий остаток и защищённый выходной торец вместе с
наружной поверхностью. Checkpoint сохранён в двух существующих pending-примерах
без новых вырезов; свежий аудит после actual reopen подтвердил запись, владельцев,
объём, драйверы и исходное окончание. Эта проверка предшествовала публичной интеграции.
Частный flat-bottom guard теперь отдельно связывает полную цилиндрическую основу,
глубину отверстия и рабочий участок; public through guard не расширен. Snapshot
защищает наружный цилиндр, диск дна и задний диск по span, радиусам обрезанных
границ и аналитическим площадям. Checkpoint связывает положительный зазор от
последнего следа до дна и толщину материала за ним. Два уже построенных pending
примера обеих рук с отверстием20 в основе24 и последним следом18 прошли свежий
аудит, запись checkpoint и actual close/open без новых вырезов. Публичный
`exit_mode="blind"` теперь использует тот же guard/checkpoint без специального
резца: family preview готовится на полный bore-span, затем отдельный endpoint plan
задаёт рабочую длину, её input variable, end origin и Height expression. Проверены
левая create/reopen/inspect/source-preserving rebuild и правая same-file
continue/reopen/inspect в плоскодонном отверстии, а также правое создание/повторное
открытие глухого окончания в сквозном отверстии. Старые внутренние through обеих
рук и внешние through/blind/omitted прошли свежие read-only аудиты с неизменными
хешами файлов. Through остаётся default; pending-примеры не продвигаются автоматически.

### Layer 4 — законченные семейства деталей

Layer 4 задаёт публичный контракт целого CAD-модуля: параметры, дерево операций,
формулы, readback и канонические варианты.

Требования к новым законченным модулям определяет регламент:
[English](docs/en/module-development.md) / [Русский](docs/ru/module-development.md).
Он связывает блок Studio, общий генератор и независимый MCP, задаёт режимы ввода
и критерии готовности. Параметризуется всё, что рационально параметризовать;
исключения обосновываются для конкретных эскизов/операций (`SKETCH-001`).
Текущие возможности перечисленных ниже семейств остаются такими, как описано
в их контрактах; требования к новой работе не меняют их runtime-статус.

Текущие семейства:

- ступенчатые/конические и thread-related parametric parts;
- compression, conical, torsion и extension springs;
- disc/Belleville springs;
- diaphragm spring: flat, single-bend и S-bend, circle/oval relief, through-all
  cuts и multi-source circular pattern.

Mechanical transmissions have an approved Layer 4 managed-pulley workflow in
progress. Its architecture is defined in
`docs/transmission-platform-concept.md`: functional members compose with generic
hub/bore/keyway modules through semantic references, while native Shaft/GEARS
commands remain black-box research oracles.
The implemented V-belt Layer 3 member may append an optional post-cut `IFillet`
manufacturing feature for upper groove edges; the functional cut sketch and its
sharp-profile analytical verification remain separate from that feature.
Its Layer 2 catalog keeps `din_iso` and `gost_20889_88` as independent standard
systems; dimensions, angle schedules, and standard fillet radii are never mixed
implicitly across systems.
The separate Poly-V Layer 2/3 member owns ISO 9982:2021 PH/PJ/PK/PL/PM data and
builds nominal `rt` plus deterministic maximum-`rb` rounded profiles directly in
one fully defined master/dependent cut sketch. Pitch, both radii, angle, linked
blank radius/width, axial center, and closure overshoot are live dimensions;
dependent grooves use equal/parallel/tangent contracts rather than fixed copied
points. Its CAD closure overshoots the blank only outside the material envelope
so the operational contour remains one simple component; the functional rim
geometry is unchanged. V-belt and Poly-V schemas and catalogs must not be merged
into one implicit family.
The Layer 4 pulley workflow creates a new owned rotational blank and applies the
existing family-specific Layer 3 groove builder inside the same unsaved KOMPAS
document. Arbitrary pre-existing bodies are intentionally outside this product
contract. Recognition scans the complete part-variable, sketch, and rotational
feature collections for a compound ownership fingerprint; it does not require
the managed groove to remain the last model-tree feature.
Recognized version-1 blocks support complete profile editing through the same
Layer 4 plan used for creation. Parameter-only edits update existing
`PULLEY_*` and family `VB_*`/`PV_*` variables and rebuild in place. Changes to
groove count, V-belt designation or standard, and standard-fillet presence or
radius use an owned topology replacement: strict preflight rejects any
non-owned downstream modeling operation, the bridge deletes only the managed
fillet/cut/sketch branch, reapplies the existing family-specific Layer 3 builder,
then verifies ownership, profile readback, and a positive-volume single body.
The original plan is supplied as rollback data; failed replacement removes a
partial new branch and recreates the prior managed branch. CUSTOM V-belt fields
and catalog overrides are stored as managed metadata so save/reopen inspection
can reconstruct the editable profile without relying on display names.
The flat-belt Layer 4 family is a separate owned rotational rim rather than a
groove cut over a cylindrical blank. It supports cylindrical and explicit
circular-crown profiles, uses `PULLEY_D1`, `PULLEY_L1`, and `FP_*` ownership
variables, and reuses the managed topology-replacement/rollback boundary for
profile edits. Belt routes, belts, and tensioners remain outside this family.
Its initial body is closed to the rotation axis and contains no bore; the rim
thickness, hub, bore, keyway, and shaft interfaces belong to separate generic
modeling modules. Its cylindrical and circular-crown sketches carry formula-bound
driving dimensions and must read back as fully defined. Studio bounds each
isolated bridge call and can cancel that child process without terminating
KOMPAS, so a stalled COM operation cannot retain the single CAD-job lock forever.
The trapezoidal timing-belt family is an approved managed Layer 4 Studio module.
Its internal Layer 3 construction covers numeric and parameterized T/AT mechanics:
a cylindrical blank, one closed groove sketch with six primary segments
and four true-radius arcs (two retained-tooth transitions tangent to the outside
circle plus two groove-root fillets),
a through-all cut, and a full circular pattern. The parameterized mode adds 15
semantic `TB_*` variables, eight auxiliary datum entities, 45 geometric
constraints, eight formula-bound sketch dimensions, blank-width binding, and
tooth-count/angular-step pattern bindings. The numeric mode remains available as
the accepted geometry baseline. Trapezoidal T/AT and curvilinear HTD profiles
remain separate Studio modules because their groove sketches have different
entity and constraint mechanics.
Each preview is a cropped end-view fragment of three grooves and two teeth with
a short tooth-tip reference arc, a closed lower/side break boundary, tangent
profile fillets, and distributed outside/root diameter plus groove width/depth
and fillet-radius dimensions;
both timing descriptors report `build=true`. Their Layer 4 blocks own a `TB_*`
and `GW_*` fingerprint,
two sketches, blank/cut extrusions, and circular pattern. Generated pattern
copies participate in the owned set and topology preflight, but only the five
root objects define the stable block identity. Parameter updates rebind and
read back blank width, pattern count, and angular step; failure restores the
previous variables and rebuilds the recognized block. Live create, designation,
tooth-count and width update, save/reopen, and rollback are accepted for both
T/AT and HTD. The HTD Layer 3 contour uses two true-radius outside-circle
transitions and one central root arc, 37 geometric constraints, and seven
formula-bound dimensions. Studio module
descriptors carry stable group/subgroup/family taxonomy so staged selectors can
separate a family path from modules without coupling identity to display structure.

The roller/bush-chain sprocket family has an initial create-only Layer 4 vertical
slice for single-row ISO 606 and GOST 591 profiles. Layer 2 supplies the exact
tangent-circle tooth-space contour and a standard-derived functional tooth width.
Catalog rows within the supported engagement-ratio range use the detailed KOMPAS-compatible GOST 591 working
construction: six arcs, two common-tangent segments, the unchanged `r`, `r1`,
and `r2` formula set, and a user-selectable offset or non-offset pair of
roller-seat arc centers. A separate three-segment cap closes the cut contour
outside the functional profile. In the
offset construction the physical right seat center is at `+e/2` and the physical
left seat center is at `-e/2`; the secondary-flank centers are translated from
their corresponding seat centers before tangent construction. ISO 606 and
GOST chain dimensions remain separate from the shared tooth-construction
algorithm; selecting the construction variant does not rewrite catalog pitch,
roller diameter, or inner width.

Layer 2 rejects ordinary tooth construction outside
`1.4 <= pitch / engagement_diameter <= 2.0` before CAD writes: GOST 591-69
limits its scope to lambda <= 2 and its Table 1 starts at 1.40. ПРИ rows above
that range use a separately labelled native-KOMPAS compatibility profile with
`K=0.532`. Five measured diameters for ПРИ-78.1-360 and one `z=60` diameter for
each remaining ПРИ row reproduce that rule to the displayed 0.01 mm. Layer 2
also verifies that the outside circle precedes the intersection of neighboring
`r2` branches, so the full circular pattern retains a blunt outside arc rather
than a pointed overlap. This policy is not presented as normative GOST 591 geometry.
`ISO_08A` (and its row-count variants) carries ISO 606:1994 dimensions from
GOST 13568-97, mandatory Annex A, Table A.1; it is not an alias for the existing
`ISO_40A` reference-catalog entry. The supplied ISO 606:2015 sample does not
establish dimensional equivalence between those entries. The root diameter is
`pitch_diameter - 2 * seating_radius`, per GOST 591-69 Table 1.

The KOMPAS application catalog's special B-1 rows `081` through `085` are
dimensionally separate from `08B-1` and carry their local provenance as
`Таблица ГВС 005-2015`; they are not presented as additional normative ISO 606
designations. These five simplex-only rows use the native
`0.93*Bvn-0.15` tooth-width formula. The public request field retains its
historical `gost_profile_variant` name for client compatibility, but Studio
labels and applies the selector to both ISO and GOST chains.
Layer 3 creates one cylindrical blank, one through-all tooth-space cut, and a full
circular pattern. Live ISO and GOST creation verifies a fully defined closed arc
sketch, pattern count, rebuild, and one positive-volume solid. In-place editing
remains outside this slice. Workspace readback does
recognize the create-only block from `GW_FAMILY_CODE=6`, the complete `CH_*`
fingerprint, and five root objects; generated pattern copies are owned but do not
participate in stable block identity. Creation also persists a checksummed
`geomwright.chain.recipe` with the Studio designation, chain type, tooth count,
row count, and tooth-gap variant. Recognition restores that profile and marks the
block recreatable, so a reopened model offers a new build with edited inputs while
the saved document stays unchanged.

Multi-row creation is available for catalog rows with both transverse pitch and
plate height. ISO 606:1994 A/B rows through 32A/32B are sourced from GOST
13568-97 Annex A Table A.1; missing old-ISO A rows such as 10A were added as
distinct profiles rather than aliased to ANSI-numbered entries. Axial data is
attached only after pitch, roller diameter, and inner width all match, preventing
the existing ANSI-derived `ISO_40A` key from being mistaken for old ISO 40A.
ANSI-numbered A-series rows 25A through 240A carry a separate ANSI B29.1
transverse-pitch and plate-height schedule converted with the exact 25.4 mm/in
factor. For narrow catalog gaps such as 05B, the normal GOST 591 `r4` remains
the preferred radius; when two such arcs cannot fit, the plan uses the largest
equal fitted radius while preserving a ten-percent central land and records the
selection policy in readback.
GOST 13568 PR/PV multi-row rows use their own Table 2 dimensions. A shared
Layer 2 axial layout supplies preview and CAD tooth width, pitch, total width,
and connecting-rim diameter. Multi-row widths use GOST 591-69 Table 2;
GOST 21834-87 NP/TP rows use the corresponding catalogue transverse-pitch and
plate-height schedule, so all three published chain-standard branches have
multi-row representatives in the same plan contract.
`Dc=floor(t*cot(pi/z)-1.3*h)` uses its maximum rim diameter and clause 1.5 rounding.
The first row is built at its own width, including both axial roundings. A
type-528 `ILinearPattern` copies the evaluated whole body along negative X;
`CH_N` and `CH_A` bind its count and pitch. After explicit rebuild, every row's
bounding box and the temporary body count must match the plan. A separate,
parameterized connecting-rim revolution then unites the rows. Final verification
checks one solid, total width, and volume against N finished rows plus cylindrical
gap material. Ownership includes the body pattern and rim but preserves the five
original identity references. Reopened models recover `row_count` from `CH_N`;
legacy models without that variable remain single-row. Missing catalog data is
a preflight error, not permission to estimate row pitch. Two- and three-row 08B
Z25 have live create/save/reopen and pattern-expression readback evidence. For
three rows the total width is 34.665 mm and the rim sketch reads fully defined
after reopen. In the two-row sample the rim sketch read
fully defined at creation and code 1 after reopen; that solver state still needs
UI confirmation. The connecting rim receives one circular-edge fillet feature
on all `2*(row_count-1)` internal ring junctions. GOST 591-69 Table 2 sets
`r4=1.6 mm` for pitch <=35 mm and `2.5 mm` above it. Preflight requires room
between adjacent fillets and below the root/rounding envelope. Edge resolution
uses unique circular body edges at the planned axial positions/rim radius, not
collection indexes. The concave fillets must add the analytically expected stock
and preserve overall bounds and one solid. The circular-edge helper is shared
with V-belt finishing, whose convex fillets retain their material-removal check.
Three-row 08B Z25 has create/save/reopen evidence for all four r4 junctions and
their radius, persisted ownership and body volume.
Three-row 10A Z25 and four-row 4PR-38.1 Z25 also have live create/save/reopen
evidence; the latter verifies six junction edges and the `r4=2.5 mm` branch.

Creation also appends two axial tooth-end cut revolutions, using GOST 591-69
Fig. 3/Table 2: minimum `r3 = 1.7 * engagement_diameter` and centre drop
`h3 = 0.8 * engagement_diameter`. These are functional axial profiles, not
constant-radius edge fillets. Each has a closed arc/three-line sketch with
constraints applied before its formula-bound dimensions. The owned YOZ blank
occupies global X `[-CH_B, 0]`; the two profiles enter that interval from its
opposite ends. Every cut must remove material and preserve a single solid.
The new sketches/rotations are owned, but the original five root references
remain the identity for both new and older chain blocks. Radius selection keeps
at least 20% of the face width as a flat tooth-tip land: this is an explicit
generator policy, not a GOST-prescribed dimension. It retains `r3=1.7D` when
`b >= 0.5D`; otherwise `r3=h3*h3/(0.8b)+0.2b`, derived from circular sag
`s=0.4b`. Both radii meet the normative minimum; width and h3 remain unchanged.
The selection is formula-bound in CAD, including the branch condition.
ISO 081 Z25 has live create/save/reopen evidence with b=2.919 mm,
r3=17.044916820829 mm and a 0.5838 mm tip land; both axial sketches read fully
defined after reopen. ISO 08A-1 Z25 has live create/save/reopen evidence
for both cuts and their radii, end placement, closed topology and ownership.
Both axial sketches read fully defined during creation; after reopen one read
code 1 and the other code 2, so the former still needs UI state confirmation.

The tooth-space sketch now exposes its independent construction through named
datum circles, centre spans, geometric constraints, and formula-linked dimensions.
The offset construction applies 41 in-sketch constraints and 17 sketch
dimensions; the degenerate `e=0` construction applies 35 and 14 respectively.
Both receive one additional post-build type-2 `point_on_curve`, so their final
constraint totals are 42 and 36. In the offset variant, one horizontal common
lower tangent joins the two trimmed roller-seat arcs, replacing their intersecting
bottom endpoints. Its length follows the centre span `CH_E`; two tangencies and
the existing centre/radius dimensions own it without another driving length.
This gives 12 contour entities (six arcs, six segments); the non-offset variant
retains 11 and never creates a zero-length bottom segment. Master
roller-seat, flank, and head arcs carry formula-bound driving radii `CH_R`,
`CH_R1`, and `CH_R2`; their mirrored dependents inherit equal radii. Six tangent
relations determine the working branch junctions in addition to the contour's
merge topology. The production workflow adds one `point_on_curve` from the start
of the right technical side line to the outside datum after blank, sketch, cut,
and pattern creation. This call is isolated and followed by independent readback
of the exact entity-reference pair, closed topology, gaps, and
self-intersections. A timeout is accepted only when that readback proves the
relation. The user confirmed both the saved and unsaved candidate sketches fully
defined in visible KOMPAS. API `ConstraintsState` may still report code 1 outside
that UI context and is therefore returned as diagnostics rather than used as the
sole verdict. The
non-working outer branch is deliberately linear: two equal
vertical `CH_CO` overshoots raise the horizontal closure to exactly
`CH_RA + 0.5 mm`, guaranteeing 0.5 mm radial clearance from the blank even for
small diameters. The horizontal line carries a visible reference width dimension
`CH_CW`; making that dimension driving creates a redundant closed-loop ownership
cycle in KOMPAS. The branch has no closure arc, auxiliary closure circle, or
intermediate top node. Both variants require exact initial applied counts,
post-build relation readback, radial-dimension readback, closed topology, full
feature completion, positive body, rebuild, and save/reopen evidence.

The `gear_spur` Studio module is the first cylindrical-gear family slice. Layer 2
`src/kompas_mcp/gears/` owns four basic-rack systems: ГОСТ 13755-2015 with its
A–D modifications (ГОСТ 9563-60 module rows), ГОСТ 9587-81 small-module shapes,
ГОСТ Р 50531-93 high-stress types 1–2, and ISO 53:1998 profiles A–D with
ISO 54:1996 module rows. It also owns the analytic involute flank, the
theoretical sharp-rack trochoid root with undercut trimming, control
measurements (span length, constant chord, over-pin), the cached standard
wire/roller rows for the over-pin input, and a structured check report; the
representation is `nominal`, not `generated_exact`. A positive
`helix_angle_deg` plus a separate `hand` field turns the same request into a
helical gear: the end view is the transverse section (`m_t`, `α_t`, `β_b`), the
addendum/dedendum stay normal, and the summary adds lead, axial pitch, and
axial overlap. The Studio form separates the standard from the contour
modification and derives the profile coefficients from that pair; only the
user-defined modification exposes them as inputs, and a module outside the
selected contour's declared range is reported instead of silently accepted.
Layer 3 `gears/cad.py` builds
a create-only numeric plan: cylindrical blank, one tooth-space cut whose flanks
are smooth cubic Bézier-NURBS curves split at the form point (root curve plus
involute curve, seven entities per tooth space), and a full circular pattern.
For `β = 0` the cut is a through-all extrusion; for `β > 0` the
`helical_cut_evolution` bridge scenario sweeps the transverse sketch along a
cylindrical spiral with `Step = lead`, `Height = b`, and the spiral position
point anchored **on the gear axis** (the anchor is what makes the sweep exact;
`CAD_PATTERNS.md` `EVO-001`). Optional end chamfers (`tip_chamfer_mm`) are two
`rotational_cut` cone cuts on the blank before the tooth-space cut, so the
expensive circular pattern stays the last feature; the final Boolean body is
identical to chamfering the finished teeth. After the final rebuild the bridge
hides the spiral, the 3D points/axis, all sketches, and the default planes. The
bridge adds `GW_GEAR_VERSION=1`,
`GW_FAMILY_CODE=8`, a `GEAR_*` readback fingerprint with standard/modification
codes plus `GEAR_BETA_DEG`/`GEAR_HAND`, and a checksummed recipe; reopened blocks
are read-only and can recreate a new part from the persisted Studio profile.
`gear_tools.py` exposes the same Layer 2/3 core through
`list_gear_standards`, `preview_cylindrical_gear`, `create_cylindrical_gear`,
and `inspect_cylindrical_gear`.
Live create, volume/bounds/pattern verification, save/reopen recognition, spur
and helical cases (β=20° right and β=30° left), and an odd-tooth-count
profile-shift case are accepted. Rounded cutter-tip `generated_exact` roots,
herringbone and worm families, and gear pairs remain outside this slice.

The `gear_internal` Studio module is the second cylindrical-gear family slice
and reuses the same basic-rack catalog, but follows ГОСТ 19274-73 for the wheel:
`d_a2 = d2 - 2 (h_a* - x2 - 0.2) m`, `d_f2 = d2 + 2 (h_a* + c* + x2) m`, and
the controls are measured across the internal tooth spaces. Layer 2
`gears/internal.py` owns the nominal involute space, the radial tip extension
when the tip circle lies inside the base circle, the tangent cubic-Bezier
approximation of the generated root transition (scaled down when it does not
fit the space), the ring-wall and tip checks, and the span/constant-chord/over-pin
measurement set. Layer 3 `gears/cad.py` builds a create-only numeric plan: a
ring blank with an explicit outside diameter, a full-rotation rectangular bore
at the tip diameter, two optional tooth-tip chamfer cuts at the bore edges, one
internal tooth-space cut closed by cubic-Bezier root transitions and exact
bore/root arcs, and a
circular pattern; the space cut is a through-all extrusion for a spur gear and
a cut evolution along the cylindrical spiral for `β > 0`. The bridge persists `GW_GEAR_VERSION=2`,
`GW_FAMILY_CODE=9`, `GEAR_RING_DA`, the `GEAR_*` fingerprint, and a checksummed
internal recipe; reopened blocks are read-only and recreatable. Live acceptance
covers an internal spur `m2 z40 D100 × 20` and an internal helical `m2 z40`,
`β=20°` left with one positive solid, expected bounds, the physical tooth
count, volume within 0.02 % of the analytic ring section, and save/reopen.
Pinion-cutter `generated_exact` roots, end chamfers, hubs, keyways, housings,
and gear pairs remain outside this slice. The contract is in
[docs/gear-internal.md](docs/gear-internal.md).

The `gear_bevel` Studio module is the first bevel-gear family slice. Layer 2
`gears/bevel.py` owns the ГОСТ 19624-74 macro geometry (outer cone distance,
addendum/dedendum angles, face and root cones, face-width recommendation, and
the dish blank parameters `rim_back_extension_mm` / `rim_front_extension_mm`)
and the Tredgold virtual gear: the continuous virtual tooth count
`z_v = z / cos δ`, the back-cone involute/trochoid flank generated by the shared
`build_tooth_space_flank` core, the tip/undercut/face width/dish checks, and the
cone-normal tooth-space sections. Representation mode is `nominal`; the report
states that the flank is the Tredgold projection, not the exact spherical
involute or an octoid. Layer 3 `gears/cad.py` builds a create-only numeric plan:
a `revolved_profile_blank` dish (flat back and front faces joined by back, tip,
and front cones), two `section_profile_sketch` sections on the cone planes
normal to the tooth, one `loft_cut` between them (`ILoft` with
`ksOperationResultEnum::ksOperationCut`), and a circular pattern. The sections
are homothetic copies of the virtual contour, so the loft side surfaces follow
the projection rays and the tooth ends are formed by the same cone surfaces as
the rim instead of an axial plane. `section_profile_sketch` supports planes
perpendicular to an explicit 3D axis line and measures the actual sketch frame
from probe points before writing the host 3D contour, so no plane-orientation
assumption enters the host plan. The bridge persists `GW_GEAR_VERSION=3`,
`GW_FAMILY_CODE=10`, `GEAR_DELTA_DEG`/`GEAR_ZA`/`GEAR_ZF` and the full `GEAR_*`
fingerprint plus a bevel recipe; reopened blocks are read-only and recreatable.
Live acceptance covers a `m3 z20 δ=45°` dish and a `m4 z16 δ=26.565°` shifted
case with one positive solid, dish-minus-spaces volume within 0.06 %, expected
axial span, 20/16 pattern instances and save/reopen. Circular (spiral) teeth,
gear pairs, cutters, chamfers, contact patterns, and strength remain outside
this slice. The contract is in [docs/gear-bevel.md](docs/gear-bevel.md).

The `shaft_spline` and `hub_spline` Studio modules are the first shaft-connection
slice. Layer 2 `connections/splines/` owns the ГОСТ 1139-80 catalog (light,
medium, and heavy series with the table `b`, `d1`, `a`, `c`, `r` values), the
exact straight-sided end profile for shafts and hubs, preflight checks, and the
ГОСТ 1139-80 fit registry with numeric ГОСТ 25346/ISO 286 limits for the zones
that standard lists. `build_spline_geometry` returns exact segments and arcs
(parallel flanks, root fillets, root/bore arcs) plus a Green's-theorem section
area; the preview adds a cropped sector for Studio and the fit report. Layer 3
`connections/cad.py` builds create-only numeric plans: a shaft section with the
cylinder blank, two optional `c x 45` tip chamfers, one through tooth-space cut
and a circular pattern, or a hub ring with a rotational bore at `d`, the
internal space cut and the pattern. The bridge persists `GW_SPLINE_VERSION=1`,
`GW_FAMILY_CODE=11`, an `SPL_*` fingerprint and a checksummed recipe; reopened
blocks are read-only and recreatable. `spline_tools.py` exposes
`list_spline_sizes`, `preview_spline`, `create_spline`, and `inspect_spline`.
Live acceptance covers a light-series `8x36x40` shaft section (volume error
8.6e-08, 8 pattern instances, save/reopen) and a Ø55 hub ring (volume error
1.2e-14, save/reopen). The radius cutter runout, the rolled execution-1 groove,
the internal runout contract, involute and triangular splines, keyways, and
face joints remain in the connection plan
([docs/spline-straight.md](docs/spline-straight.md)).

`silent_chain_sprocket` Studio preview adapts separate host-side GOST, DIN and
ASME-compatible profile mechanics plus their axial layout metadata into two
canvas views. Its catalogs cover GOST 13552-81/13576-81, secondary DIN 8190 A/B
rows, and ASME-compatible open-reconstruction pitch/guide metadata. DIN/ASME
choices retain explicit provenance and no-conformity warnings. The
descriptor advertises `preview=true`, `build=true` with a create-only Layer 4
functional-rim contract.
Its Layer 2 owner `transmissions/silent_geometry/` is presentation-independent;
Studio's former calculation files remain thin compatibility facades. The shared
`silent_chain_completion.py` separates source
data from explicit user construction choices. It exports a bounded completeness
report and a validated functional-rim geometry specification for CAD
planning, never a COM action. Construction intent is inferred from actual input
values; no mode selector or confirmation checkbox is required. Missing values
and unresolved radial conflicts cannot become CAD-planning-ready; this is not conformity,
strength, native sketch or B-Rep verification.
`transmissions/silent_chain.py` consumes that specification without importing
Studio or COM. Its numeric Layer 3 plan revolves the completed axial outline
closed on the rotational axis: the blank is solid, with no central hole. The
detail-view depth only crops the preview and never creates an inner CAD surface;
it is optional and excluded from required construction inputs. Automatic view
framing is permitted without inventing an engineering dimension.
Holes, shaft seats and hubs belong to subsequent modules. The plan
cuts a radial profile and patterns it around global X. DIN's analytic involute
and rolling-rack envelopes become three or five cubic NURBS, fitted independently
across intentional undercut/trim corners. Neutral `sketch_runtime/cubic.py` owns
the shared C2 interpolator used by cams and the bounded analytic-path fitter;
held-out source samples enforce a 0.0005 mm fit limit. Circular GOST/ASME runs
become native arcs; residual noncircular sampled runs have bounded 0.0005 mm
source-point simplification. The bridge owns execution and actual profile/body readback,
including NURBS order/poles/weights/knots, actual-curve topology sampling, and a
source-cut-volume multiplier check for every pattern instance.
Missing construction inputs and unresolved source conflicts fail before document
creation. The `GW_SILENT_VERSION`/`SC_*` fingerprint recognizes five stable root
objects; generated copies are owned but excluded from identity. A persisted form
restores a new-part draft, not an in-place editor. Failures retain a structured
partial-document result; cancellation does not roll back KOMPAS operations.
DIN/ASME provenance warnings remain in force after CAD creation.
`silent_chain_tools.py` registers paginated catalog discovery, bounded preview,
new-part preflight/creation and read-only saved-recipe inspection in the public
MCP registry and transmission-design catalog. Studio and MCP use the same Layer 2
schema/calculation and Layer 3 CAD plan. Preflight never calls COM; execution
requires explicit write confirmation. Tool responses omit sampled contours and
raw sketch readback arrays, retaining actual body checks, exact document IDs and
semantic references. Recipe recognition is not a fresh geometry audit. Neither
interface currently replaces the old body inside an existing document.

Geomwright Studio owns document/session navigation above Layer 4 modules. Its
workspace discovers open KOMPAS documents, opens saved files, presents managed
blocks together with surrounding unmanaged KOMPAS operations, and routes a
recognized block to its fixed-family editor. File selection, active-document
following, safe Save/Discard/Cancel closure, mixed-tree navigation, and editor routing belong to Studio rather
than to an individual pulley module. The first workspace slice supports one
managed block per document; multi-block cascade authoring is deliberately
deferred, while workspace data structures remain lists and carry stable block
identity so that future cascades do not require another navigation redesign.
Studio bridge calls attach through the COM Running Object Table to an already
running KOMPAS application and never create a COM server. If that registered
instance is hidden, Studio makes it visible and verifies visibility before any
document operation. If no application is registered, workspace reports a
recoverable disconnected state and retries after KOMPAS starts; file and CAD
writes remain unavailable until attachment succeeds.
Document activation and lifecycle writes resolve the exact current runtime ID;
they fail on stale IDs and never fall back to another active document. Changed
untitled documents require an explicit Save As path before close. Save and Save
As are document-level commands independent of block rebuild. Successful Layer 4
creation is followed by workspace readback; Studio enters the recognized new
block's editor only after matching the returned runtime document ID and module.

Подробные контракты находятся в `docs/`; runtime tool catalog остаётся источником
истины для фактически зарегистрированных MCP names.

## Сквозные оси

### Данные

Публичная граница использует JSON-совместимые dictionaries/lists/scalars.
Внутренние dataclasses и typed specs допустимы внутри владельца слоя, но нельзя
создавать второй публичный schema-contract для того же MCP tool.

Единый глобальный `EntitySpec` для всего проекта пока не является production
контрактом. Экспериментальные реализации не должны оборачивать существующие tool
responses или менять их shape без отдельной миграции.

### Состояние документа

Документ адресуется стабильным `document_id`; операции записи сопровождаются
snapshot/readback там, где это поддержано. KOMPAS остаётся stateful, но MCP не
предоставляет универсальную multi-call transaction/session abstraction.

Правила безопасности:

- preflight перед записью;
- явный target document/feature/sketch;
- fail-fast при невалидном COM-результате;
- сохранение и reopen-readback для законченного workflow;
- отсутствие скрытого fallback на другой документ или entity.

### Верификация

Уровень проверки выбирается по риску:

- нормализованный preview и инварианты Layer 2;
- operation/model-object readback;
- snapshot delta;
- body/topology/formula inspection;
- reopen-readback сохранённой модели;
- визуальная проверка только там, где B-Rep и COM readback не выражают нужный
  критерий.

## Production boundary

Production surface состоит только из модулей, импортируемых зарегистрированным
MCP server и описанных канонической документацией. Research-only native-module
tools регистрируются только при явном `GEOMWRIGHT_ENABLE_RESEARCH_TOOLS=1` и не
входят в обычную публичную MCP-сессию.

Опциональные presentation adapters могут поставляться в том же Python package,
но не становятся частью MCP production surface автоматически. Их capability
contract и граница с CAD runtime должны быть описаны отдельно.

Незаконченные OperationGraph, universal rule engine, template library, session
tracking и spring-readback prototypes помещаются в ignored-зону
`experiments/spikes/`. Они не являются частью package, tool catalog или roadmap,
пока не выполнены одновременно:

- один явный owner layer;
- package-data contract;
- корректная propagation ошибок и зависимостей;
- schemas, выведенные из реальных MCP tools;
- Verify/Correct semantics;
- документация публичной миграции.

Исторические task briefs также не являются roadmap.

## Текущее состояние

| Компонент | Слой | Статус |
| --- | --- | --- |
| session/document lifecycle | L1 | stable |
| specifications, relinking, composition | L1–L3 | stable |
| low-level sketch/feature runtime | L1–L2 | experimental |
| `sketch_runtime/` | L2 | current deterministic core |
| parametric part workflows | L2–L4 | experimental, family-specific live evidence |
| managed spring families | L2–L4 | implemented, see family contracts |
| cam profiles | L2–L4 | create-only single cam, shared Studio/MCP plan, actual curve/contact/body verification |
| diaphragm module | L2–L4 | complete and live-verified |
| mechanical-transmission platform | L2–L4 | managed V-belt, Poly-V, timing and flat-belt pulley workflows plus live-verified create-only single-row ISO/GOST chain sprockets and external/internal cylindrical gears, and straight bevel gears |
| shaft connections | L2–L4 | live-verified create-only straight-sided splines (ГОСТ 1139-80) for shafts and hubs with fits; runout and further connection families planned |
| Geomwright Studio | presentation over L2–L4 | experimental; create-only completed silent-chain rims and gear blocks, managed pulley previews/build, and no arbitrary-body write path |
| native module inspection/launch | L1–L3 | research, explicit opt-in for registration and launch |
| universal OperationGraph/Rule Engine/templates | — | not production; quarantined prototype |

## Документационная иерархия

1. `README.md` — установка, runtime status и первый workflow;
2. этот файл — ownership и production boundaries;
3. `CAD_PATTERNS.md` — переносимые CAD-инварианты;
4. `docs/README.md` — индекс тематических контрактов;
5. `docs/en/` и `docs/ru/` — синхронизированные руководства и парные полные
   контракты, включая регламент новых модулей; правила владения и расширения
   языков определены в `docs/README.md`;
6. `experiments/spikes/` — локальная ignored-зона для исторических и незавершённых
   материалов, не входящих в публичный runtime.

## Связанные документы

- [Documentation index](docs/README.md)
- [Reusable CAD patterns](CAD_PATTERNS.md)
- [Low-level runtime](docs/low-level-runtime.md)
- [Write operations](docs/write_operations.md)
- [Sketch authoring agent protocol](docs/sketch-authoring-agent-protocol.md)
- [Parametric workflows](docs/parametric-workflows.md)
- [Spring workflows](docs/spring-workflows.md)
- [Diaphragm spring](docs/diaphragm-spring.md)
- [Geomwright Studio](docs/geomwright-studio.md)
