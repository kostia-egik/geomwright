# Inspect sketch full report

Статус: current readback contract. Численные данные ниже являются live evidence
конкретной модели, а не универсальными параметрами workflow.

Отчет по реализации `inspect_sketch_full`.

## Что добавлено

Добавлен новый read-only инструмент `inspect_sketch_full`:

- bridge action: `inspect_sketch_full`;
- adapter method: `KompasAdapter.inspect_sketch_full(...)`;
- MCP tool: `inspect_sketch_full` в `sketch_tools.py`.

Инструмент не меняет модель. Он открывает существующий эскиз через
`BeginEdit()`, читает drawing container и закрывает эскиз через `EndEdit()`.

## Что возвращает tool

Основные поля результата:

- `sketch_name`;
- `sketch_ref`;
- `status`;
- `summary` по коллекциям;
- `entities` - плоский список всех найденных сущностей;
- `collections` - группировка по коллекциям;
- `dimensions`;
- `constraints`.

Актуальные диагностические поля текущей версии:

- `dimensions.items[*].api5.dimension_variable_name` - имя переменной размера из
  API5 `ksGetDimensionVariableName`, если КОМПАС его отдает;
- `dimensions.items[*].api5.dimension_variable` - связанная `IVariable7` с
  `Expression/Value`, если переменная найдена в variable surfaces;
- `constraints.api5_items` - ограничения, прочитанные через API5
  `ksGetObjConstraints` и распакованные как `ksConstraintParam`;
- `constraints.all_items` - объединенный список API7 + API5 ограничений;
- `constraints.projection_items` - UI-like projection constraints, включая
  `проекционная связь` и `проекция конечной точки`, когда они распознаны;
- `entities[*].projection.classification.projection_role` - различает
  `projected_object_candidate` и `projection_reference_geometry_candidate`;
- `entities[*].projection.ui_constraints` - projection-related constraints,
  привязанные к конкретной сущности;
- `entities[*].projection.drawing_object1.properties` - дополнительные API7
  флаги `IDrawingObject1` (`IsInAssociationView`, `IsCurve`, и т.п.);
- `constraint_state_summary` - сводка по `IDrawingObject1.ConstraintsState`
  для каждой сущности эскиза;
- `closure_audit.all_geometry` - read-only проверка замкнутости по всем
  line/arc endpoints;
- `closure_audit.primary_style` - read-only проверка замкнутости только по
  основному стилю линий (`Style == 1` по умолчанию), аналог UI-проверки
  замкнутости со стилем;
- `closure_audit.*.self_intersections` - приближённая проверка
  самопересечений: дуги дискретизируются в polyline и проверяются пересечения
  несоседних участков. Для `ICircleArc.Direction` используется семантика KOMPAS:
  `false` - против часовой стрелки от start к end, `true` - по часовой;
- `sketch_diagnostics.recommended_focus` - компактный список первоочередных
  проблем: открытый контур, ветвления, несколько контуров, неполностью
  параметризованные сущности;
- `diagnostics.variable_surfaces` - поверхности переменных на sketch/edit/view
  объектах;
- `projection_diagnostics` - блок 3D-проекционных данных, который теперь
  возвращается и для обычных успешно открытых эскизов, а не только как fallback;
  `edges[*].result.items[*].edge_points` содержит мировые концы `IEdge` через
  `GetPoint(0/1)`, а `directing_objects`/`association_object` показывают
  направляющие и ассоциативные объекты эскиза, если KOMPAS их предоставляет.

Публичный wrapper принимает `include_diagnostics`: оставляйте `true` для
исследований и ставьте `false`, если нужен более компактный ответ.

Сущности читаются из коллекций:

- `LineSegments` -> `segment`;
- `Arcs` -> `arc`;
- `Circles` -> `circle`;
- `Points` -> `point`;
- `Ellipses` -> `ellipse`.

Для координат используется cast к конкретным COM-интерфейсам:

- `ILineSegment`;
- `IArc`;
- `ICircle`;
- `IPoint`;
- `IEllipse`.

Это важно: без cast эталонный sketch возвращал entity counts, но координаты
отрезков/дуг приходили как `None`.

## Sketch diagnostics layer

`inspect_sketch_full` теперь возвращает отдельный исследовательский слой
`sketch_diagnostics`. Его нужно смотреть первым, когда эскиз не принимает
операция или состояние эскиза `under_constrained`.

Минимальный порядок анализа:

1. `sketch_diagnostics.closure_audit.primary_style.closed` - должен быть `true`
   для одного рабочего контура операции.
2. Если `closed=false`, смотреть `primary_style.gaps`: там координаты разрывов и
   references сущностей, чьи endpoints не нашли пару.
3. Если `branch_count > 0`, в основном контуре есть T-образные/ветвящиеся узлы;
   для автоматизированных операций это обычно надо разделить на разные эскизы.
4. Если `component_count > 1`, найдено несколько отдельных рабочих контуров.
5. Если `self_intersection_count > 0`, контур формально может быть замкнут, но
   перекручен/самопересечён и не пригоден для операции.
6. Затем смотреть `constraint_state_summary.not_full`: это сущности, у которых
   `IDrawingObject1.ConstraintsState` не `full`.

`closure_audit.all_geometry` намеренно включает оси и вспомогательные линии. Он
полезен для общей картины, но для `OP-002` и операций вращения/выдавливания
главный сигнал обычно `closure_audit.primary_style`.

Generation reports can also contain a `profile_preflight` step. It reuses the
same primary-style closure audit after sketch parameterization and before the
revolve update. A failed preflight means the generator intentionally stopped
before KOMPAS built from an open, branched, or self-intersecting primary profile.

`inspect_sketch_full` updates the target sketch before reading `ConstraintsState`
by default (`update_before_state=true`). This avoids stale under-constrained
readback immediately after reopening a document whose sketch becomes fully
defined after KOMPAS recomputes the solver state.

SDK notes:

- В SDK найдены `ISketch.ConstraintsState` и
  `IDrawingObject1.ConstraintsState`/`Constraints`.
- Также найдены APIs вида `ksIsCurveClosed`, `ICurve2D.IsClosed`,
  `IContour.Closed`, но они не являются прямым аналогом UI-команды, которая
  ставит красные точки в местах разрыва.
- UI-команды проверки замкнутости могут создавать/удалять маркеры и показывать
  диалоги, поэтому текущий слой реализован как read-only endpoint graph без
  изменения модели.

## Live-проверка

Проверка выполнена на эталоне:

`sample/live_outputs/пример вокруг себя.m3d`

Summary сохранен в:

`sample/live_outputs/inspect_sketch_full_reference_summary.json`

Полный слепок сохранен в:

`sample/live_outputs/inspect_sketch_full_reference_snapshot.json`

Целевой sketch:

`EXT_V_BOTH_HEIGHT_FORMULA_V3_LEFT_V_BODY_LEG_PATH`

Результат:

- `ok = true`;
- segments: `7`;
- arcs: `1`;
- circles: `0`;
- points: `0`;
- ellipses: `0`;
- line dimensions: `4`;
- constraints readback: `0` constraints found by current constraint surface scan.
- sketch `ConstraintsState`: `under_constrained` / `has_degrees_of_freedom`.

Первый segment теперь возвращает координаты:

```json
{
  "start": [-1.656190624504395e-15, 0.0],
  "end": [-1.656190624504395e-15, 13.5]
}
```

Первая arc теперь возвращает координаты:

```json
{
  "start": [-40.0, -13.574361074530819],
  "end": [-35.07379698404049, -15.874304974131086],
  "center": [-37.0, -13.574361074530819],
  "radius": 3.0,
  "direction": false
}
```

## Ограничения текущей версии

Dimensions читаются через существующий dimension readback. Для эталона получены
4 line dimensions с текстовыми nominal values (`40`, `13,5`, `40`, `20`), но
operation variables/expressions у этих размеров не извлечены.

Constraints для эталонного sketch текущий constraint scanner не обнаружил:

- просканировано owners: `8`;
- найдено constraint objects: `0`;
- sketch-level `ConstraintsState`: `under_constrained`.

Это может означать одно из двух:

- constraints действительно отсутствуют как отдельные API-objects;
- KOMPAS хранит их на другом surface, который текущий scanner еще не обходит.

С учетом `ConstraintsState = under_constrained` наиболее вероятно, что эталонный
эскиз не полностью ограничен и полный набор ограничений из него восстановить
нельзя. Для будущей production-реализации ограничения придется проектировать
самостоятельно на основе геометрии и размеров, а не копировать из эталона.

## Проверка реализации

Host-side modules и обе bridge-копии должны компилироваться своими runtime.
Поведенческая проверка выполняется через `inspect_sketch_full` на сохранённой
модели с повторным открытием документа и сравнением summary/snapshot. Synthetic
responses не заменяют live COM readback.

## Следующий шаг

Для self-wrapping hook phase 2 теперь можно использовать
`inspect_sketch_full_reference_summary.json` как исходный геометрический слепок:

- 7 отрезков;
- 1 дуга;
- координаты start/end/center/radius;
- 4 line dimensions из эталона.
- факт отсутствия найденных constraint objects и состояние `under_constrained`.

Если понадобится строгое сравнение constraints, нужно расширить constraint
scanner отдельной задачей после выяснения, на каком COM-surface KOMPAS хранит
ограничения эталонного эскиза.
