# Краткая архитектура

[English](../en/architecture.md) · [Русский индекс](README.md) · [Подробный источник](../../ARCHITECTURE.md)

Geomwright отделяет детерминированную геометрию от операций с состоянием КОМПАС.
Корневой документ архитектуры владеет подробными runtime-решениями; здесь
собраны основные правила расширения без копирования истории реализации.

## Путь вызова

```text
MCP client → geomwright.server → geomwright.kompas.server
           → *_tools.py / KompasAdapter → BridgeRunner
           → настроенный Windows Python + pywin32 → bridge → КОМПАС API7/API5
Studio     → registry / preview → ограниченный adapter workflow → тот же bridge
```

`geomwright` — публичный application namespace. Большинство реализаций КОМПАС
остаётся в `kompas_mcp` для совместимости. Preview в Studio рассчитывается
на host; CAD-задания идут через adapter и подключаются к видимому КОМПАС.

## Владельцы логики

| Слой | Ответственность | Типичный владелец |
| --- | --- | --- |
| L1 | Одна ограниченная операция или readback | Регистрация tools, adapter, runner, COM bridge |
| L2 | Детерминированная геометрия, нормализация и проверки | `sketch_runtime/`, request/calculation модули семейств |
| L3 | Последовательность операций и проверка результата | Workflow orchestration и verified runners |
| L4 | Завершённое поддержанное семейство деталей | Детали, пружины, кулачки, передачи |

Studio — presentation adapter над этими слоями. У него нет второго
геометрического ядра; preview-модули не регистрируются как MCP tools.
План конкретного семейства принадлежит host, переиспользуемые CAD-примитивы — bridge.

## Контракты и состояние

Публичные запросы и ответы используют JSON-совместимые значения. Внутренние typed
specs допустимы; универсальные `EntitySpec` и operation graph не являются
установленным публичным контрактом. Расширяйте существующего владельца логики,
не создавая конкурирующую схему.

Явно задавайте документ, эскиз и feature, выполняйте preflight перед записью.
Используйте **Plan → Execute → Verify → Correct**. Проверка может включать snapshot
delta, readback операции, чтение тела/топологии/формул, save/reopen и визуальный
контроль при необходимости. Сам по себе COM `Update()` этого не подтверждает.
Универсальной транзакции между несколькими MCP-вызовами нет.

Именованный Windows mutex bridge отклоняет параллельные вызовы с `CAD_BUSY`;
он не сериализует целый workflow из нескольких вызовов или ручные правки в КОМПАС.
Селекторы готовой геометрии временные: получите их заново после rebuild/reopen.
Read-only чтение геометрии не перестраивает и не исправляет модель скрытно.

## Runtime и упаковка

В нормальном режиме `BridgeRunner` по умолчанию имеет timeout 300 секунд.
Transport-файлы временные; явный diagnostic-режим сохраняет артефакты и сообщает
их пути. Ошибки содержат последний доступный progress checkpoint. Настройте
современный интерпретатор bridge через `KOMPAS_PYTHON`.

Исходником bridge владеет `bridge/kompas_bridge.py`; packaged-копия в
`src/kompas_mcp/assets/bridge/` должна быть byte-identical. Общие runtime assets
bridge должны входить в package data. Исследовательские native tools требуют
`GEOMWRIGHT_ENABLE_RESEARCH_TOOLS=1`; незавершённые прототипы и живые свидетельства
остаются в ignored-каталоге `experiments/spikes/`.

Перед расширением CAD-workflow прочитайте [CAD-паттерны](../../CAD_PATTERNS.md) (EN),
[low-level контракт](../low-level-runtime.md) (EN) и [руководство разработчика](development.md).
