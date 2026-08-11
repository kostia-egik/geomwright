# Архитектура kompas-mcp

Этот документ определяет владельцев runtime-логики и границу между рабочим MCP,
CAD-side bridge, параметрическими модулями и исследовательскими прототипами.

## Runtime-топология

```text
MCP client
    │ JSON/MCP
    ▼
src/kompas_mcp/server.py
    │ tool registration
    ▼
KompasAdapter + normalizers/workflows
    │ JSON request/result files
    ▼
BridgeRunner
    │ launches the KOMPAS-bundled Python runtime
    ▼
bridge/kompas_bridge.py
    │ API7/API5 COM
    ▼
KOMPAS-3D document/model
```

MCP host работает на Python, указанном в `pyproject.toml`. Bridge запускается
отдельным Python runtime из установки КОМПАС-3D v23 и поэтому не должен получать
синтаксис или зависимости, недоступные этому runtime.

Канонический исходник bridge находится в `bridge/kompas_bridge.py`. Его packaged
копия — `src/kompas_mcp/assets/bridge/kompas_bridge.py`. Эти файлы обязаны быть
byte-identical.

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

### Layer 4 — законченные семейства деталей

Layer 4 задаёт публичный контракт целого CAD-модуля: параметры, дерево операций,
формулы, readback и канонические варианты.

Текущие семейства:

- ступенчатые/конические и thread-related parametric parts;
- compression, conical, torsion и extension springs;
- disc/Belleville springs;
- diaphragm spring: flat, single-bend и S-bend, circle/oval relief, through-all
  cuts и multi-source circular pattern.

Mechanical transmissions have an approved concept but no production Layer 4
family yet. Their architecture is defined in
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
MCP server и описанных канонической документацией.

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
| diaphragm module | L2–L4 | complete and live-verified |
| mechanical-transmission platform | L2–L4 | V-belt and Poly-V Layers 2/3 exposed and live-verified; complete Layer 4 pulley family pending |
| native module inspection/launch | L1–L3 | research, explicit opt-in for launch |
| universal OperationGraph/Rule Engine/templates | — | not production; quarantined prototype |

## Документационная иерархия

1. `README.md` — установка, runtime status и первый workflow;
2. этот файл — ownership и production boundaries;
3. `CAD_PATTERNS.md` — переносимые CAD-инварианты;
4. `docs/README.md` — индекс тематических контрактов;
5. `docs/archive/` — только исторические freezes, backlogs и evidence.

## Связанные документы

- [Documentation index](docs/README.md)
- [Reusable CAD patterns](CAD_PATTERNS.md)
- [Low-level runtime](docs/low-level-runtime.md)
- [Write operations](docs/write_operations.md)
- [Sketch authoring agent protocol](docs/sketch-authoring-agent-protocol.md)
- [Parametric workflows](docs/parametric-workflows.md)
- [Spring workflows](docs/spring-workflows.md)
- [Diaphragm spring](docs/diaphragm-spring.md)
