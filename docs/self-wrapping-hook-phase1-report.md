# Self-wrapping hook phase 1 report

Отчет относится к `tasks/21-self-wrapping-hook-phase1.md` и фиксирует только
исследование. Production hook-code не менялся: `parametric.py` не дорабатывался
под новый hook type. Bridge inspector позднее был расширен только для чтения
API5 constraints эталонных эскизов.

## Цель phase 1

Разобрать эталонную модель `sample/live_outputs/пример вокруг себя.m3d` и
проверить, можно ли через текущий API создать базовый 7-образный профиль
самозаворачивающегося зацепа без добавления нового сценария в продуктовый код.

## Эталонная модель

Файл:

`sample/live_outputs/пример вокруг себя.m3d`

Readback выполнялся через существующие bridge actions:

- `open_document`
- `list_features`
- `list_sketches`
- `list_sketch_entities`
- `list_sketch_dimensions`
- `list_sketch_constraints`

Сырые результаты сохранены в:

`sample/live_outputs/self_wrapping_bridge_readback.json`

## Дерево построения эталона

Bridge readback видит одну основную feature-операцию:

- `spring_body`
- тип: `evolution`
- reference: `1073760020`

Это важный ориентир: эталон уже собран как одно тело по траектории, а не как
набор отдельных вспомогательных кривых.

## Эскизы эталона

Readback нашел 4 эскиза.

### 1. `EXT_V_BOTH_HEIGHT_FORMULA_V3_LEFT_V_BODY_LEG_PATH`

Основной интересный эскиз самозаворачивающегося/V-образного участка.

Состав:

- segments: 7
- arcs: 1
- entity_count: 8
- line dimensions: 4

Вывод: форма не является одним простым arc/line pair. Это составной 2D-контур:
несколько прямых участков и одна дуга. Для реализации нельзя ограничиться
только `segment + arc + segment`, если нужно точно повторить эталон; минимальный
proof можно начинать с этой упрощенной схемы, но phase 2 должен уточнить весь
набор сегментов.

Уточненная интерпретация первого эскиза:

Эскиз состоит из вспомогательного каркаса и рабочего контура зацепа. Диагональные
линии начинаются в точке `(0, 13.5)`. Эта точка соответствует точке конца
основной спирали вне эскиза. Для фиксации ее положения в эскизе есть
вспомогательная вертикальная линия от начала координат до `(0, 13.5)`. Она имеет
ограничение вертикальности и размер с формулой радиуса пружины:

`(D - WD1) / 2`

В эталонном численном случае это `13.5`.

Вспомогательный каркас задает общие габариты зацепа:

- вспомогательная диагональ идет из точки конца спирали `(0, 13.5)` к узлу
  пересечения нижней вспомогательной горизонтали и левой вспомогательной
  вертикали;
- нижняя вспомогательная горизонталь задает высоту/вылет зацепа и имеет размер
  `40`;
- вспомогательная вертикаль от начала координат до начала нижней горизонтали
  задает половину ширины зацепа, в эталоне `20`; это центрирует полку зацепа
  относительно оси пружины, проходящей через начало координат;
- левая вспомогательная вертикаль задает полку зацепа и имеет полный размер
  ширины зацепа, в эталоне `40`;
- вспомогательная вертикаль от начала координат вверх задает радиус до точки
  конца спирали.

Все элементы вспомогательного каркаса должны быть связаны между собой
ограничениями совпадения точек. Это относится и к соединениям с началом
координат:

- нижний конец радиальной вертикали совпадает с началом координат;
- верхний конец радиальной вертикали совпадает с началом вспомогательной
  диагонали и началом рабочего диагонального участка;
- нижний конец центрирующей вертикали совпадает с началом нижней горизонтали;
- конец нижней горизонтали совпадает с нижним концом левой вертикали;
- нижний конец левой вертикали совпадает с концом вспомогательной диагонали;
- все эти связи должны быть `merge_points`, а не только совпадением численных
  координат.

Рабочий контур зацепа строится поверх этого каркаса:

- первый рабочий отрезок начинается в точке конца спирали `(0, 13.5)`;
- начало рабочего отрезка должно иметь `merge_points` с концом радиальной
  вспомогательной вертикали;
- рабочий отрезок идет вдоль вспомогательной диагонали;
- конец рабочего диагонального отрезка совпадает с концом дуги скругления;
- между рабочим диагональным отрезком и дугой требуется касательность;
- конец рабочего диагонального отрезка должен иметь связь с вспомогательной
  диагональю через `point_on_curve`, чтобы рабочий отрезок оставался на ее
  направлении;
- дуга скругления переходит во второй рабочий отрезок;
- между дугой и вторым рабочим отрезком также требуется `merge_points` и
  касательность;
- второй рабочий отрезок лежит на левой вспомогательной вертикали и должен быть
  закреплен аналогичным набором связей: совпадение конечных точек с дугой/полкой
  и принадлежность вспомогательной вертикали.

Практический вывод для реализации: эскиз нужно строить как параметрический
каркас плюс рабочий контур, а не как набор абсолютных координат. Размеры должны
висеть преимущественно на вспомогательном каркасе, а рабочий контур должен
держаться через совпадения точек, касательности и `point_on_curve` к
вспомогательным линиям.

### 2. `Эскиз:1`

Состав:

- segments: 4
- points: 1
- entity_count: 5
- dimensions: 1
- API5 constraints: 20
- state: `well_constrained` / `fully_defined`

Снимок:

`sample/live_outputs/inspect_sketch_full_reference_sketch1_snapshot.json`

Геометрия:

- segment 0, style 6: `(0, -13.5)` -> `(35.0737969840391, 15.874304974132746)`;
- segment 1, style 6: `(40, -20)` -> `(0, 13.5)`;
- segment 2, style 6: `(0, 13.5)` -> `(0, -13.5)`;
- segment 3, style 3: `(16.11940298507463, 0)` -> `(40, -20)`;
- point 0, style 127: `(40, -20)`.

Ручная интерпретация проекций:

- в `Эскиз:1` из первого эскиза спроецированы две сущности: диагональная линия и
  точка свободного конца полки зацепа;
- источник этих projection links текущими инструментами не читается: snapshot
  показывает сами projected candidates / projection constraints, но не объект
  первого эскиза, на который ведет ссылка ограничения;
- спроецированная диагональная линия добавлена как страховочная геометрия и не
  является критичной для дальнейшего построения;
- спроецированная точка свободного конца полки зацепа критична: она позволяет
  опереться на уже построенный первый эскиз без масштабного повторения
  вспомогательных построений и размеров.

По смыслу `Эскиз:1` во многом повторяет первый эскиз зеркально относительно оси
пружины. Диагональная линия в этом эскизе выступает как осевая линия. Далее она
будет использоваться для построения плоскости третьего эскиза.

Единственный размер связан с переменной `v277`:

`v277 = D1 - WD1 = 27`

Constraint readback через API5 показывает, что размерный объект сам участвует в
`merge_points` связях как partner. После расширения `inspect_sketch_full` ссылка
на размер `1073768027` резолвится в `partner_object.kind = "dimension"` и
`variable_name = "v277"`.

Основные связи `Эскиз:1`:

- segment 2 является вертикальной базой от `(0, 13.5)` к `(0, -13.5)` и имеет
  constraint `vertical`;
- segment 1 соединяет `(40, -20)` с `(0, 13.5)` и замыкает верхний узел с
  segment 2, а нижний узел с point 0 / segment 3;
- segment 3, style 3, начинается на кривой segment 1 и заканчивается в point 0;
- segment 0 начинается в нижней точке segment 2 и проходит через начальную точку
  segment 3 по `point_on_curve`;
- dimension `v277` связан `merge_points` с концами segment 0, segment 1 и
  segment 2, поэтому это не просто числовой размер, а полноценная constraint
  reference в эскизе;
- одна связь segment 1 имеет нерезолвнутый partner reference в API5 readback:
  `point_on_curve` для конечной точки `(0, 13.5)`. Этот объект не попадает в
  обычные collections segments/arcs/points/dimensions. По ручной интерпретации
  эталона это связано с проекционными объектами, источник которых API readback
  пока не раскрывает.

Практический вывод: `Эскиз:1` нужно воспроизводить не только как четыре отрезка и
точку. Для совместимости с эталоном нужно поддержать constraint-to-dimension
references и явно опираться на проекцию точки свободного конца полки из первого
эскиза. Source object проекции пока фиксируется вручную, не через inspector.

### 3. Isolated `Эскиз:1` probe

Добавлен live proof в `sample/live_self_wrapping_phase2_sketch.py` без изменения
production hook-code.

Артефакты:

- модель:
  `sample/live_outputs/self_wrapping_phase2_first_and_sketch1_v9.m3d`;
- отчет построения:
  `sample/live_outputs/self_wrapping_phase2_first_and_sketch1_report.json`;
- readback snapshot:
  `sample/live_outputs/self_wrapping_phase2_sketch1_probe_snapshot.json`.

Результат после сохранения и повторного `inspect_sketch_full`:

- segments: 4;
- points: 1;
- dimensions: 1;
- dimension variables linked: 1;
- API5 constraints: 19;
- failed count при построении: 0.

KOMPAS автоматически создал constraint-to-dimension references для размера
`D1 - WD1`, поэтому отдельный writer API для ручного создания таких связей на
этом шаге не понадобился. В probe sketch воспроизведены внутренние связи между
отрезками, точкой и размером. Эталон имеет 20 API5 constraints; оставшаяся
разница соответствует скрытой/проекционной `point_on_curve` reference
`1073768028`, которая не попадает в обычные entity/dimension collections.

### 4. Sketch-to-sketch projection write probe

Добавлен probe:

`sample/live_self_wrapping_projection_probe.py`

Артефакты:

- модель:
  `sample/live_outputs/self_wrapping_phase2_projected_sketch1_v10.m3d`;
- отчет:
  `sample/live_outputs/self_wrapping_phase2_projected_sketch1_report.json`;
- snapshot:
  `sample/live_outputs/self_wrapping_phase2_projected_sketch1_snapshot.json`.

Проверялась прямая проекция sketch-объектов из первого эскиза во второй:

- диагональный segment `(0, 13.5)` -> `(40, -20)`;
- явная point entity в точке свободного конца полки `(40, -20)`;
- fallback: вся полка segment `(40, -20)` -> `(40, 20)`.

Проверенные варианты `ISketch.AddProjectionOf`:

- raw `ILineSegment` / `IPoint`;
- cast к `IEntity`, `IDrawingObject`, `IModelObject`;
- передача самого source sketch;
- передача `source_sketch.Edges(...)`;
- вызов до `EndEdit` source sketch, когда source objects имеют `Valid=True` и
  ненулевые references;
- вызов после `EndEdit/Update` source sketch;
- target sketch с `BeginEdit` и без `BeginEdit`.

Результат:

- raw `ILineSegment` / `IPoint` и cast этих объектов к API7-интерфейсам не
  создают projected entities: `AddProjectionOf` возвращает `None` без COM error;
- рабочий путь найден через `source_sketch.Edges(...)`: метод может вернуть не
  collection, а одиночный `IEdge`, его нужно передавать в `target_sketch.AddProjectionOf`;
- target sketch должен быть открыт через `BeginEdit()` на момент вызова
  `AddProjectionOf`, после чего нужно выполнить `EndEdit()` / `Update()`;
- construction geometry style 6 не становится sketch edge для этого пути;
- рабочая line style 1 становится `IEdge` и успешно проецируется.

Сохраненный `v10` после повторного открытия содержит:

- projected diagonal segment `(0, 13.5)` -> `(40, -20)`;
- projected fallback shelf segment `(40, -20)` -> `(40, 20)`;
- `projection_constraint_count = 2`;
- `projected_object_count = 2`.

Практический вывод: для второго эскиза можно воспроизвести эталонный подход через
реальные KOMPAS projection links, если исходные элементы доступны как
`source_sketch.Edges(...)`. Отдельная point entity через `AddProjectionOf` пока не
проецируется, поэтому рабочий fallback для точки свободного конца полки -
проецировать всю полку и использовать ее конец.

### 5. `Эскиз:1` через projection links в phase2 flow

Добавлен bridge action `project_sketch_edges`, чтобы выполнять проекцию в том же
`BridgeRunner`-процессе и активном 3D-документе сразу после создания первого
эскиза. Это важно: после сохранения/переоткрытия `source_sketch.Edges(...)` может
возвращать wrapper, который `AddProjectionOf` не принимает.

Артефакты:

- модель:
  `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v15.m3d`;
- отчет:
  `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v15_report.json`;
- snapshot:
  `sample/live_outputs/self_wrapping_phase2_projected_sketch1_v15_snapshot.json`.

Результат `SELF_WRAPPING_PHASE2_LEFT_SKETCH1_PROJECTED`:

- segments: 2;
- arcs: 0;
- entity_count: 2;
- `projected_object_count = 2`;
- `projection_constraint_count = 2`.

Спроецированы два прямых `IEdge` из первого эскиза:

- диагональ: `(0, 13.5)` -> `(-35.07379698404049, -15.874304974131086)`;
- fallback-полка: `(-40, -13.574361074530819)` -> `(-40, 20)`.

Дуга первого эскиза отфильтрована через `only_straight=True`, duplicate edge refs
отбрасываются. Это подтверждает рабочий путь для построения зависимого
`Эскиз:1`: проецировать диагональ и всю полку из первого эскиза, а не пытаться
проецировать endpoint point напрямую.

### 6. Возврат построений якоря поверх projected `Эскиз:1`

Артефакты:

- модель:
  `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v24.m3d`;
- отчет:
  `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v24_report.json`;
- snapshot:
  `sample/live_outputs/self_wrapping_phase2_projected_sketch1_v24_snapshot.json`.

В `SELF_WRAPPING_PHASE2_LEFT_SKETCH1_PROJECTED` добавлены построения якоря поверх
двух projected линий:

- vertical base: `(0, 13.5)` -> `(0, -13.5)`, style 6;
- mirror diagonal: `(0, -13.5)` -> `(-35.07379698404049, 15.874304974131086)`,
  style 6;
- work axis: `(-16.11940298507618, 0)` -> `(-40, 20)`, style 3;
- shelf point: `(-40, 20)`, style 127.

Snapshot v24:

- segments: 5;
- points: 1;
- entity_count: 6.

Стиль самих projected segments теперь меняется на auxiliary. Рабочий путь:

1. Сначала обычный `ksGetObjParam` / `ksSetObjParam` по API7 `Reference`
   projected segment пробуется и ожидаемо не срабатывает.
2. Затем берется середина projected segment из readback geometry.
3. В открытом sketch editor вызывается `ksFindObj(mid_x, mid_y, tolerance)`.
4. Возвращенный внутренний API5 ref передается в
   `ksSetObjectStyle(found_ref, 6)`.

Для v24:

- projected diagonal: API7 ref `1073742821`, internal API5 ref `1073742833`,
  style `1 -> 6`;
- projected shelf: API7 ref `1073742822`, internal API5 ref `1073742834`,
  style `1 -> 6`.

Cleanup после UI-like выбора:

- после `ksSetObjectStyle` вызывается `ksLightObj(found_ref, 0)` для найденного
  внутреннего ref;
- после серии изменений вызывается `ksEndObj()`; в v24 он возвращает `0`, что
  означает, что активного составного объекта/режима для закрытия не было, но
  вызов безопасен;
- затем выполняется `EndEdit()` / `Update()` эскиза.

Проверенные отрицательные пути:

- повторный `BeginEdit` и доступ через API7 `LineSegments` collection: projected
  lines не попадают в editable collection;
- API5 `ksGetObjParam` / `ksSetObjParam` с `ko_LineSegParam = 11`: projected refs
  не читаются как line segment params;
- перебор базовых `parType` также не дал параметров для projected refs.

Дополнительная проверка после v21:

- после стабилизации/сохранения эскиза `LineSegments` collection может видеть
  projected lines как `IDrawingObject`, и cast к `ILineSegment` позволяет временно
  поставить `Style = 6`;
- после `EndEdit()` / regeneration стиль снова становится `1`, то есть это
  временный result object, а не сохраняемое свойство projection feature;
- смена стиля исходных линий первого эскиза до или после projection не заставляет
  projected lines унаследовать auxiliary style;
- `ksGetObjectStyle` / `ksSetObjectStyle` по API7 `Reference` projected segment
  возвращают `0` / `False`;
- `ksFindObj` требует API5 `ActiveDocument2D`; в fresh `DispatchEx` API7 session
  API5 document2D может быть недоступен, поэтому этот fallback должен выполняться
  в обычной API5/API7 KOMPAS session, как в phase2 runner.

Итог v24: две projected source-линии имеют style 6, возвращенные построения якоря
остались на своих стилях (`vertical/mirror` style 6, `work_axis` style 3,
`shelf_point` style 127). Инспекторская эвристика `projection_role` после смены
стиля стала менее надежной, потому что все объекты эскиза имеют общий parent
`Type=10031`; для подтверждения смены стиля использовать фактические `Style` и
`post_anchor_report.ksfind_style_refs`.

### 3. `Эскиз:2`

Состав:

- segments: 2
- arcs: 1
- points: 2
- entity_count: 5
- line dimensions: 1

Похоже на дополнительный hook/переходный эскиз.

### 4. `spring_wire_profile`

Эскиз сечения проволоки.

Состав:

- circles: 1
- diametral dimensions: 1

## Ограничения эталона

Старая entity surface `Constraints` по-прежнему часто возвращает
`constraint_count = 0`, но API5 surface теперь читается через
`inspect_sketch_full`.

Для `Эскиз:1` API5 readback возвращает 20 constraints, включая:

- `merge_points`;
- `point_on_curve`;
- `vertical`;
- связи с размером `v277` как отдельным partner object.

Практический вывод: для анализа эталона нужно использовать `inspect_sketch_full`,
а не старый `list_sketch_constraints`. При реализации constraints все равно нужно
проектировать явно и валидировать live в KOMPAS, потому что скрытые/проекционные
references пока не полностью декодированы.

## API proof model

Для проверки создания базовой 7-образной геометрии был создан отдельный
исследовательский файл:

`sample/live_outputs/self_wrapping_phase1_probe.m3d`

Отчет по созданию:

`sample/live_outputs/self_wrapping_phase1_probe_report.json`

Proof создавал:

- обычную construction spring model;
- новый sketch `SELF_WRAPPING_HOOK_PHASE1_7_PROFILE`;
- 3 sketch entities:
  - vertical body leg segment;
  - wrap arc;
  - horizontal return tail segment;
- 5 constraints:
  - fixed start point;
  - vertical body leg;
  - horizontal tail;
  - merge body leg end to arc start;
  - merge arc end to tail start.

Результат API proof:

- sketch created: yes;
- entity_count: 3;
- constraints applied: 5/5;
- geometry creation: ok;
- constraints: ok;
- dimensions: failed for planned generic kinds `line` and `radius`.

## Dimension writer gap

В proof-модели generic `create_sketch_entities` вернул:

- `unsupported_dimension_kind` для `kind = line`;
- `unsupported_dimension_kind` для `kind = radius`.

Это не ошибка геометрии hook-а, а ограничение текущего generic writer-а для
исследовательского action. Для phase 2 есть два варианта:

1. Использовать уже поддерживаемые dimension kinds bridge, если они подходят для
line/radius в нужной коллекции.
2. Доработать writer размеров так, чтобы он создавал line length и radius
   dimensions для segment/arc entities.

Без этого 7-образный sketch можно создать и связать constraints, но нельзя
полностью параметризовать размерами через текущий generic action.

## Предлагаемая схема phase 2

Не добавлять сразу новый production hook type. Сначала сделать отдельный
side-aware builder для одного самозаворачивающегося зацепа и проверить live.

Минимальный план:

1. Создать body spiral как сейчас для extension spring.
2. Получить endpoint основной спирали:
   - left side: start point;
   - right side: end point.
3. Построить плоскость на endpoint перпендикулярно основной спирали.
4. Создать sketch self-wrapping hook на этой плоскости.
5. В sketch построить параметрический каркас и рабочий контур:
   - каркас: радиальная вертикаль, нижняя горизонталь, левая вертикаль,
     диагональ и центрирующая вертикаль;
   - рабочий контур: диагональный участок, дуга скругления, вертикальная полка;
   - связи: `merge_points`, касательность, `point_on_curve`.
6. Наложить constraints в момент `BeginEdit()` sketch, как было важно для
   bent-coil auxiliary sketches.
7. После стабильной геометрии добавить размеры/переменные.
8. Подключить sketch path к финальному `full_path_sequence` и проверить один
   `IEvolution` body.

## Риски

1. Эталонный основной path sketch сложнее минимальной 7-схемы: это
   параметрический вспомогательный каркас плюс рабочий контур. Ограничения все
   равно придется проектировать явно.
2. В `Эскиз:1` осталась как минимум одна нерезолвнутая API5 reference
   `1073768028`, вероятно скрытая или проекционная.
3. Generic dimension writer не поддерживал generic `line/radius` kinds в раннем
   proof; для текущих live scripts нужно использовать поддерживаемые
   `line_length` и `arc_radius`.

## Что уже подтверждено

- Эталонная модель открывается и читается bridge actions.
- Эталон собран как `spring_body` evolution.
- Ключевой path sketch эталона содержит 7 segments и 1 arc.
- Смысл этих элементов разобран: часть отрезков является вспомогательным
  каркасом, а рабочий контур состоит из диагонального участка, дуги и
  вертикальной полки.
- Wire profile эталона - отдельный `spring_wire_profile` circle sketch.
- Через API можно создать 7-подобный sketch с segment/arc/segment.
- Constraints для proof sketch создаются через bridge API и применяются 5/5.
- `inspect_sketch_full` теперь читает API5 constraints и резолвит partner links
  не только на entities, но и на dimensions.

## Следующий практический шаг

Для phase 2 лучше начать не с production `hook_type`, а с live builder script:

- вход: side (`left/right`), wire diameter, body diameter, body endpoint;
- выход: single self-wrapping sketch path на endpoint plane;
- проверка: sketch fully constrained, path пригоден для `full_path_sequence`.

После live-подтверждения переносить в `parametric.py`/bridge как новый hook
contract.
## Context Recovery: Sketch1 Constraint Strategy

After the environment move, re-check the task from readback data before adding more code. The stable generated baseline is still the projected/decorated sketch (`v24` shape, now kept as projection/style/anchor only in the live script). It contains:

- projected diagonal, auxiliary style `6`;
- projected shelf fallback, auxiliary style `6`;
- vertical base auxiliary line at `x = 0`;
- mirrored lower diagonal auxiliary line;
- work axis style `3`;
- one free shelf point.

The reference `Эскиз:1` remains the guide, but not a literal entity-for-entity target:

- it has `20` API5 constraints and `1` line dimension with expression `D1 - WD1`;
- some constraint partners are projected/hidden refs (`1073768782`, `1073768783`) rather than normal visible geometry entities;
- the generated sketch intentionally uses the shelf edge as a fallback for the free shelf endpoint, because direct point projection did not persist through `AddProjectionOf`.

Therefore, do not try to blindly replay all reference constraints onto the generated sketch. The next safe step is an isolated API5 probe that applies one constraint to the already-decorated sketch and verifies it through `inspect_sketch_full`. Only after one relation is proven should the minimal fallback-specific constraint set be integrated:

- vertical constraint on `vertical_base`;
- merge `vertical_base` top with projected diagonal top;
- merge `vertical_base` bottom with mirrored diagonal bottom;
- point-on-curve relation for the work-axis start against the upper/lower diagonals;
- merge work-axis/free endpoint with projected shelf fallback/free point;
- one driving line dimension on `vertical_base` with expression `D1 - WD1`.

## Live Result: Creation-Time Sketch1 Constraints

Post-factum constraint attempts on a saved/reopened projected sketch are not reliable:

- API7 `LineSegments` is empty after `BeginEdit` on the reopened generated projected sketch;
- API5 `ksFindObj` can find an internal ref, but `ksSetObjConstraint` on that hit-test ref returned `0` and readback did not persist a constraint;
- `ksSetObjConstraint` on the entity ref from `inspect_sketch_full` also returned `0`.

The working path is to create constraints immediately while adding anchor geometry, before `EndEdit`, while live COM objects from `_add_sketch_line_segment` / `_add_sketch_point` are still available.

Validated artifact:

- model: `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v37.m3d`;
- report: `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v37_report.json`;
- snapshot: `sample/live_outputs/self_wrapping_phase2_projected_sketch1_v37_snapshot.json`.

`v37` readback:

- segments: `5`;
- points: `1`;
- projected objects: `2`;
- projection constraints: `3`;
- API5/all constraints: `10`;
- dimensions: `1`;
- dimension variable expression: `D1 - WD1`.

Creation-time constraints now validated:

- `vertical` on `vertical_base`;
- `merge_points` between `vertical_base.bottom` and `mirror_diagonal.start`;
- `point_on_curve` for `work_axis.start` on `mirror_diagonal`;
- `merge_points` between `work_axis.end` and `shelf_point`;
- driving line dimension on `vertical_base` with expression `D1 - WD1`.

Remaining work: projected-to-anchor constraints still need a separate strategy, because projected entities do not survive as normal API7 line objects in the reopened/editable collection. Do not add broad post-pass constraints until projected entity handles are proven at creation time.

## Live Result: Same-Edit Projection Constraints

The projected-to-anchor constraints must be created in the same sketch edit session as `AddProjectionOf`. Closing the sketch and reopening it loses editable API7 handles for projected entities.

Validated best artifact for this phase:

- model: `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v45.m3d`;
- report: `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v45_report.json`;
- snapshot: `sample/live_outputs/self_wrapping_phase2_projected_sketch1_v45_snapshot.json`.

`v45` readback:

- entities: `5` segments, `1` point;
- API5/all constraints: `19`;
- dimensions: `1`;
- dimension expression: `D1 - WD1`;
- state: still `under_constrained`.

The visible construction now matches the intended constraint scheme:

- projected diagonal and projected shelf are used as reference geometry;
- `vertical_base.top` is tied to the projected diagonal side;
- `vertical_base.bottom` is tied to the mirrored diagonal;
- `vertical_base` has a vertical constraint and the `D1 - WD1` length dimension;
- `work_axis.start` is on both the projected diagonal and mirrored diagonal;
- `work_axis.end`, `shelf_point`, and the projected shelf free endpoint are tied together.

The remaining underdefinition appears to come from the fallback projected shelf line. The reference sketch projects/uses a point-like free-end reference, while the generated sketch projects the whole shelf segment because direct point projection did not persist. This extra projected line likely contributes an extra degree of freedom to the sketch state. A probe adding `vertical` to the projected shelf did not change the state and should not be kept as final logic.

Next useful investigation: find a durable way to project the shelf free endpoint as a point/vertex reference, or replace the shelf-line fallback with a point-like construction that remains linked to source geometry without adding an extra underdefined line entity.

## Saved Artifact Note

Earlier live artifacts after the first partial save could be missing later-created sketches if KOMPAS was closed with unsaved changes. The live scenario now performs a final `save_document` after projection, anchor geometry, constraints, dimensions, and snapshot capture.

First verified saved artifact:

- model: `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v47.m3d`;
- report: `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v47_report.json`;
- saved-file verification: `sample/live_outputs/self_wrapping_phase2_v47_saved_file_verification.json`.

The saved file was reopened from disk and verified to contain both key sketches:

- `SELF_WRAPPING_PHASE2_LEFT_FIRST_SKETCH`;
- `SELF_WRAPPING_PHASE2_LEFT_SKETCH1_PROJECTED`.

The reopened projected sketch readback matches the working state: `5` segments, `1` point, `1` dimension, `19` API5 constraints, and `D1 - WD1` linked through the dimension variable.

## Saved Artifact: Fully Defined Sketch1

User review found two missing semantic constraints in the generated sketch:

- the additional diagonal line also has to terminate at the projected hook shelf free end, independently of the axis line;
- the axis start point has to lie on both diagonals, not only one.

The generated geometry was corrected so the additional diagonal runs from the lower end of `vertical_base` to the projected shelf free end. The constraint set now includes separate links for the diagonal, axis, and shelf point at that free end, plus point-on-curve links from the axis start to both diagonals.

The projected curve style regression was also fixed by restoring the API5 hit-test style pass after anchor/constraint creation. Direct `Style` assignment during projection is not enough; the durable style change is still the `ksFindObj`/`ksSetObjectStyle` pattern from `SKETCH-003`.

Verified saved artifact:

- model: `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v48.m3d`;
- report: `sample/live_outputs/self_wrapping_phase2_first_and_projected_sketch1_v48_report.json`;
- saved-file verification: `sample/live_outputs/self_wrapping_phase2_v48_saved_file_verification.json`.

The file was reopened from disk after final save. The projected sketch readback is now `well_constrained` / `fully_defined`:

- `5` segments;
- `1` point;
- `1` dimension;
- `25` API5 constraints;
- `4` projection constraints;
- `2` projected objects;
- projected/reference construction segments style `6`;
- axis segment style `3`;
- dimension expression `D1 - WD1` remains linked.

## Live Result: Axis Plane Through Sketch1 Axis

Next construction step creates the plane that will host the self-wrapping hook-end sketch. The plane is created by the KOMPAS operation "plane through edge parallel/perpendicular to face": use the finished Sketch1 axis as the edge, XOY as the base plane, and perpendicular mode.

Implementation details:

- bridge action: `create_plane_by_edge_and_plane`;
- COM operation: `Planes3D.Add(23)` cast to `IPlane3DByEdgeAndPlane`;
- inputs: `Edge`, `Plane`, `Parallel=False`;
- source sketch: `SELF_WRAPPING_PHASE2_LEFT_SKETCH1_PROJECTED`;
- axis selection: segment style `3`; when sketch edge geometry is not readable, use the extra `Edges(2)` candidate not present in `Edges(1)` as the axis edge fallback;
- base plane: XOY.

Verified saved artifact:

- model: `sample/live_outputs/self_wrapping_phase2_first_projected_and_axis_plane_v50.m3d`;
- report: `sample/live_outputs/self_wrapping_phase2_first_projected_and_axis_plane_v50_report.json`;
- saved-file verification: `sample/live_outputs/self_wrapping_phase2_v50_saved_file_verification.json`.

The saved file was reopened from disk. It contains the two self-wrapping sketches and the new plane:

- `SELF_WRAPPING_PHASE2_LEFT_FIRST_SKETCH`;
- `SELF_WRAPPING_PHASE2_LEFT_SKETCH1_PROJECTED`;
- `SELF_WRAPPING_PHASE2_AXIS_PERP_PLANE`.

The reopened projected sketch remains `well_constrained` / `fully_defined` with `25` API5 constraints and the `D1 - WD1` dimension still linked.

## Reference Sketch2 Snapshot

Reference file:

- `sample/live_outputs/пример вокруг себя.m3d`.

Captured artifacts:

- full snapshot: `sample/live_outputs/inspect_sketch_full_reference_sketch2_snapshot.json`;
- compact analysis: `sample/live_outputs/inspect_sketch_full_reference_sketch2_analysis.json`;
- edit-entry probe: `sample/live_outputs/reference_sketch2_beginedit_probe.json`.

`Эскиз:2` is the final hook path sketch where the wire reaches itself and starts wrapping around itself. The normal bridge-runner call initially produced only a partial snapshot because `BeginEdit` returned `None`; direct document activation followed by direct bridge inspection worked. `BeginEdit`, `BeginEditEx(True/False/0/1/2)` all entered the sketch once the document was active.

Readback summary:

- state: `under_constrained` / `has_degrees_of_freedom` in the reference;
- entities: `2` line segments, `1` arc, `2` points;
- visible dimensions: `1` line dimension;
- API5/all constraints: `16`;
- constraint kinds: `11` merge-points, `4` tangent-two-curves, `1` vertical.

Entity map:

- `long_tangent_segment` (`1073751870`): from approximately `(0, -43.5073)` to `(-2.9959, -12.6488)`;
- `right_vertical_segment` (`1073751871`): from `(3.01, -12.3579)` to `(3.01, -18.3579)`;
- `turn_arc` (`1073751872`): center near `(0, -12.3579)`, radius `3.01`, start `(-2.9959, -12.6488)`, end `(3.01, -12.3579)`, clockwise/readback direction `true`;
- `arc_center_point` (`1073751873`): coincident with the arc center;
- `long_segment_end_point` (`1073751874`): coincident with the long segment far end near `(0, -43.5073)`.

Dimensions and variables:

- line dimension `1073751875` on `right_vertical_segment`, variable `v291`, expression `6`, value `6`;
- sketch variables include `v290`, radial dimension, expression `P1`, value `3.01`; the visible dimension collection did not expose this as a normal dimension item, but the arc radius is clearly parameterized by `P1`.

Important constraints to reproduce:

- far endpoint point coincident with `long_tangent_segment.start`;
- `long_tangent_segment.end` coincident with `turn_arc.start`;
- `long_tangent_segment` tangent to `turn_arc`;
- `right_vertical_segment.start` coincident with `turn_arc.end`;
- `right_vertical_segment` tangent to `turn_arc`;
- `right_vertical_segment` has vertical constraint;
- line dimension `6` constrains `right_vertical_segment` length;
- `arc_center_point` coincident with `turn_arc.center`;
- arc radius driven by `P1`.

User review clarified that KOMPAS UI reports the reference sketch as fully defined. The `under_constrained` readback is likely an inspector limitation: the current inspector does not fully account for the radial dimension and some projection/dimension relationships. Treat the UI state and semantic construction as authoritative here.

Sketch2 construction intent:

- Start from two projected reference points. They should come from the two ends of the previous sketch axis. If endpoint projection is not available, projecting the whole previous axis is an acceptable fallback.
- The first projected point is the previous contour endpoint. The new contour line starts there.
- The second projected point is where this sketch plane intersects the original first-sketch diagonal; it is also the center of the wrapping arc.
- A tangent line starts from the first projected point, then meets the arc by coincident endpoint and tangent constraints.
- The arc is centered on the second projected point and wraps around that point.
- The arc then transitions by coincident endpoint and tangent constraints into a vertical return/tail line.
- The arc radius is driven by `P1` (`v290 = P1 = 3.01` in the reference), so the wire body clears itself instead of touching itself.
- The return/tail length is driven by the visible linear dimension (`v291 = 6` in the reference). Generated construction should expose this through its own named variable rather than leaving only an anonymous `v*` variable.
## Live Result: Generated Sketch2 Path

Generated artifact:

- model: `sample/live_outputs/self_wrapping_phase2_with_sketch2_v57.m3d`;
- report: `sample/live_outputs/self_wrapping_phase2_with_sketch2_v57_report.json`;
- saved-file verification: `sample/live_outputs/self_wrapping_phase2_v57_saved_file_verification.json`.

The model now includes `SELF_WRAPPING_PHASE2_SKETCH2_PATH` on `SELF_WRAPPING_PHASE2_AXIS_PERP_PLANE`. It projects the previous sketch axis as an auxiliary reference line, then builds the final hook path from that projection:

- projected axis reference, style `6`;
- tangent line starting at the previous contour endpoint;
- wrapping arc centered on the other projected axis endpoint;
- return/tail line after the arc;
- center point and endpoint point;
- tail line dimension expression `HT1`, value `6`.

Arc direction was checked using the `ARC-001` rule, not only the raw `direction` flag. The generated `v57` arc has the same short sweep class as the reference: approximately `174.45°`. The earlier `v56` variant produced the long-side sweep of approximately `185.55°`, so `v57` is the corrected direction.

Remaining technical gap: the generated arc has geometric radius `3.01`, but a true radial dimension with expression `P1` is not yet created/read back as a dimension variable. The reference exposes this through sketch variable `v290 = P1`. Add a real radial dimension before considering Sketch2 fully parameterized by catalog rules.

## Live Result: Finished Sketch2 Parameterization

Verified saved artifact:

- model: `sample/live_outputs/self_wrapping_phase2_with_sketch2_v59.m3d`;
- report: `sample/live_outputs/self_wrapping_phase2_with_sketch2_v59_report.json`;
- saved-file verification: `sample/live_outputs/self_wrapping_phase2_v59_saved_file_verification.json`.

User review found the final missing items for Sketch2:

- radial dimension on the wrapping arc;
- horizontal constraint on the return/tail line;
- named variable for tail length.

`v59` addresses these items. After reopening the saved file from disk, `SELF_WRAPPING_PHASE2_SKETCH2_PATH` is `well_constrained` / `fully_defined`.

Readback:

- entities: `3` segments, `1` arc, `2` points;
- API5/all constraints: `24`;
- constraint kinds: `19` merge-points, `4` tangent-two-curves, `1` horizontal;
- projection constraints: `5`;
- projected objects: `5`;
- visible dimension collection: `1` line dimension;
- sketch variable surface includes radial dimension variable `v277`, expression `SWR1`, value `3.01`;
- sketch variable surface includes tail length variable `v276`, expression `HT1`, value `6.0`.

Note: the original reference uses `P1` for the radial expression. In the generated model `P1` was already occupied with value `4.0`, so the generated self-wrapping radius uses `SWR1 = 3.01` to avoid silently changing an existing base-model parameter. The radial dimension itself is now present and driving.

## Curve Fillet Probe: Direct FilletCurves

Goal: investigate replacing the older trim/connect 3D-curve transition mechanism with the native KOMPAS 3D curve fillet operation, so the transition is controlled by an actual radius.

Existing code paths:

- old robust-but-complex path: manually create `TrimmedCurves`, then connect/fillet those prepared curves;
- desired path: native `FilletCurves.Add()` / `IFilletCurve` with `Curve1`, `Curve2`, `Radius`, `TrimCurve1=True`, `TrimCurve2=True`.

Probe artifacts:

- all-edge direct probe: `sample/live_outputs/self_wrapping_curve_fillet_direct_probe_v1_report.json`;
- all-edge direct probe model: `sample/live_outputs/self_wrapping_curve_fillet_direct_probe_v1.m3d`;
- compact inspection: `sample/live_outputs/self_wrapping_curve_fillet_direct_probe_v1_inspection_compact.json`;
- spiral-to-first-contour focused probe: `sample/live_outputs/self_wrapping_curve_fillet_spiral_to_first_contour_probe_v1_report.json`;
- first-to-second cutpoint probe: `sample/live_outputs/self_wrapping_curve_fillet_first_shelf_to_sketch2_line_cutpoint_v2_report.json`.

Findings:

- Native `FilletCurves` works directly for the spiral-to-first-contour joint without manually creating `TrimmedCurves`.
- In the broad probe, two first-sketch edge candidates accepted direct native fillets against the spiral; the meaningful one for the transition is the first contour edge, not the shelf edge.
- The focused spiral-to-first-contour probe succeeded without cut points: the fillet is valid and preserves radius `3.0`.
- A cut point guessed as `(0, 13.5, 0)` for the same joint was wrong: KOMPAS created an invalid fillet with radius `0`.
- A broad first-contour-to-second-contour all-pairs probe is unsafe: inappropriate pairs can hang behind KOMPAS modal dialogs or long COM calculations.
- A focused first-shelf-to-Sketch2-start probe with cut point `(-40, 20, 0)` returns quickly, but creates invalid fillets with radius `0`. This means the chosen 3D cut point or selected edge representation is not acceptable to `IFilletCurve` for that cross-plane joint.
- Follow-up order probe on a unique source/output file proved that the same first-shelf-to-Sketch2-start curve pair is valid when no manual cut point is forced. All tested parameter orders produced valid saved fillets with radius `3.01`. The saved-file reopen check also reports radius `3.01` for each variant.

Current conclusion:

- Native `FilletCurves` is viable and should replace the trim/connect mechanism where the input curve pair and side selection are known.
- For the spiral-to-first-contour joint, the native operation is already proven enough for the next integration probe.
- For the first-contour-to-second-contour joint, the correct input pair is the first sketch shelf edge and the Sketch2 start line edge. Do not force a guessed cut point. Native `FilletCurves` with the two edges, `Radius=3.01`, `TrimCurve1=True`, and `TrimCurve2=True` is stable.

Additional probe artifacts:

- order probe: `sample/live_outputs/self_wrapping_curve_fillet_order_probe_v1_report.json`;
- order probe model: `sample/live_outputs/self_wrapping_curve_fillet_order_probe_v1.m3d`;
- order probe saved-file check: `sample/live_outputs/self_wrapping_curve_fillet_order_probe_v1_reopen_check.json`.

## Curve Fillet Probe: Contour3D Usability

Goal: verify whether native `FilletCurve` results can be used downstream as contour/path elements, not only displayed as standalone auxiliary curves.

Probe artifacts:

- report: `sample/live_outputs/self_wrapping_curve_fillet_contour_combo_probe.json`;
- model: `sample/live_outputs/self_wrapping_curve_fillet_contour_combo_probe.m3d`;
- earlier two-joint contour report: `sample/live_outputs/self_wrapping_curve_fillet_contour_probe_report.json`.

Findings:

- `FilletCurve` can be inserted into `Contour3D.Edges` and produces a valid contour.
- A contour made from `fillet_only` is valid and reports `EdgesCount = 1`.
- A contour made from `[first_edge, fillet, second_edge]` is valid, but reports `EdgesCount = 2` even though three source objects were supplied.
- This means native fillet results are usable for downstream path construction, but the old contour completeness check `EdgesCount == len(source_curves)` is too strict when native `FilletCurve` objects are part of the path. KOMPAS may collapse/merge the fillet and adjacent trimmed input portions into fewer contour edges.

Implementation implication:

- When building a main path that includes native `FilletCurve`, use `allow_incomplete=True` or a fillet-aware completeness rule. Do not reject a valid contour only because `EdgesCount` is lower than the number of source objects.
- Still verify contour validity, saved-file reopen, and downstream operation success before replacing the production trim/connect path.

Open issue: UI exposes native curve fillets like a container with trimmed input curves and the fillet arc selectable from a dropdown/tree. COM probes so far do not expose those internal selectable parts through `IFilletCurve`, `OwnerFeature.ModelObjects(...)`, `SubFeatures(...)`, dynamic `Edges/GetEdges/ResultCurves`, or similar dispatch names. This matters for chained fillets, where the second fillet may need to select a trimmed sub-curve produced by the first fillet. Current safe automation capability is: use the whole `FilletCurve` object as a contour/path element. Selecting an internal trimmed child of a previous fillet remains unresolved and likely needs a UI-like selection/tree-reference investigation.

## Curve Fillet Smoke Test: Both Self-Wrapping Joints

Final smoke-test before body construction:

- script: `sample/live_curve_fillet_self_wrapping_smoke.py`;
- source copy: `sample/live_outputs/self_wrapping_curve_fillet_smoke_source_v1.m3d`;
- output model: `sample/live_outputs/self_wrapping_curve_fillet_smoke_v1.m3d`;
- report: `sample/live_outputs/self_wrapping_curve_fillet_smoke_v1_report.json`;
- reopen check: `sample/live_outputs/self_wrapping_curve_fillet_smoke_v1_reopen_check.json`.

The smoke-test creates two native KOMPAS `FilletCurves` with radius `3.0`, matching the first-sketch fillet radius (`SFR1`):

- `smoke_spiral_to_first_contour`: spiral to the first contour start edge;
- `smoke_first_contour_to_second_contour`: first contour shelf edge to the Sketch2 start line.

Both fillets are valid immediately after creation and remain valid after saving and reopening the model from disk:

- radius: `3.0`;
- `TrimCurve1=True`;
- `TrimCurve2=True`.

This confirms the native curve-fillet operation is viable for both self-wrapping transition joints without the old manual `TrimmedCurves` + connect-curve mechanism.

## Curve Fillet Smoke Test: Radius Expression Binding

The previous smoke-test verified the numeric radius value. User clarified that the actual requirement is stronger: the 3D curve fillet radius field must be driven by the same expression as the first-sketch fillet radius, `SFR1`, not merely equal to `3.0` at creation time.

Expression smoke-test artifacts:

- script: `sample/live_curve_fillet_self_wrapping_smoke_expression.py`;
- source copy: `sample/live_outputs/self_wrapping_curve_fillet_smoke_expr_source_v1.m3d`;
- output model: `sample/live_outputs/self_wrapping_curve_fillet_smoke_expr_v1.m3d`;
- report: `sample/live_outputs/self_wrapping_curve_fillet_smoke_expr_v1_report.json`;
- reopen check: `sample/live_outputs/self_wrapping_curve_fillet_smoke_expr_v1_reopen_check.json`.

Implementation:

- create each native `FilletCurve` with numeric radius `3.0`;
- inspect operation variables;
- bind the operation variable with `ParameterNote == "Радиус"` to expression `SFR1` using `_bind_operation_variables`;
- update the fillet;
- save and reopen from disk.

Reopen result:

- `smoke_expr_spiral_to_first_contour`: valid, radius `3.0`, trim flags true, operation variable `Радиус` expression `SFR1`;
- `smoke_expr_first_contour_to_second_contour`: valid, radius `3.0`, trim flags true, operation variable `Радиус` expression `SFR1`.

Conclusion: native 3D curve fillets can be parameterized by `SFR1` through operation-variable binding. This is the correct integration path; numeric-only radius assignment is not sufficient for production.

## Integrated Phase2 Curve Fillets

The confirmed native-fillet flow is now integrated into the isolated phase2 live scenario, still outside production hook generation.

Artifacts:

- script: `sample/live_self_wrapping_phase2_sketch.py`;
- sketch2 source model: `sample/live_outputs/self_wrapping_phase2_with_sketch2_v59.m3d`;
- curve-fillet model: `sample/live_outputs/self_wrapping_phase2_with_curve_fillets_v60.m3d`;
- curve-fillet report: `sample/live_outputs/self_wrapping_phase2_with_curve_fillets_v60_report.json`.

Created operations:

- `SELF_WRAPPING_PHASE2_FILLET_SPIRAL_TO_FIRST_CONTOUR`;
- `SELF_WRAPPING_PHASE2_FILLET_FIRST_TO_SECOND_CONTOUR`.

Reopen verification from disk:

- both fillets are valid;
- both fillets have `TrimCurve1=True` and `TrimCurve2=True`;
- both fillets report numeric radius `3.0`;
- both fillets persist operation variable `Радиус` with expression `SFR1`.

This completes the current isolated 3D-curve transition step. The next body-generation step should consume the native `FilletCurve` objects directly and use fillet-aware contour validation instead of expecting source edge count to match contour edge count exactly.

## Integrated Phase2 3D Contour Probe

After v60, the next isolated check created 3D contours from the native `FilletCurve` objects and sketch/spiral source curves.

Artifacts:

- script: `sample/live_self_wrapping_phase2_contour_probe.py`;
- source model: `sample/live_outputs/self_wrapping_phase2_with_curve_fillets_v60.m3d`;
- output model: `sample/live_outputs/self_wrapping_phase2_contour_probe_v61.m3d`;
- report: `sample/live_outputs/self_wrapping_phase2_contour_probe_v61_report.json`.

Probe contours:

- `SELF_WRAPPING_PHASE2_CONTOUR_FILLET1_ONLY`: valid;
- `SELF_WRAPPING_PHASE2_CONTOUR_FILLET2_ONLY`: valid;
- `SELF_WRAPPING_PHASE2_CONTOUR_SPIRAL_FILLET1_FIRST`: valid, source count `3`, KOMPAS edge count `2`;
- `SELF_WRAPPING_PHASE2_CONTOUR_FIRST_FILLET2_SECOND`: valid, source count `3`, KOMPAS edge count `2`;
- `SELF_WRAPPING_PHASE2_CONTOUR_FULL_PROBE`: valid, source count `9`, KOMPAS edge count `7`.

Reopen verification confirmed all created contours are still present and valid. On reopen the same COM surface did not expose `EdgesCount`, returning `null`, so validity and downstream operation acceptance remain the meaningful checks for native-fillet contours.

The full probe contour is the current candidate path for the next body-generation operation.

## Integrated Phase2 Body Probe

The next isolated check used the full v61 contour as an `IEvolution` path.

Artifacts:

- script: `sample/live_self_wrapping_phase2_body_probe.py`;
- source model: `sample/live_outputs/self_wrapping_phase2_contour_probe_v61.m3d`;
- output model: `sample/live_outputs/self_wrapping_phase2_body_probe_v62.m3d`;
- report: `sample/live_outputs/self_wrapping_phase2_body_probe_v62_report.json`.

Probe setup:

- path: `SELF_WRAPPING_PHASE2_CONTOUR_FULL_PROBE`;
- profile: temporary circle sketch `SELF_WRAPPING_PHASE2_BODY_PROFILE`;
- profile radius: numeric smoke value `1.0`;
- operation: `IEvolution` / `o3d_bossEvolution`;
- settings: `SketchShiftType = 2`, `BySurfaceNormal = True`.

Result:

- `SELF_WRAPPING_PHASE2_BODY_PROBE` was created successfully;
- the operation is valid before save;
- after save and reopen, KOMPAS still reports `SELF_WRAPPING_PHASE2_BODY_PROBE` as a valid evolution operation.

This confirms that the native-fillet full 3D contour can drive body creation. The body probe is intentionally still a smoke check: the next production-quality step is to replace the temporary numeric profile radius with the correct self-wrapping wire/profile parameterization.

## Hook Type Integration

The self-wrapping mechanism is now integrated as a dedicated extension-spring hook type rather than a sample-only postprocess.

New hook type:

- `hook_type = "self_wrapping_hooks"`;
- base planning skeleton: existing `v_hooks`;
- replaced mechanics: left V-hook sketch/transition path is replaced by the self-wrapping sketch chain and native `FilletCurves`;
- old `TrimmedCurves` / `ConnectCurves` transition plan is disabled for this hook type.

Runtime path sequence:

- `self_wrapping_left_spiral`;
- `self_wrapping_left_fillet1`;
- `self_wrapping_left_first_edge0`;
- `self_wrapping_left_first_edge1`;
- `self_wrapping_left_first_edge2`;
- `self_wrapping_left_fillet2`;
- `self_wrapping_left_second_line0`;
- `self_wrapping_left_second_arc0`;
- `self_wrapping_left_second_line1`.

Profile anchor correction:

- v64 built a valid body, but the wire profile sketch was anchored at the spiral end;
- v65 fixes the profile anchor to the end of the hook chain:
  `profile_anchor_plane.path_name = "self_wrapping_left_second_line1"`, `vertex = "end"`.

Current live artifact:

- script: `sample/live_self_wrapping_hook_type_integration.py`;
- output model: `sample/live_outputs/self_wrapping_hook_type_integration_v65.m3d`;
- report: `sample/live_outputs/self_wrapping_hook_type_integration_v65_report.json`.

v65 reopen verification:

- `spring_body` evolution is valid;
- both native curve fillets are valid;
- both native curve fillet radius variables persist as `Радиус = SFR1`;
- profile anchor is `self_wrapping_left_second_line1 / end`.

## Hook Type Path Correction

v65 still had two path-composition problems:

- the profile anchor was moved away from the spiral, but the second-sketch path names did not reliably target the final bent tail edge;
- the self-wrapping path mixed sketch edge sets incorrectly, so some sketch-owned rounded/tail portions could be skipped or duplicated.

v66 changes the hook-type path to use the topological sketch contour edge sets exposed by KOMPAS:

- first self-wrapping sketch: `self_wrapping_left_first_edge0`, `self_wrapping_left_first_edge1`, `self_wrapping_left_first_edge2`;
- second self-wrapping sketch: `self_wrapping_left_second_edge0`, `self_wrapping_left_second_edge1`, `self_wrapping_left_second_edge2`;
- profile anchor: `self_wrapping_left_second_edge2 / end`.

Current artifact:

- output model: `sample/live_outputs/self_wrapping_hook_type_integration_v66.m3d`;
- report: `sample/live_outputs/self_wrapping_hook_type_integration_v66_report.json`.

v66 reopen verification:

- `COMPRESSION_SPRING_PATH_CONTOUR` is valid;
- `spring_body` evolution is valid;
- both native curve fillets are valid;
- both native curve fillet radius variables persist as `Радиус = SFR1`;
- profile anchor is `self_wrapping_left_second_edge2 / end`.

Rebuild diagnostic:

- script: `sample/live_self_wrapping_hook_type_reopen_update_probe.py`;
- output model: `sample/live_outputs/self_wrapping_hook_type_reopen_update_v68.m3d`;
- report: `sample/live_outputs/self_wrapping_hook_type_reopen_update_v68_report.json`.

v68 confirms a false-positive API-build state:

- immediately after reopen: `COMPRESSION_SPRING_PATH_CONTOUR.Valid=True`, `spring_body.Valid=True`;
- after `document.RebuildDocument()`: `COMPRESSION_SPRING_PATH_CONTOUR.Valid=False`, `spring_body.Valid=False`;
- both native `FilletCurve` operations remain valid after rebuild.

Conclusion: v66/v68 are not production-ready. The failure is in the final contour/evolution path, not in the native fillet operations themselves. The current contour still uses whole `FilletCurve` operations as path objects, while KOMPAS UI expects selectable result parts. The next required fix is extracting or recreating fillet result sub-curves as actual contour segments before body creation.

## Native Fillet Result Edges

The UI behavior was reproduced through COM. `FilletCurve.Owner` exposes an `IFeature7` container. Calling `Owner.ModelObjects(7)` returns the three result `IEdge` objects shown under the fillet operation in the KOMPAS tree:

- trimmed source curve 1;
- fillet curve;
- trimmed source curve 2.

The self-wrapping hook path now uses these result edges instead of the whole `FilletCurve` operation:

- `self_wrapping_left_fillet1_edge0`;
- `self_wrapping_left_fillet1_edge1`;
- `self_wrapping_left_fillet1_edge2`;
- `self_wrapping_left_fillet2_edge0`;
- `self_wrapping_left_fillet2_edge1`;
- `self_wrapping_left_fillet2_edge2`.

Rebuild verification artifact:

- output model: `sample/live_outputs/self_wrapping_hook_type_reopen_update_v69.m3d`;
- report: `sample/live_outputs/self_wrapping_hook_type_reopen_update_v69_report.json`.

v69 result:

- immediately after reopen: contour and `spring_body` are valid;
- after `document.RebuildDocument()`: contour and `spring_body` remain valid;
- after explicit object updates: contour and `spring_body` remain valid;
- both native fillet operations remain valid and keep `Радиус = SFR1`.

This resolves the false-positive API-build problem for the current left self-wrapping hook path.

## Second-Sketch Tail Completion

v69 still missed one visible continuation segment after the fillet between the first and second self-wrapping sketch contours. The final path now explicitly includes the full second-sketch continuation after the second fillet result edges:

- `self_wrapping_left_second_edge0`: straight segment from the second sketch after the fillet transition;
- `self_wrapping_left_second_edge1`: second-sketch arc;
- `self_wrapping_left_second_edge2`: bent tail end.

Rebuild verification artifact:

- output model: `sample/live_outputs/self_wrapping_hook_type_reopen_update_v70.m3d`;
- report: `sample/live_outputs/self_wrapping_hook_type_reopen_update_v70_report.json`.

v70 result:

- immediately after reopen: contour and `spring_body` are valid;
- after `document.RebuildDocument()`: contour and `spring_body` remain valid;
- after explicit contour/evolution updates: contour and `spring_body` remain valid;
- both native fillet operations remain valid and keep `Радиус = SFR1`;
- profile anchor remains `self_wrapping_left_second_edge2 / end`.

## Correct Second Fillet Target And Final 9-Edge Contour

The second native curve fillet was later found to be attached to the wrong second-sketch edge in some integration attempts. That produced a contour that looked partially correct but did not reach the final bent tail consistently.

Correct second-sketch edge roles:

- `second_edges[2]`: working straight segment used as the second input curve for the fillet between sketch1 and sketch2;
- `second_edges[1]`: second-sketch arc after the fillet transition;
- `second_edges[0]`: final bent tail segment.

The profile anchor is restored to the final contour end:

- `profile_anchor_plane.path_name = "self_wrapping_left_second_edge2"`;
- `profile_anchor_plane.vertex = "end"`.

The current integrated build performs a rebuild/materialization after creating Sketch2 and before creating the native curve fillets, then captures the fillet result edges for the final path.

Current verification artifact:

- output model: `sample/live_outputs/self_wrapping_hook_type_reopen_update_v87.m3d`;
- report: `sample/live_outputs/self_wrapping_hook_type_reopen_update_v87_report.json`.

v87 result:

- `COMPRESSION_SPRING_PATH_CONTOUR` is created before `spring_body`;
- source path count is `9`;
- contour `EdgesCount` at build time is `9`;
- `spring_body` uses the 9-edge contour;
- after reopen, `document.RebuildDocument()`, `part.RebuildModel()`, and explicit object updates, contour and `spring_body` remain valid;
- both native fillets remain valid and keep `Радиус = SFR1`.

## Cleanup: Clearance Radius And Auxiliary Visibility

The self-wrapping radius variable is now derived from wire diameter instead of a fixed numeric default:

- `SWR1 = WD1 + 0.01`;
- initial numeric fallback is `wire_diameter + 0.01`.

This preserves the previous `3.01` value for `WD1 = 3.0`, while tying the self-clearance radius to the actual wire diameter.

Current cleanup verification artifact:

- output model: `sample/live_outputs/self_wrapping_hook_type_reopen_update_v90.m3d`;
- report: `sample/live_outputs/self_wrapping_hook_type_reopen_update_v90_report.json`.

v90 result:

- profile anchor remains `self_wrapping_left_second_edge2 / end`;
- `COMPRESSION_SPRING_PATH_CONTOUR` has source path count `9` and build-time edge count `9`;
- after reopen, `document.RebuildDocument()`, `part.RebuildModel()`, and explicit object updates, contour and `spring_body` remain valid;
- auxiliary visibility cleanup succeeds with no failed objects;
- self-wrapping sketches, axis plane, and native fillet operations are hidden after body creation.

## Right Hook First Sketch Endpoint Positioning

For the right self-wrapping hook, the base plane alone is not enough. The first
sketch must be positioned from the actual moving spiral endpoint, not from the
old end-center origin used by the V-hook sketch.

Current diagnostic artifact:

- output model: `sample/live_outputs/right_first_sketch_endpoint_v8.m3d`;
- report: `sample/live_outputs/right_first_sketch_endpoint_v8_report.json`;
- inspect snapshot: `sample/live_outputs/right_first_sketch_endpoint_v8_inspect.json`.

v8 result:

- endpoint projected sketch coordinates are `[20.0, 13.5]`;
- the right Sketch1 payload is transformed so the original local contour-start
  point `(0, SRAD1)` lands on that endpoint projection;
- X is mirrored so the hook builds outward from the opposite spring end;
- the arc direction is inverted after mirroring (`direction=false`);
- an explicit sketch point `endpoint_projection_anchor` is created at the endpoint
  projection coordinates;
- `spring_radius_axis` endpoint index `1` and `work_diagonal` endpoint index `0`
  are merged to that anchor point;
- the sketch remains valid after rebuild.

Open caveat: direct API projection of the `IPoint3D` endpoint through
`AddProjectionOf(IPoint3D)` still returns no sketch object in the tested path.
The current sketch uses an explicit anchor point at the computed projection
coordinates. Before final production integration, either confirm this is acceptable
in live KOMPAS behavior or find the API surface that creates a true associative
projected point object.

## Right Hook Ordered Integration

The right self-wrapping hook can now be built before the final path contour and
spring body. This addresses the earlier diagnostic state where
`right_fillet2_sketch_edges_matrix_f2_s2_v1.m3d` contained the useful right hook
sketches and Sketch1-to-Sketch2 fillet, but those operations were created after
the main contour/body and therefore could not be part of the final evolution
path.

Current verification artifacts:

- root bridge model: `sample/live_outputs/self_wrapping_right_order_v1.m3d`;
- root bridge report: `sample/live_outputs/self_wrapping_right_order_v1_report.json`;
- packaged bridge model: `sample/live_outputs/self_wrapping_right_order_asset_v1.m3d`;
- packaged bridge report: `sample/live_outputs/self_wrapping_right_order_asset_v1_report.json`.

v1 result:

- the right first sketch is anchored from the right spiral endpoint projection;
- the right second sketch is created from the projected first sketch through a
  perpendicular plane;
- `SELF_WRAPPING_RIGHT_FILLET_SPIRAL_TO_FIRST_CONTOUR` is created from the
  trimmed body-side source produced by the left hook stage to right Sketch1;
- `SELF_WRAPPING_RIGHT_FILLET_FIRST_TO_SECOND_CONTOUR` uses the confirmed
  Sketch1/Sketch2 `F2_S2` pairing from the matrix probe;
- both right fillet contours are created before the final path contour/profile/body;
- the final resolved path sequence contains `17` source path parts, including the
  right fillet and second-sketch edges;
- after reopen/readback, the right sketches, right fillets, final contour, and
  `spring_body` are present and valid.

Open caveat: build-time contour readback still reports `edges_count = 9` while
`source_path_count` and `expected_edges_count` are `17`. Treat this as a
KOMPAS materialization/readback detail until a stricter contour-edge inspection
confirms the effective edge mapping.

v2 update:

- packaged bridge model: `sample/live_outputs/self_wrapping_right_order_asset_v2.m3d`;
- packaged bridge report: `sample/live_outputs/self_wrapping_right_order_asset_v2_report.json`;
- `SELF_WRAPPING_RIGHT_FILLET_SPIRAL_TO_FIRST_CONTOUR` now uses the diagonal
  right Sketch1 edge (`edge_0`) rather than the upper shelf (`edge_2`);
- this diagonal fillet requires explicit cut points slightly inside the shared
  body/diagonal endpoint; without cut points KOMPAS rejects the fillet, and with
  the raw sketch segment object KOMPAS updates the operation but does not expose
  stable result edges;
- the final path sequence no longer includes `self_wrapping_left_fillet1_edge1`;
  the body-side source is replaced by the right transition fillet result edge,
  so the main curve section is trimmed by both hook transition fillets;
- `build_spring_path_contour` now receives `16` source path parts and reports
  `expected_edges_count = 16`; KOMPAS materializes this as `edges_count = 8`;
- reopen/rebuild readback keeps the final path contour and `spring_body` valid.

Open caveat: after the final contour/body is built from captured result edges,
the auxiliary operation `SELF_WRAPPING_RIGHT_FILLET_SPIRAL_TO_FIRST_CONTOUR`
can read back as `valid = false`, even though its pre-rebuild result edges are
usable and the final contour/body remain valid. A standalone copy with the same
diagonal cut-point fillet and the `F2_S2` fillet, but without consuming that
fillet in the final spring path, reads back both fillets as valid. Treat this as
the next cleanup target for fully parametric right-hook stability.

v3 update:

- packaged bridge model: `sample/live_outputs/self_wrapping_right_order_asset_v3.m3d`;
- packaged bridge report: `sample/live_outputs/self_wrapping_right_order_asset_v3_report.json`;
- the right transition fillet still uses the diagonal `edge_0`, but its
  `Curve1CutPoint` is now placed exactly on the shared endpoint of the trimmed
  body curve and the diagonal; `Curve2CutPoint` remains slightly inside the
  diagonal;
- the previous `valid = false` caveat for
  `SELF_WRAPPING_RIGHT_FILLET_SPIRAL_TO_FIRST_CONTOUR` is resolved in v3;
- reopen/readback shows all four hook fillets, the final path contour, and
  `spring_body` as valid;
- `build_spring_path_contour` still receives `16` source path parts and now
  materializes as `edges_count = 11`.

v4 update:

- packaged bridge model: `sample/live_outputs/self_wrapping_right_order_asset_v4.m3d`;
- packaged bridge report: `sample/live_outputs/self_wrapping_right_order_asset_v4_report.json`;
- the final right-hook path now includes the missing first-sketch inner segment
  `self_wrapping_right_first_edge1` between
  `self_wrapping_right_fillet1_edge2` and `self_wrapping_right_fillet2_edge1`;
- this mirrors the already-working left-hook order, where the first sketch inner
  segment bridges the first transition fillet result to the Sketch1/Sketch2
  fillet result;
- `build_spring_path_contour` now receives `17` source path parts, expects `17`,
  and materializes as `edges_count = 17`;
- reopen/readback shows all four hook fillets, the final path contour, and
  `spring_body` as valid.

v6 coordinate-system update:

- packaged bridge model: `sample/live_outputs/self_wrapping_right_order_asset_v6b_cs_post_turns_5_0.m3d`;
- packaged bridge report: `sample/live_outputs/self_wrapping_right_order_asset_v6b_cs_post_turns_5_0_report.json`;
- do not set `Sketch.CoordinateSystem` to the plane before drawing the first
  right hook sketch: its payload coordinates are authored in the previous
  construction coordinate frame, and early coordinate-system assignment changes
  those local coordinates;
- instead, the three right hook sketches are switched to their plane coordinate
  systems after the final path contour and `spring_body` have been built;
- the post-body coordinate-system step covers
  `SELF_WRAPPING_RIGHT_FIRST_SKETCH`,
  `SELF_WRAPPING_RIGHT_FIRST_SKETCH_PROJECTED`, and
  `SELF_WRAPPING_RIGHT_SECOND_SKETCH_PATH`;
- the right hook base plane is resolved by `_RIGHT_HOOK_PLANE` suffix because
  the live object may use the scenario name rather than the generic
  `COMPRESSION_SPRING` prefix;
- verification for `turns = 5.0` keeps all four hook fillets, the final path
  contour, and `spring_body` valid after reopen/readback, with the final contour
  still materialized as `17` edges.

Open note: direct fresh construction at some fractional turn counts can still
hit a separate projected-sketch edge-selection issue before the post-body
coordinate-system step is reached. That is distinct from the early-coordinate
system assignment problem and should be handled by making the projected-sketch
axis-edge selection geometric instead of relying on a fixed style/index.

v9 placement-order update:

- The post-body coordinate-system workaround from v6 is superseded.
- Root cause: assigning `Sketch.CoordinateSystem` after `Sketch.Plane` makes
  KOMPAS preserve the current sketch placement by writing sketch geometry-scale
  values into placement fields such as offset X/Y, and this can shift later
  projections.
- Correct creation order for plane-local sketches is now:
  `Sketch.CoordinateSystem = plane_object`, then `Sketch.Plane = plane_object`,
  then one `Sketch.Update()`.
- This order matches the clean UI placement state: base plane and coordinate
  system are selected, while offset/rotation/axis-direction fields stay empty or
  zero.
- The central bridge helper `_create_sketch_on_plane` now uses this order when a
  coordinate system is assigned from an object plane. String plane calls remain
  conservative and do not implicitly assign a custom coordinate system.
- Verified right-hook artifacts:
  - `sample/live_outputs/self_wrapping_right_order_asset_v9_full_native_fillet_after_placement_fix.m3d`
  - `sample/live_outputs/self_wrapping_right_order_asset_v9_full_native_fillet_turns_5_5.m3d`
  - `sample/live_outputs/self_wrapping_right_order_asset_v9_full_native_fillet_turns_5_25.m3d`
- For `turns = 5.0`, `5.5`, and `5.25`, the final path contour receives
  `source_path_count = 17`, `expected_edges_count = 17`, and materializes as
  `edges_count = 17`; the saved model includes `spring_body`.

Final cleanup verification after removing the temporary dual-trim fallback and
the visible endpoint fallback point:

- local reproducible final clean models (generated by the live probe, not
  committed as binary evidence):
  - `sample/live_outputs/self_wrapping_right_order_asset_v9_final_clean_hidden_point_turns_5_0.m3d`
  - `sample/live_outputs/self_wrapping_right_order_asset_v9_final_clean_hidden_point_turns_5_5.m3d`
  - `sample/live_outputs/self_wrapping_right_order_asset_v9_final_clean_hidden_point_turns_5_25.m3d`
- committed readback summary:
  - `sample/live_outputs/self_wrapping_right_order_asset_v9_final_clean_hidden_point_summary.json`
- for all three turn counts, the final path contour still reports
  `source_path_count = 17`, `expected_edges_count = 17`, and `edges_count = 17`;
- stale investigation names are absent from the summary, local full reports, and
  bridge code:
  `EXTENSION_SPRING_RIGHT_ANCHOR_POINT`, `TRIM_FIRST`, `TRIM_SECOND`,
  `FILLET2_*COPY`, `dual_trim`, and `native_after_placement_fix`;
- live model-tree readback for `5.0`, `5.5`, and `5.25` shows the right-hook
  service sketches, right-hook planes, and both right-hook fillet curves as
  `Hidden=True` and `Valid=True`; `spring_body` remains `Hidden=False` and
  `Valid=True`;
- readback of the saved models shows only the expected `COMPRESSION_*` 3D
  points (`COMPRESSION_SPRING_START`, `COMPRESSION_SPRING_END`,
  `COMPRESSION_SPRING_RIGHT_ANCHOR_POINT`, and
  `COMPRESSION_SPRING_PROFILE_ANCHOR_POINT`), all with `Hidden=True` and
  `Valid=True`.

Visibility cleanup follow-up for the preserved spiral endpoint:

- the right-hook replacement now reads preserved `*_RIGHT_ANCHOR_POINT` objects
  from `model_container.Points3D`, not from the auxiliary container;
- this prevents a duplicate visible fallback point named
  `EXTENSION_SPRING_RIGHT_ANCHOR_POINT`;
- the hidden-point live CAD checks for `5.0`, `5.5`, and `5.25` still report
  the final contour as `source_path_count = 17`,
  `expected_edges_count = 17`, and `edges_count = 17`, with `spring_body`
  present and no stale dual-trim names.
