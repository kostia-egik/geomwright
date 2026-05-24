# kompas-mcp

Практичный MCP для первого этапа работы с КОМПАС-3D:

- чтение состояния сессии
- список открытых документов
- чтение дерева 3D-документа
- поиск и выборка узлов
- анализ проблем в именах
- анализ базовых проблем спецификации
- безопасная пакетная обработка моделей
- параметрические `.m3d`-сценарии через `stepped_shaft`, `point`, `lcs`
- revolve/extrude модули поверх этой базы: conical step, stepped bore, ring groove, polygonal step, bolt-circle holes
- каталожные native-резьбы КОМПАС: `external_threaded_step`, `internal_threaded_step`
- физические винтовые резьбы на уже существующей цилиндрической геометрии: `external_helical_thread`, `internal_helical_thread`
- цепочки операций через публичный `workflow`

Что уже реально работает в этой версии:

- подключение к живому `Kompas.Application.7`
- bridge через встроенный Python КОМПАСа
- безопасное чтение без записи в документ
- анализаторы поверх дерева модели
- отдельные `.spw`-спецификации с preview и export
- batch smoke-check и batch-анализ качества по папке моделей
- live-построение параметрических деталей и опорной геометрии
- object-selectors для торцев, плеч и цилиндрических поверхностей `stepped_shaft`
- рабочие revolve/cut/extrude сценарии поверх `workflow`, `point` и `lcs`
- native thread-модули через каталог `thread.db` и API `ISymbols3DContainer.Threads`
- физические спиральные резьбы через `ICylindricSpiral3D` + `IEvolution`

Что оставлено на следующий этап:

- редактирование свойств
- preview/apply changeset
- checkpoint/restore
- атрибуты и расширенные поля спецификации
- более общие external object-references между feature-модулями
- устойчивое сохранение/перезапись уже открытых `.m3d`
- добивание внешних driving-параметров там, где COM пока даёт только числовой fallback

## Run

```powershell
cd C:\Users\Костя\work\kompas-mcp
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m kompas_mcp
```

Packaged installs include the default rules and bridge script. Development
checkouts still prefer the root `rules/default.json` and
`bridge/kompas_bridge.py` files when they exist. Override paths with
`KOMPAS_BRIDGE_SCRIPT` or an explicit rules path when testing a custom bridge or
rule set.

## MCP tool map

The server exposes many tools, so start with `get_mcp_tool_catalog` when
you need orientation. It returns categories such as `low_level_runtime`,
`session_lifecycle`, `composition_specification`, `relink`,
`document_tree_items`, and `quality_changesets`.

Low-level runtime/readback tools are documented in
[`docs/low-level-runtime.md`](docs/low-level-runtime.md).
Snapshot-verified write contracts are documented in
[`docs/write_operations.md`](docs/write_operations.md).
For the first live read-only audit, run
`sample\audit_live_kompas_low_level_2026_05_20.py`.

Parametric workflow and thread details are documented in
[`docs/parametric-workflows.md`](docs/parametric-workflows.md).

## Отдельные .spw-спецификации

Поток `.spw` создаёт отдельный документ спецификации КОМПАС из текущего дерева
сборки/модели. Это отдельный сценарий, не встроенное описание спецификации
внутри `.a3d`.

По умолчанию записываются только стабильные базовые колонки:

```json
{
  "tool": "create_spw_from_model",
  "arguments": {
    "output_path": "C:\\Temp\\kompas-mcp\\assembly.spw"
  }
}
```

Базовый набор колонок:

- `position`
- `designation`
- `title`
- `quantity`
- `comment`

Инженерные данные доступны в строках preview/отчёта, но не пишутся в стандартную
форму `.spw` без явного запроса. Готовый пресет можно использовать, если в
целевой форме есть подходящие колонки примечаний/пользовательские ячейки:

```json
{
  "tool": "create_spw_from_model",
  "arguments": {
    "output_path": "C:\\Temp\\kompas-mcp\\assembly-engineering.spw",
    "column_preset": "engineering_comment_columns"
  }
}
```

Для нестандартной формы передайте явную карту колонок. Инженерные поля требуют
`include_engineering: true` на весь вызов или `allow_engineering: true` на
конкретную колонку:

```json
{
  "tool": "create_spw_from_model",
  "arguments": {
    "output_path": "C:\\Temp\\kompas-mcp\\assembly-custom.spw",
    "columns": [
      "position",
      "designation",
      "title",
      { "field": "quantity", "skip_unit_value": true },
      "comment",
      {
        "field": "mass",
        "column_type": 7,
        "block_number": 2,
        "column_number": 5,
        "allow_engineering": true
      }
    ]
  }
}
```

Перед записью удобно вызвать `preview_spw_generation` с теми же
`columns` / `column_preset` и проверить `spw_columns`, `spw_ignored_columns`,
`spw_column_report` и счётчики engineering-данных.

## Пакетная проверка моделей

Первый безопасный слой пакетной обработки не меняет исходные модели. Он нужен,
чтобы быстро понять, какие файлы лежат в папке и стабильно ли КОМПАС может
открывать/закрывать их через MCP.

Сканирование папки без запуска КОМПАС:

```json
{
  "tool": "scan_model_files",
  "arguments": {
    "root": "C:\\Users\\Костя\\work\\kompas-test\\r2-pump-pilot\\renamed",
    "recursive": false
  }
}
```

По умолчанию выбираются только `.a3d` и `.m3d`, а временные `~$...` lock-файлы
пропускаются. В отчёте есть `by_extension` и `skipped_by_reason`.

Пакетный lifecycle smoke-check по папке:

```json
{
  "tool": "batch_smoke_check_session",
  "arguments": {
    "root": "C:\\Users\\Костя\\work\\kompas-test\\r2-pump-pilot\\renamed",
    "recursive": false,
    "limit": 2,
    "output_dir": "C:\\Temp\\kompas-mcp"
  }
}
```

Команда для каждого файла делает open -> save-as smoke copy -> close ->
open read-only -> close. Ошибка одного файла не останавливает пакет, если не
передать `continue_on_error: false`.

Пакетный анализ качества без записи в модели:

```json
{
  "tool": "batch_analyze_model_quality",
  "arguments": {
    "root": "C:\\Users\\Костя\\work\\kompas-test\\r2-pump-pilot\\renamed",
    "recursive": false,
    "limit": 5,
    "analyses": ["naming", "spec"]
  }
}
```

Команда открывает каждый файл read-only, читает дерево, запускает проверки
именования и базовых данных спецификации, затем закрывает документ в любом
случае. В результате есть общий `summary`, список `results` по файлам и
детальные замечания внутри `analyses`.

Чтобы сохранить результат в файлы, передайте `report_dir`. По умолчанию будут
созданы полный JSON и короткий Markdown-отчёт:

```json
{
  "tool": "batch_analyze_model_quality",
  "arguments": {
    "root": "C:\\Users\\Костя\\work\\kompas-test\\r2-pump-pilot\\renamed",
    "recursive": false,
    "limit": 5,
    "report_dir": "C:\\Temp\\kompas-mcp\\reports",
    "report_name": "r2-quality-check",
    "report_formats": ["json", "md"]
  }
}
```

`report_formats` можно ограничить, например `["md"]`, если нужен только
человеческий отчёт.

## Parametric details

The main entry points are `preview_part_scenario` and
`create_part_from_scenario`. Current scenarios cover `stepped_shaft`,
conical/bore/groove/bolt-circle modules, polygonal steps, native KOMPAS
thread modules, physical helical-thread operations, and `workflow` chains.

Detailed live examples, thread roadmap, workflow links, and known modelling
gaps are in [`docs/parametric-workflows.md`](docs/parametric-workflows.md).

## Тесты

Быстрые проверки без живой сессии КОМПАС после `pip install -e .`:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
```

Из сырого checkout без editable install:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests
```

## Notes

- По умолчанию используется встроенный Python КОМПАСа:
  `C:\ProgramData\ASCON\KOMPAS-3D\23\Python 3\App\python.exe`
- При необходимости можно переопределить:
  - `KOMPAS_PYTHON`
  - `KOMPAS_BRIDGE_SCRIPT`
  - `KOMPAS_RULES_PATH`
