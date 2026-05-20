# Sketch Runtime Strategy

## Implementation status

Current baseline exists in `src/kompas_mcp/sketch_runtime/`:

- `entities.py`: semantic points, segments, arcs, circles, sketch model ids, roles and construction flags;
- `topology.py`: closed-loop, standalone circle-loop, missing endpoint/center, dangling point, connectivity, construction-in-profile and segment-intersection preflight checks;
- `frames.py`: 2D local-frame checks for zero axes, orthogonality and handedness;
- `constraints.py`: staged constraint plan checks for unknown stages, missing targets, required constraints and minimum target counts;
- `relations.py`: point-to-point relative position checks (`left_of`, `right_of`, `above`, `below`, `same_x`, `same_y`) for semantic geometry sanity checks;
- `tangency.py`: segment/arc/circle tangency checks at shared or explicit contact points, with missing-contact and non-parallel tangent diagnostics;
- `measurements.py`: numeric geometry checks for point distances, horizontal/vertical spans, segment length, arc radius and circle radius;
- `orientation.py`: segment-loop signed-area orientation checks for expected clockwise/counter-clockwise contour direction;
- `dimensions.py`: variable/dimension binding checks for missing variables, missing targets and unknown expression references;
- `verify.py`: one-call preflight aggregation across topology, frame, constraints, point relations, tangencies, measurements, loop orientation and dimension bindings;
- `readback.py`: dependency-free actual-vs-expected sketch snapshot checks for ids, coordinates, primitive shape, loop membership, construction flags and actual topology;
- `diagnostics.py`: compact model-readable diagnostics shared by the preflight reports.

These modules are intentionally dependency-free and do not call KOMPAS/COM yet. They are the first pure-python preflight/readback layer that future sketch builders can use before and after executing live commands.

Цель документа - зафиксировать первый нижний слой разработки `kompas-mcp`, который
снимает с модели ручное управление мелкими, но постоянно повторяющимися действиями
КОМПАСа.

Фокус первого этапа:

- точки, отрезки, дуги, окружности;
- роли и имена элементов эскиза;
- топология контуров;
- порядок применения ограничений и размеров;
- ЛСК, направления и локальные оси;
- переменные, формулы и привязка выражений к размерам;
- readback после solver-а;
- диагностика, понятная модели.

Этот слой не отвечает за выдавливания, вырезы, вращения, тела и сложные feature-
операции. Он должен стать надежной базой, из которой позже будут собираться такие
операции.

## Почему это нужно

Текущие модули уже дают хороший результат, но разработка часто идет через перебор:
модель не видит, где именно нарушилась геометрия, порядок сборки или привязка
параметров. Особенно ярко это проявляется в эскизах, но та же природа есть у ЛСК,
направлений действий, переменных и формул.

Нужен слой, который делает каждый микро-шаг наблюдаемым:

```text
declare -> preflight -> execute -> readback -> verify -> diagnose
```

В проекте уже есть частные ростки такого подхода:

- `src/kompas_mcp/thread_profile_sketch.py` содержит contract-check для V60 flat
  profile;
- `bridge/kompas_bridge.py` поддерживает staged-порядок
  `anchored_dimensions_then_constraints`;
- в параметрах эскиза уже есть `readback_geometry` для live-проверок.

Задача runtime - превратить эти частные решения в общий обязательный протокол.

## Границы слоя

`sketch_runtime` работает ниже модулей деталей и выше сырого API КОМПАСа.

Он должен принимать не произвольный набор COM-команд, а декларативное описание
микро-геометрии:

```json
{
  "frame": "profile_lcs",
  "entities": [
    {"id": "left_outer", "kind": "point", "role": "outer_surface_point"},
    {"id": "right_root", "kind": "point", "role": "root_point"},
    {"id": "left_flank", "kind": "segment", "from": "left_outer", "to": "root"}
  ],
  "loops": [
    {"id": "profile_loop", "entities": ["left_flank", "root_flat", "right_flank", "crest_flat"]}
  ],
  "constraints": [
    {"kind": "coincident", "a": "left_flank.end", "b": "root_flat.start"},
    {"kind": "collinear", "target": "left_flank", "partner": "left_theory"}
  ],
  "dimensions": [
    {"id": "pitch_dim", "target": "right_pitch_ref", "expression": "Pitch"}
  ]
}
```

Модель должна оперировать ролями и инвариантами, а не случайными COM-объектами,
индексами линий или визуальными догадками.

## Набор микропримитивов

Минимальные публичные primitives/recipes:

- `create_named_point`
- `create_segment`
- `create_arc`
- `create_circle`
- `create_closed_polyline`
- `join_points_coincident`
- `apply_horizontal_by_frame`
- `apply_vertical_by_frame`
- `apply_parallel`
- `apply_collinear`
- `apply_tangent`
- `bind_linear_dimension`
- `bind_angular_dimension`
- `bind_radius_dimension`
- `bind_formula`
- `verify_closed_loop`
- `verify_no_dangling_entities`
- `verify_no_duplicate_entities`
- `verify_no_unexpected_intersections`
- `verify_lcs_orientation`
- `verify_formula_binding`
- `readback_sketch_geometry`

Каждый primitive должен возвращать не только success/failure, но и stage-local
diagnostics.

## Рекомендуемая структура пакета

```text
src/kompas_mcp/sketch_runtime/
  __init__.py
  entities.py      # semantic ids, roles, points, curves, COM id mapping
  frames.py        # LCS contract, direction aliases, handedness checks
  topology.py      # graph, loops, dangling ends, intersections
  constraints.py   # staged constraint plan and application reports
  dimensions.py    # variables, expressions, formula binding, readback checks
  verify.py        # invariant checks
  diagnostics.py   # model-readable failures and repair hints
```

Первый вариант может быть тонким Python-слоем над текущими структурами
`profile_points`, `profile_lines`, `profile_arcs`, `construction_lines`,
`profile_constraints` и `profile_dimensions`. Не нужно сразу переписывать bridge.

## Staged pipeline

Порядок сборки должен быть явным и одинаковым для всех новых эскизов:

1. Normalize input parameters.
2. Resolve frame contract: origin, axes, handedness, direction aliases.
3. Declare named entities without constraints.
4. Build topology graph.
5. Preflight topology: missing endpoints, duplicate ids, expected loops.
6. Create raw entities in KOMPAS.
7. Apply anchor/coincidence constraints.
8. Read back connectivity if live mode is enabled.
9. Apply orientation constraints: horizontal/vertical/parallel/collinear by frame.
10. Apply driving dimensions.
11. Bind formulas and variables.
12. Apply deferred constraints/dimensions when solver requires staging.
13. Force update/solve.
14. Read back geometry, dimensions and solver state.
15. Verify contract invariants.
16. Return compact stage report.

`partial` results are acceptable only в явно помеченном exploratory/dev-mode.
Для production-пути новый runtime должен стремиться к `strict`.

## Frame contract

Путаница с "лево/право", "внутрь/наружу", "start/end" должна решаться не в
промпте, а контрактом ЛСК:

```json
{
  "id": "profile_lcs",
  "origin": "thread_start",
  "x_axis": "along_thread_span",
  "y_axis": "radial_outward",
  "handedness": "right",
  "aliases": {
    "axial_positive": "+X",
    "radial_outer": "+Y",
    "radial_inner": "-Y"
  }
}
```

Verifier обязан ловить:

- инверсию радиальной оси;
- несовпадение expected handedness;
- использование глобальных координат там, где нужен frame-local смысл;
- конфликт alias-ов `start/end`, `left/right`, `inner/outer`.

## Topology contract

До применения размеров и сложных constraints runtime должен знать граф эскиза.

Минимальные проверки:

- все entity ids уникальны;
- все references существуют;
- каждый segment/arc имеет валидные endpoints;
- expected loop замкнут;
- у замкнутого loop нет dangling ends;
- нет нулевых отрезков и дуг;
- нет неожиданных пересечений;
- construction geometry не попала в solid/profile loop;
- profile geometry не помечена как construction случайно.

Пример stage report:

```json
{
  "stage": "preflight_topology",
  "ok": true,
  "points": 6,
  "curves": 5,
  "loops": [{"id": "profile_loop", "closed": true, "entities": 5}],
  "dangling_endpoints": [],
  "unexpected_intersections": []
}
```

## Constraint contract

Ограничения должны применяться планом, а не неупорядоченным списком.

Рекомендуемые группы:

- `anchor`: совпадения точек, фиксация базовых references;
- `orientation`: horizontal/vertical/parallel/collinear относительно ЛСК;
- `shape`: tangent, equal radius, symmetry, profile-specific relations;
- `driving_dimensions`: размеры с управляющими выражениями;
- `deferred`: то, что нужно применять после первичной стабилизации solver-а.

Каждая группа должна иметь expected count и список обязательных constraints.

```json
{
  "stage": "orientation_constraints",
  "ok": false,
  "failed": [
    {
      "code": "missing_collinear_constraint",
      "target": "left_flank",
      "partner": "left_theory",
      "repair_hint": "add collinear before driving dimensions"
    }
  ]
}
```

## Dimension and formula contract

Формулы и переменные нужно привязывать через binder, а не через ad hoc строки.

Проверки binder-а:

- переменная существует или объявлена runtime-ом;
- expression не пустой;
- expression не был заменен числом при записи;
- dimension target существует;
- dimension привязан к правильным объектам;
- readback expression/value соответствует expected;
- units и frame-local direction не конфликтуют.

Пример:

```json
{
  "id": "pitch_dim",
  "target": "right_pitch_ref",
  "expression": "Pitch",
  "required": true,
  "readback": {
    "expression": "Pitch",
    "value_mm": 1.5,
    "ok": true
  }
}
```

## Readback contract

После live-сборки runtime должен вернуть не большой dump, а компактное состояние:

```json
{
  "sketch": "thread_profile",
  "frame": "profile_lcs",
  "stages": {
    "topology": "ok",
    "constraints": "ok",
    "dimensions": "ok",
    "solver": "well_constrained"
  },
  "entities": {
    "points": 8,
    "segments": 6,
    "arcs": 0,
    "construction_curves": 7
  },
  "loops": [
    {"id": "profile_loop", "closed": true, "orientation": "ccw"}
  ],
  "failed_invariants": [],
  "warnings": []
}
```

Именно этот compact report должен видеть модель при разработке.

## Diagnostics

Ошибки должны быть пригодны для исправления кода:

```json
{
  "ok": false,
  "code": "radial_axis_inverted",
  "stage": "verify_lcs_orientation",
  "expected": {"radial_outer": "+Y"},
  "actual": {"radial_outer": "-Y"},
  "likely_cause": "profile frame was built from reversed reference direction",
  "repair_hint": "swap frame y-axis or invert radial aliases before entity generation"
}
```

Минимальные классы diagnostics:

- `missing_entity`
- `duplicate_entity_id`
- `dangling_endpoint`
- `open_loop`
- `unexpected_intersection`
- `wrong_loop_orientation`
- `tangency_mismatch`
- `measurement_mismatch`
- `construction_profile_mixup`
- `missing_constraint`
- `constraint_apply_failed`
- `missing_dimension`
- `formula_not_bound`
- `formula_numeric_fallback`
- `readback_mismatch`
- `lcs_axis_inverted`
- `direction_alias_conflict`
- `solver_underconstrained`
- `solver_overconstrained`

## Первый пилот

Пилотный кандидат - текущий V60 flat thread profile helper:

- он уже содержит именованные точки и линии;
- уже имеет contract verifier;
- уже использует staged-параметризацию;
- уже требует live readback для конических NPT-кейсов;
- в нем проявились типовые ошибки направления, замкнутости, projection refs,
  driving dimensions и conical compensation.

Цель пилота - не изменить внешний API модуля. Нужно заменить внутреннюю сборку
эскиза на runtime-протокол:

```text
current thread profile params
  -> SketchRuntime declaration
  -> preflight topology
  -> current bridge structures
  -> live KOMPAS apply
  -> readback
  -> contract diagnostics
```

Критерии успеха:

- preview/build результат совпадает с текущим рабочим модулем;
- verifier ловит типовые ошибки до визуального просмотра;
- live readback показывает конкретный stage, где возникла проблема;
- новые profile variants добавляются через декларацию ролей и invariants, а не
  через ручной перебор constraints.

## Поэтапное внедрение

1. Создать `sketch_runtime` skeleton без изменения поведения.
2. Перенести в него типы diagnostics и stage report.
3. Добавить topology preflight для уже существующих dict-структур.
4. Подключить preflight к `thread_profile_sketch.py` в preview-only режиме.
5. Перенести текущий V60 flat verifier в общий формат invariant checks.
6. Включить strict-mode для пилотного live-сценария.
7. После стабилизации использовать runtime для следующего нового sketch-family.

Не нужно сразу мигрировать все модули. Runtime должен доказать пользу на одном
болезненном, но уже рабочем эскизе.

## Что не делать на первом этапе

- Не проектировать общий feature/kernel слой для тел и операций.
- Не переписывать bridge целиком.
- Не заменять сразу все существующие module-specific helpers.
- Не делать универсальный solver поверх КОМПАСа до появления конкретных failure
  cases.
- Не скрывать partial/fallback как success в новом production-пути.

## Открытые решения

- Нужен ли отдельный offline preflight-solver, или сначала достаточно graph +
  live readback.
- Какой формат ids выбрать: короткие role ids или namespaced ids
  `profile.left_flank`.
- Где хранить repair hints: в verifier-ах или в центральной diagnostics table.
- Делать ли strict-mode default для новых модулей сразу, оставив legacy режим
  только для старых helpers.
- Нужен ли JSON schema для declarations уже на первом пилоте.
