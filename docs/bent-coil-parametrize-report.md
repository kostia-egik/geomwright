# Bent coil parametrization report

Отчет фиксирует работы по `extension_spring / bent_coil_left_spike`, начиная с
`tasks/18-bent-coil-parametrize.md`, и текущее рабочее состояние отогнутых
кольцевых зацепов.

## 1. Исходная задача

Task 18 задавал три основных направления:

1. Параметризовать отогнутую спираль: диаметр, шаг, витки, направление
   построения и угловое положение.
2. Разобраться с двумя механизмами углового положения спирали:
   начальный угол спирали против вращения системы координат.
3. Довести auxiliary-эскизы bent coil до определенного состояния через
   ограничения и размеры.

Важные ограничения из задачи были соблюдены в финальном варианте:

- auxiliary-геометрия не удалялась;
- `segment_plan` не переписывался глобально;
- другие `hook_type` не трогались;
- отогнутая спираль создается отдельным deferred-блоком после auxiliary-
  построений.

## 2. Итоговая схема построения

Для `bent_coil_left_spike` сейчас используются три сегмента:

1. `body` - основная спираль пружины.
2. `bent_coil_left` - левая отогнутая спираль.
3. `bent_coil_right` - правая отогнутая спираль.

Preview normalization добавляет:

- `construction_only = false` для финальных bent-coil сегментов;
- `bent_coil_auxiliary_construction = true`;
- `connector_plan = []`;
- `segment_plan = [body, bent_coil_left, bent_coil_right]`;
- `bent_coil_building_direction = false` по умолчанию.

Для отогнутого сегмента заданы:

- диаметр: `D1 - WD1`;
- радиус: `(D1 - WD1) / 2`;
- шаг: `P1`;
- число витков: `BT1`;
- высота: `BH1`, где `BH1 = P1 * BT1`;
- угол плоскости отгиба: `BA1`, по умолчанию `90` градусов;
- начальный угол самой спирали: жесткое значение `90`.

Ключевой вывод: `BA1` больше не является начальным углом спирали. Это
переменная угла плоскости отгиба.

## 3. Auxiliary-геометрия

Auxiliary-блок создает:

1. `body_start_point` - точка конца/начала основной спирали, от которой строится
   зацеп.
2. `body_start_plane` - плоскость, перпендикулярная основной спирали в этой
   точке.
3. `tangent_sketch` - первый эскиз на `body_start_plane`, задающий ось для
   угловой плоскости.
4. `bent_coil_angle_plane` - плоскость под углом, параметризованная через `BA1`.
5. `center_sketch` - эскиз на `bent_coil_angle_plane`, задающий ось смещения
   центра отогнутой спирали.
6. `COMPRESSION_SPRING_BENT_COIL_CENTER_POINT` - точка центра отогнутой
   спирали, смещенная от `body_start_point` на радиус.

## 4. Первый эскиз

Первый эскиз был геометрически правильным, но не был до конца определен.
Важная диагностика: если накладывать constraints после `EndEdit()`, KOMPAS
возвращал `NewConstraint returned None`. Рабочий способ - создавать ограничения
внутри первоначального `BeginEdit()` сразу после создания линии.

Сейчас первый эскиз создается как раньше:

- `Plane = body_start_plane`;
- `CoordinateSystem = body_start_plane`.

Добавлены ограничения:

- `fixed_point` для первой точки линии;
- `vertical` для линии;
- `fixed_length = (D1 - WD1) / 2`.

Live-проверка показала `created_count = 3` для первого эскиза.

## 5. Center sketch

Center sketch создается на `bent_coil_angle_plane` и используется для построения
направления смещения точки центра отогнутой спирали.

Сейчас он имеет:

- проекцию `body_start_point` в эскиз;
- `merge_points` первой точки оси с проекцией;
- `vertical`;
- `fixed_length = (D1 - WD1) / 2`.

Live-проверка показала `created_count = 3` для center sketch.
Если `merge_points` с проекцией центра не создается для одной из сторон,
bridge добавляет fallback `fixed_point` на начало center-axis линии. Поэтому
center-axis получает точку, вертикальность и фиксированную длину даже при
нестабильном projection-merge.

## 6. Точка центра отогнутой спирали

Раньше `COMPRESSION_SPRING_BENT_COIL_CENTER_POINT` смещалась числом, например
`15.0`. Это было заменено на параметрический радиус.

Из-за особенности COM нельзя безопасно записывать строку-формулу в
`IPoint3DParamDisplace.Distance` до `Update()`: это приводило к ошибке типа.
Рабочая схема:

1. Создать displacement point с числовым fallback-значением радиуса.
2. После создания привязать operation variable `Distance` к выражению
   `(D1 - WD1) / 2`.
3. Обновить объект.

Live-проверка показала `center_point_binding_ok = true`.

## 7. Угловая плоскость

Угол плоскости отгиба теперь параметризован через `BA1`.

Как и с точкой смещения, прямое присваивание выражения в поле угла при создании
плоскости оказалось ненадежным. Рабочая схема:

1. Создать `IPlane3DByAngle` числовым fallback-значением угла.
2. После создания привязать operation variable `Angle` к `BA1`.

Live-проверка показала `angle_plane_binding_ok = true`.

## 8. Отогнутая спираль

Отогнутая спираль создается в deferred-блоке после auxiliary-построений.

Позиционирование:

- точка вставки: `COMPRESSION_SPRING_BENT_COIL_CENTER_POINT`;
- `Position.ParameterType = 1` - точка задается association-object;
- `Position.OrientationType = 0` - ориентация задается направлением осей;
- `Position.LocalCSParameters` приводится к `ILocalCSAxesDirectionParam`;
- `LeadAxis = 73` (`OZ`);
- направляющий объект: `bent_coil_angle_plane` через
  `SetDirectingObject(73, ...)`;
- `RotateAxis` в deferred-блоке отогнутой спирали не задается.

Важно: видимые в UI углы нутации, прецессии и вращения не являются мусорными
полями, которые нужно обнулять. KOMPAS показывает абсолютную ориентацию позиции.
Фактическое угловое положение начала спирали складывается из этой ориентации и
внутреннего начального угла спирали.

Параметризация спирали:

- `Diameter -> D1 - WD1`;
- `Step/Pitch -> P1`;
- `Height -> BH1`;
- `BuildingDirection = false`;
- `TurnDirection = not left_hand`;
- начальный угол левой отогнутой спирали задается числом `90`;
- начальный угол правой отогнутой спирали задается числом `270`.

`BA1` намеренно не привязывается к начальному углу спирали.

## 9. Подбор направления и начального угла

Были проведены live-сравнения вариантов `BuildingDirection`.
Итог:

- `BuildingDirection = false` - правильное направление для отогнутой спирали;
- `BuildingDirection` применяется только в deferred-блоке `bent_coil_left`, а не
  в основном цикле построения спиралей.

Для правого зацепа KOMPAS показывает абсолютный угол вращения позиции `90`, и
начальный угол спирали `90` разворачивал начало на `180`. Поэтому правый
внутренний `InitialAngle` компенсирован до `270`: `90 + 270 = 360`.

Это меняет именно внутренний угол спирали, а не `BA1`, `AngleByOwnAxis` или
способ ориентации позиции.

## 10. Диагностические точки

В процессе диагностики создавались точки на отогнутой спирали:

- start;
- opposite_end.

Они помогли проверить направление и начальную фазу, но в рабочей модели не
нужны. Сейчас создание этих диагностических точек удалено, и в live-report нет
`diagnostic_points` для `create_bent_coil_spiral_segment`.

## 11. Проблема углов нутации, прецессии и вращения

В UI KOMPAS в полях позиционирования точки вставки отогнутой спирали появлялись
углы вроде `90`, `10`, `270`.

Контекст:

- эти поля не являются начальным углом спирали;
- они относятся к ориентации локальной системы координат при позиционировании;
- в режиме `ILocalCSAxesDirectionParam` они не читаются как обычные свойства
  `Nutation/Precession/Rotation` через текущий wrapper;
- SDK KOMPAS API7 показывает отдельные интерфейсы: `ILocalCSAxesDirectionParam`,
  `ILocalCSEulerParam` и `ILocalCSOrientByObjectParam`;
- `ILocalCSOrientByObjectParam` уже проверялся как альтернатива, но для
  bent-coil дает неправильное физическое положение несмотря на правильный объект.

Принятое решение:

- не пытаться очищать видимые Euler-поля как ошибку;
- позиционировать через association point и axis-direction по
  `bent_coil_angle_plane`;
- фазу стыковки подбирать через начальный угол самой спирали с учетом
  абсолютной ориентации позиции.

Правая отогнутая спираль не должна исправляться сменой способа ориентации на
`OrientByObject`; компенсация выполняется через внутренний `InitialAngle`.

## 12. Live-модели

Ключевые модели, созданные во время проверки:

- `sample/live_outputs/bent_coil_left_spike_ba1_90_no_orientation_rotation.m3d` -
  проверка начального угла `90`.
- `sample/live_outputs/bent_coil_left_spike_clean_parametric.m3d` - clean
  параметрический вариант после удаления диагностических точек.
- `sample/live_outputs/bent_coil_first_sketch_parametric_point_plane_only.m3d` -
  текущая точечная проверка: первый эскиз параметризован, позиционирование
  отогнутой спирали только по точке и плоскости.

Последняя live-проверка:

- `aux_ok = true`;
- `bent_ok = true`;
- первый sketch: `created_count = 3`;
- center sketch: `created_count = 3`;
- `angle_plane_binding_ok = true`;
- `center_point_binding_ok = true`;
- `positioning.orientation_type = "axis_direction"`;
- `positioning.orientation_type_value = 0`;
- `positioning.parameter_type_value = 1`;
- контурный счетчик сам по себе не является достаточным доказательством
  правильной фазы bent-coil спирали.

## 13. Live CAD readback

Проверка выполняется live-созданием модели KOMPAS, без добавления автотестов.
Ложноположительный вариант, который нельзя считать финальным:

```text
sample/live_outputs/bent_orient_by_object_clean.m3d
```

Он давал полный contour count, но физическое положение было неправильным из-за
неподходящего способа ориентации.

Актуальный контроль должен смотреть не только count, но и суммарный фазовый угол:

```text
position orientation + spiral initial angle
```

После компенсации правого внутреннего начального угла текущая live-модель:

```text
sample/live_outputs/bent_right_initial_270_readback.m3d
```

Readback:

```text
bent_coil_left.positioning.orientation_type = axis_direction
bent_coil_right.positioning.orientation_type = axis_direction
bent_coil_left.positioning.orientation_type_value = 0
bent_coil_right.positioning.orientation_type_value = 0
bent_coil_left.positioning.parameter_type_value = 1
bent_coil_right.positioning.parameter_type_value = 1
bent_coil_left.parameterization.initial_angle.value = 90
bent_coil_right.parameterization.initial_angle.value = 270
source_path_count = 3
expected_edges_count = 3
edges_count = 3
```

## 14. Что важно сохранить при втором зацепе

1. Не смешивать три разных угла:
   - `BA1` - угол плоскости отгиба;
   - `90`/`270` - начальные углы левой/правой отогнутой спирали;
   - поля ориентации позиции - абсолютное угловое положение локальной СК.
2. Не возвращать `RotateAxis` в deferred-позиционирование отогнутой спирали.
3. Не заменять bent-coil positioning на `ILocalCSOrientByObjectParam` без
   отдельной визуальной проверки геометрии; этот путь уже давал неверное
   положение.
4. Параметризацию COM-полей, которые не принимают строки до `Update()`, делать
   через operation-variable binding после создания объекта.
5. Constraints первого sketch создавать внутри первоначального `BeginEdit()`.
6. Не возвращать диагностические точки в рабочую модель.

## 15. Отклонения от исходного Task 18

Некоторые исходные гипотезы задачи были уточнены live-проверками:

- Начальный угол через переменную оказался не нужен в финальной схеме. Левый
  зацеп использует `90`, правый зацеп использует `270`.
- `BA1` используется для угловой плоскости, а не для initial angle.
- Прямое присваивание формул в некоторые COM-поля ненадежно; рабочий путь -
  числовое создание плюс operation-variable binding.
- Прямое чтение Euler-полей через текущий COM-wrapper ограничено, но сами поля
  нельзя считать ошибкой; они отражают абсолютную ориентацию позиции.

## 16. Текущее состояние

Механика `bent_coil_left_spike` сейчас строит оба отогнутых кольцевых зацепа:

- отогнутая спираль параметризована;
- первый и center sketches доопределены точкой, вертикальностью и длиной;
- центр отогнутой спирали параметризован радиусом;
- угол плоскости отгиба параметризован `BA1`;
- начальный угол спирали зафиксирован числом `90` слева и `270` справа;
- диагностические объекты удалены;
- deferred-позиционирование возвращено к axis-direction по angle plane;
- live-readback для дефолтного `bent_coil_left_spike` дает полный контур `3/3/3`;
- mixed-пары с `bent_coil_left_spike` включены в общую extension-hook матрицу
  `64/64`; для `bent_coil_left_spike -> self_wrapping_hooks` стык
  отогнутого кольца с телом остается без скругления, а правый self-wrapping
  fillet использует raw `BODY_PATH` и logical body-end cut point.
