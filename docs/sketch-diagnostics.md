# Sketch diagnostics workflow

Статус: experimental diagnostic contract for the low-level sketch runtime.

Этот документ описывает исследовательский слой для анализа проблемных эскизов
KOMPAS без ручной проверки в UI.

## Цель

Сделать так, чтобы агент мог сам отвечать на вопросы:

- замкнут ли рабочий контур;
- где именно контур разорван;
- есть ли ветвления или несколько контуров;
- какие объекты эскиза KOMPAS считает неполностью параметризованными.

## Основной инструмент

Используйте `inspect_sketch_full` и сначала смотрите поле
`sketch_diagnostics`.

Ключевые поля:

- `closure_audit.primary_style` - проверка только основного стиля линий
  (`Style == 1`). Это главный аналог UI-проверки замкнутости со стилем.
- `closure_audit.all_geometry` - проверка всех линий/дуг, включая оси и
  вспомогательные построения.
- `constraint_state_summary` - сводка по `IDrawingObject1.ConstraintsState`.
- `recommended_focus` - компактный список первоочередных проблем.

## Как читать closure audit

Для рабочего эскиза операции обычно нужно:

```text
closure_audit.primary_style.closed == true
closure_audit.primary_style.gap_count == 0
closure_audit.primary_style.branch_count == 0
closure_audit.primary_style.self_intersection_count == 0
closure_audit.primary_style.component_count == 1
```

Если `gap_count > 0`, поле `gaps` содержит точки разрыва:

```json
{
  "point": [61.834298690129586, 105.40679787245192],
  "endpoint_count": 1,
  "endpoints": [
    {"reference": 1073743554, "endpoint": "end", "kind": "segment"}
  ]
}
```

Это означает: у конца указанной сущности нет совпадающего endpoint другой
сущности в пределах tolerance.

Если `branch_count > 0`, в точку попали три или более endpoints. Для
автоматизированных операций это обычно нарушение правила `OP-002`: один эскиз,
один рабочий контур, одна операция.

Если `self_intersection_count > 0`, рабочий контур может быть замкнут, но
перекручен. Это частая причина отказа `bossRotated`/`cut` даже при
`gap_count == 0`. Проверка приближённая: дуги дискретизируются в polyline.
Для `ICircleArc.Direction` важно использовать семантику KOMPAS: `false` означает
обход от start к end против часовой стрелки, `true` - по часовой стрелке.

## Как читать constraint state summary

`constraint_state_summary` основан на `IDrawingObject1.ConstraintsState`.
Полезные значения:

- `full` - объект полностью параметризован;
- `ordinary` - обычный непараметризованный объект;
- `over_constrained` - переопределённый объект;
- `informative` - объект с информационными ограничениями;
- `wrong_projection` - объект с потерянной/неверной проекционной связью.

Если эскиз `under_constrained`, начинайте с `closure_audit.primary_style`.
Открытый контур важнее добивания размеров: операция всё равно может не принять
эскиз.

## Profile preflight при генерации

Для хрупких sketch-driven операций включайте
`verify_profile_after_parameterization`. Bridge после применения переменных,
размеров и ограничений запускает read-only проверку
`closure_audit.primary_style` и только потом вызывает `Rotated.Update`.

Это ловит случаи, когда размер или ограничение формально создались, но solver
сдвинул неприклеенные endpoints: размер в отчёте выглядит успешным, а рабочий
контур уже имеет gaps, ветвления или самопересечения.

Перед чтением `ConstraintsState` инспектор обновляет эскиз через `Sketch.Update()`.
Без этого после повторного открытия документа KOMPAS может вернуть устаревшее
состояние solver'а, хотя после обновления sketch уже `fully_defined`.

## SDK findings

Найденные официальные контакты:

- `ISketch.ConstraintsState` - состояние всего эскиза;
- `IDrawingObject1.ConstraintsState` - состояние конкретного объекта;
- `IDrawingObject1.Constraints` - ограничения конкретного объекта;
- `ksIsCurveClosed`, `ICurve2D.IsClosed`, `IContour.Closed` - проверки
  замкнутости отдельных кривых/контуров.

Прямой API для UI-команды “проверка замкнутости”, которая ставит красные точки в
местах разрыва, пока не найден. Поэтому текущий слой не вызывает UI-команды и не
меняет модель: он вычисляет разрывы по endpoint graph.

## Практический пример

На проблемном эскизе `diaphragm_spring_same_direction_sketch_probe_2026_07_14`
диагностика дала:

```text
sketch_state = under_constrained
closure_primary_closed = false
closure_primary_gap_count = 2
closure_primary_self_intersection_count = 0
constraint_state_counts = {"ordinary": 14}
```

Это сразу показывает, что сначала нужно чинить разрыв основного контура, а не
искать недостающий размер наугад.
