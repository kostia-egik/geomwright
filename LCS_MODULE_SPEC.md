# LCS Module Spec v1

Рабочая спецификация для двух связанных строительных блоков:

- `create_point`
- `create_lcs`

Цель: отделить задачу базирования и параметрических смещений от feature-модулей вроде `revolved_body`.

## Зачем два модуля

Одна ЛСК не решает все задачи.

- ЛСК хорошо задаёт базу и ориентацию.
- Смещения и сложная параметрическая привязка удобнее выражаются через отдельную точку.
- Feature-модули должны принимать готовую базу, а не сами решать, как она получена.

Итоговая цепочка должна выглядеть так:

1. При необходимости создаётся опорная точка.
2. По точке или объекту создаётся ЛСК.
3. Feature-модуль строится от этой ЛСК.

## Общие принципы

- Все публичные параметры namespaced через `parameter_prefix`.
- Все выходные сущности получают стабильный `id`.
- Feature-модули не знают, как именно была получена ЛСК.
- Смещение и ориентация не смешиваются с геометрией самого feature.

## Модуль `create_point`

### Роль

Создать устойчивую опорную точку, которую можно:

- параметризовать;
- привязать к объекту;
- использовать как базу для ЛСК;
- переиспользовать в других модулях.

### Публичные режимы v1

1. `global`
- точка задаётся координатами в глобальной СК;
- доступны `x`, `y`, `z`.

2. `geometry`
- точка ставится по объекту;
- объект задаёт базу;
- собственных смещений нет.

3. `offset_from_point`
- есть базовая точка или вершина;
- от неё задаются `dx`, `dy`, `dz`;
- это основной режим для эксцентриков и подобных сценариев.

4. `offset_from_object`
- есть объектная база;
- точка строится от неё с параметрическим смещением;
- режим нужен для сценариев "торец + эксцентрик".

### Входной контракт

```json
{
  "type": "create_point",
  "name": "PT_ECC_01",
  "parameter_prefix": "PT01",
  "mode": "offset_from_object",
  "reference": {
    "feature": "REV01",
    "entity": "end_face"
  },
  "coordinates": {
    "x": 0,
    "y": 0,
    "z": 0
  },
  "offset": {
    "dx": 0,
    "dy": 8,
    "dz": 0
  }
}
```

### Поля

- `name`: читаемое имя точки.
- `parameter_prefix`: namespace параметров.
- `mode`: один из режимов точки.
- `reference`: внешняя база, если режим её требует.
- `coordinates`: используется в `global`.
- `offset`: используется в `offset_from_point` и `offset_from_object`.

### Выходной контракт

```json
{
  "result": {
    "point_id": "PT_ECC_01",
    "name": "PT_ECC_01",
    "parameter_prefix": "PT01",
    "mode": "offset_from_object",
    "reference": {
      "feature": "REV01",
      "entity": "end_face"
    },
    "coordinates": {
      "x": 40,
      "y": 8,
      "z": 0
    }
  }
}
```

### Параметры точки

Минимальный набор v1:

- `PT01_X`
- `PT01_Y`
- `PT01_Z`
- `PT01_DX`
- `PT01_DY`
- `PT01_DZ`

Не все параметры обязательны в каждом режиме, но имена должны быть предсказуемыми.

## Модуль `create_lcs`

### Роль

Создать локальную систему координат, которая используется как база для feature-модулей.

### Публичные режимы v1

1. `global`
- ЛСК строится относительно глобальной СК;
- доступны смещения `x/y/z`;
- доступны повороты `rx/ry/rz`;
- нули означают совпадение с глобальной.

2. `point`
- ЛСК строится по внешней точке;
- доступны только `rx/ry/rz`;
- смещения не задаются в самой ЛСК;
- если нужно смещение, оно должно быть заложено в точке.

3. `object`
- ЛСК строится по объекту;
- смещений и поворотов нет;
- доступны только объект-специфичные опции;
- для плоской грани разрешается `only_outer_contour`.

### Входной контракт

```json
{
  "type": "create_lcs",
  "name": "LCS_ECC_01",
  "parameter_prefix": "LCS01",
  "mode": "point",
  "reference": {
    "point_id": "PT_ECC_01"
  },
  "position": {
    "x": 0,
    "y": 0,
    "z": 0
  },
  "rotation": {
    "rx": 0,
    "ry": 0,
    "rz": 0
  },
  "options": {
    "only_outer_contour": false
  }
}
```

### Правила по режимам

#### `global`

Используются:

- `position`
- `rotation`

Игнорируются:

- `reference`
- `options`

#### `point`

Используются:

- `reference.point_id`
- `rotation`

Игнорируются:

- `position`
- `options`

#### `object`

Используются:

- `reference`
- `options`

Игнорируются:

- `position`
- `rotation`

### Поддерживаемые ссылки v1

Для `point`:

- `point_id`

Для `object`:

- `vertex`
- `edge`
- `axis`
- `planar_face`
- `cylindrical_face`
- `end_face`

`only_outer_contour` разрешён только для `planar_face`.

### Выходной контракт

```json
{
  "result": {
    "lcs_id": "LCS_ECC_01",
    "name": "LCS_ECC_01",
    "parameter_prefix": "LCS01",
    "mode": "point",
    "reference": {
      "point_id": "PT_ECC_01"
    },
    "origin": {
      "x": 40,
      "y": 8,
      "z": 0
    },
    "axes": {
      "x": [1, 0, 0],
      "y": [0, 1, 0],
      "z": [0, 0, 1]
    },
    "placement_ref": "LCS_ECC_01"
  }
}
```

### Параметры ЛСК

Минимальный набор v1:

- `LCS01_X`
- `LCS01_Y`
- `LCS01_Z`
- `LCS01_RX`
- `LCS01_RY`
- `LCS01_RZ`

## Контракт для feature-модулей

Feature-модули не должны принимать сырой набор координат/углов по своей внутренней логике. Они должны принимать ссылку на базу.

### Общий формат `placement`

```json
{
  "placement": {
    "mode": "global | lcs_ref",
    "reference": "LCS_ECC_01"
  }
}
```

### Правила

- `global`: строить от глобальной СК.
- `lcs_ref`: строить от ЛСК, созданной отдельным модулем.
- Внутренний локальный ноль feature-модуля совпадает с нулём ЛСК.

## Пример цепочки для эксцентрика

### 1. Базовый вал

```json
{
  "type": "create_revolved_body",
  "name": "REV01",
  "parameter_prefix": "REV01",
  "placement": {
    "mode": "global"
  },
  "steps": [
    { "length": 40, "diameter": 24 },
    { "length": 20, "diameter": 16 }
  ]
}
```

### 2. Смещённая опорная точка от торца

```json
{
  "type": "create_point",
  "name": "PT_ECC_01",
  "parameter_prefix": "PT01",
  "mode": "offset_from_object",
  "reference": {
    "feature": "REV01",
    "entity": "end_face"
  },
  "offset": {
    "dx": 0,
    "dy": 8,
    "dz": 0
  }
}
```

### 3. ЛСК по этой точке

```json
{
  "type": "create_lcs",
  "name": "LCS_ECC_01",
  "parameter_prefix": "LCS01",
  "mode": "point",
  "reference": {
    "point_id": "PT_ECC_01"
  },
  "rotation": {
    "rx": 0,
    "ry": 0,
    "rz": 0
  }
}
```

### 4. Второе тело вращения от ЛСК

```json
{
  "type": "create_revolved_body",
  "name": "REV02",
  "parameter_prefix": "REV02",
  "placement": {
    "mode": "lcs_ref",
    "reference": "LCS_ECC_01"
  },
  "steps": [
    { "length": 30, "diameter": 12 }
  ]
}
```

## Валидация v1

### `create_point`

- нельзя одновременно использовать `coordinates` и `reference`, если режим этого не требует;
- `offset` запрещён для `global` и `geometry`;
- `reference` обязателен для `geometry`, `offset_from_point`, `offset_from_object`.

### `create_lcs`

- `global` требует только `position/rotation`;
- `point` требует `reference.point_id`;
- `object` требует `reference`;
- `position` недопустим для `point` и `object`;
- `rotation` недопустим для `object`;
- `only_outer_contour` разрешён только для `planar_face`.

### feature-модули

- `placement.mode = lcs_ref` требует существующий `lcs_id`;
- feature не должен принимать собственные offset/rotation, если они уже вынесены в ЛСК.

## Границы v1

Что входит:

- понятный контракт модулей точки и ЛСК;
- namespaced параметры;
- поддержка цепочки `point -> lcs -> feature`;
- предсказуемая валидация.

Что не входит:

- слишком умные автоориентации;
- сложные геометрические правила выбора осей;
- попытка в одном модуле и строить вспомогательную геометрию, и feature, и ЛСК;
- неограниченный список типов ссылок.

## Рекомендуемый порядок реализации

1. `create_point` в режиме `global`.
2. `create_point` в режимах `geometry` и `offset_from_object`.
3. `create_lcs` в режимах `global` и `point`.
4. `create_lcs` в режиме `object`.
5. Поддержка `placement.mode = lcs_ref` в feature-модулях.
6. Возврат стабильных ссылок `feature -> entity` из модулей вроде `revolved_body`.

## Решение по текущему `revolved_body`

Текущий временный `placement` внутри `revolved_body` следует считать переходным слоем совместимости.

Целевое состояние:

- `revolved_body` строится от `global` или `lcs_ref`;
- эксцентрик и подобные смещения не живут внутри `revolved_body`;
- они выражаются через `create_point` + `create_lcs`.
