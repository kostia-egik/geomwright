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

## Следующее направление: типы резьб после метрической

Метрическую физическую `external_helical_thread` / `internal_helical_thread` считаем достаточной базой для перехода к другим стандартам. Ближайшая линия развития - не переписывать модуль заново, а выделить семейство профиля и табличный каталог:

- сначала `unified_inch_v60` по ISO 68-2 / ASME B1.1: тот же V-профиль 60 deg, но inch/TPI размеры и свои правила корня UN/UNR/UNJ. Базовый слой уже добавлен и визуально проверен: `external_helical_thread` / `internal_helical_thread` принимают `1/4-20 UNC`, `#10-32 UNF`, explicit `major_diameter_inch + tpi` или уже пересчитанные мм-значения с `thread_profile_family`;
- затем 60 deg pipe-семейство NPT/NPS: цилиндрический `pipe_nps_v60` уже добавлен для `NPS`/`NPSM` с pipe-таблицами, inch/TPI->mm и плоским притуплением дна профиля; конический `pipe_npt_v60` тоже добавлен для `NPT` с taper 1:16, `IConicSpiral3D`, коническим source-carrier и отдельным `thread_profile_sketch` helper со staged-параметризацией и live readback-проверками tapered flat-профиля; для наружного конуса контракт зафиксирован так: сам carrier идёт `start_face` = большой/посадочный торец -> `end_face` = малый/свободный торец, но наружная резьба на неполном span якорится от малого торца и идёт `end_face -> start_face`;
- после этого Whitworth/BSP 55 deg (`G`, `R`, `Rp`) как новый V-профиль с другим углом и округлениями; цилиндрический `pipe_bsp_g_v55` уже добавлен для наружного и внутреннего `G`, а конические `R/Rp` остаются следующим подэтапом;
- дальше trapezoidal/Acme и buttress/специальные профили как отдельные эскизные семейства, а не простая смена коэффициентов.

Для каждого нового типа нужно держать прежний контракт модулей: входные размеры через именованные переменные, полностью определённый профильный эскиз, отсутствие глобальных координат, опора на входной объект/face/LCS и пригодность для цепочек `workflow` в любом направлении.

## Run

```powershell
cd C:\Users\Костя\work\kompas-mcp
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m kompas_mcp
```

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

## Параметрические детали

Параметрический слой уже не ограничивается одним эскизом. Сейчас в MCP есть:

- `stepped_shaft` — ступенчатое тело вращения;
- `external_conical_step` / `internal_conical_step` — внешняя и внутренняя конические ступени;
- `internal_cylindrical_step` — внутренний многоступенчатый bore;
- `face_ring_groove` — кольцевая проточка на торце;
- `bolt_circle_holes` — отверстия по диаметру через базовое отверстие + концентрический массив;
- `external_polygonal_step` / `internal_polygonal_step` — многогранные ступени через выдавливание/вырезание;
- `external_threaded_step` / `internal_threaded_step` — внешняя и внутренняя native-резьба по каталогу КОМПАС;
- `external_helical_thread` / `internal_helical_thread` — физическая винтовая резьба на существующем цилиндре/отверстии через спираль и кинематический вырез;
- `point` — опорные точки (`global`, `offset_from_point`, `center_of_object`);
- `lcs` — локальные системы координат (`global`, `point`, часть `object`);
- `workflow` — цепочка операций в одном документе со ссылками между шагами.

Для `external_helical_thread` и `internal_helical_thread` после построения скрываются служебные точки, LCS профиля, профильный эскиз, ось и спираль. Bridge выставляет `Hidden=True` и сразу коммитит это через `Update()`, чтобы состояние сохранялось в дереве построений после переоткрытия `.m3d`.

Для `external_conical_step` используем явную осевую семантику carrier-а: `start_face` — большой/посадочный торец, `end_face` — малый/свободный торец. Для завязанных на него наружных конических резьб резьбовой участок считается входящим со стороны малого торца, поэтому threaded/helical span по умолчанию идёт `end_face -> start_face`, а гладкий остаток при неполной длине остаётся у большого торца. Дополнительные алиасы: `large_end_face`/`seat_face` и `small_end_face`/`free_end_face`. Обратный span для наружной конической резьбы preview теперь отклоняет.

В этих же helical-thread модулях наружу выводятся публичные переменные `Diameter...`, `Pitch...` и `Length...`. Диаметр исходного цилиндра/отверстия привязывается к `Diameter...`, шаг спирали привязывается к `Pitch...`, а высота спирали привязывается к выражению `Length... + 1.05 * Pitch...` для auto entry-offset. Для параметров операции bridge использует переменные владельца операции (`Owner.Variables`) и коммитит изменения через `Update()`.

Быстрый ручной прогон нескольких проверочных примеров винтовой резьбы:

```powershell
python sample/create_helical_thread_examples.py
```

Скрипт собирает внешний и внутренний demo-кейсы, плюс пару каталожных `M12`, и пишет сводку в `sample/generated/helical_thread_examples.report.json`.

Отдельный live-пример для наружной частичной NPT-резьбы на коническом carrier-е:

```powershell
python sample/create_external_npt_partial_helical_thread_example_2026_05_19.py
```

Скрипт создаёт папку `sample/generated/external_npt_partial_helical_thread_example_2026_05_19` и дополнительно валидирует, что резьба начинается со стороны малого торца (`end_face -> start_face`), а гладкий остаток остаётся у большого торца.

Отдельный live-пример для наружной цилиндрической BSP `G 1/4` с профилем Whitworth 55°:

```powershell
python sample/create_external_bsp_g_helical_thread_example_2026_05_19.py
```

Скрипт создаёт папку `sample/generated/external_bsp_g_helical_thread_example_2026_05_19` и валидирует, что `pipe_bsp_g_v55` включает основной проход со скруглённым корнем и второй `crest_round_pass` со смещением `pitch / 2`.

Отдельный live-пример для внутренней цилиндрической BSP `G 1/4`:

```powershell
python sample/create_internal_bsp_g_helical_thread_example_2026_05_20.py
```

Скрипт создаёт папку `sample/generated/internal_bsp_g_helical_thread_example_2026_05_20` и валидирует, что `pipe_bsp_g_v55` для `internal_helical_thread` использует Whitworth-профиль 55° с round-root из `thread_geometry` и зеркальным вторым crest-pass.

Чистый повторный пакет физических метрических резьб с live-отчётом по скрытию служебной геометрии:

```powershell
python sample/create_metric_helical_thread_hidden_commit_2026_05_18.py
```

Скрипт создаёт отдельную папку `sample/generated/metric_helical_thread_hidden_commit_2026_05_18` и не перезаписывает существующий результат. Дополнительно после генерации можно сверить `reopen_hidden_probe.json`: он открывает сохранённые файлы заново и проверяет, что все служебные объекты имеют `Hidden=True`.

Пакет проверки привязки параметров операций и диаметра источника:

```powershell
python sample/create_metric_helical_thread_parameter_bound_2026_05_18.py
```

Скрипт создаёт `sample/generated/metric_helical_thread_parameter_bound_2026_05_18`; в `manifest.json` фиксируются выражения для переменных источника и для параметров спирали.

Базовый сценарий остаётся `stepped_shaft`. Он уже умеет:

- строить живой параметрический эскиз и операцию вращения;
- выводить наружу пользовательские параметры `D*` и `L*`;
- держать внутренние переменные эскиза отдельно от внешних параметров;
- перестраиваться от изменения значений в таблице функций;
- отдавать interface anchors/selectors для следующих модулей.

Отдельно по новым модулям:

- conical/bore/groove/bolt-circle уже встроены в тот же `workflow`;
- polygonal-ступени доведены до параметрического эскиза с driving-диаметром по внутренней окружности;
- threaded-step использует штатный каталог стандартов КОМПАС (`thread.db`) и живой API резьбовых обозначений;
- текущий scope threaded-step: цилиндрические/конические source-face'ы, косметическая/native-резьба, без моделирования винтового твердого тела;
- helical-thread — отдельное семейство для реальной геометрии резьбы; текущий V1 scope: цилиндрическая 60° V-резьба `metric_v60`, базовая `unified_inch_v60`, цилиндрическая pipe-резьба `pipe_nps_v60`, коническая pipe-резьба `pipe_npt_v60` и цилиндрическая BSP `G` как `pipe_bsp_g_v55`; одна заходность, внешняя/внутренняя, правая/левая, без встроенных фасок и проточек; сложные flat/tapered/Whitworth-профили проходят через `thread_profile_sketch` с именованными точками, staged-порядком ограничений/размеров и `profile_verification` + live geometry readback.
- для `external_helical_thread` и `internal_helical_thread` добавлен optional `crest_round_pass`: после основного профиля можно построить второй спиральный вырез со смещением `pitch / 2`, отдельным crest-profile и отдельным `cut_evolution`, чтобы скруглять вершину резьбы. Эта live-ветка уже используется для цилиндрического `pipe_bsp_g_v55` в обоих направлениях; коническое расширение для `R/Rp` остаётся следующим шагом.
- для polygonal стандартным считается режим `inscribed_circle`, то есть размер задаётся по внутреннему диаметру “под ключ”.

Из известных хвостов:

- не все extrude-модули уже честно выводят наружу `L` через COM; в части мест пока остаётся числовой fallback;
- “удобные” параметры вроде `PCD`, количества и угла массива отверстий ещё не везде вынесены как внешние driving-переменные;
- threaded-step пока строит именно native-резьбу КОМПАС, а не физическую винтовую геометрию профиля;
- helical-thread пока не пытается автоматически восстанавливать полный профиль стандарта со всеми tolerance-классами и служебными элементами; для метрических, unified inch 60°, NPS/NPSM и NPT pipe 60° профилей это управляемый printable-модуль поверх уже подготовленной заготовки.
- если целевой `.m3d` открыт в КОМПАС, перегенерация в тот же файл пока может вести себя нестабильно; это вынесено в отдельную задачу.

Preview для `stepped_shaft`:

```json
{
  "tool": "preview_part_scenario",
  "arguments": {
    "scenario": "stepped_shaft",
    "params": {
      "name": "Вал",
      "designation": "SHAFT-001",
      "material": "Сталь 45",
      "steps": [
        {"length": 20, "diameter": 12},
        {"length": 30, "diameter": 18},
        {"length": 15, "diameter": 10}
      ]
    }
  }
}
```

Live-создание:

```json
{
  "tool": "create_part_from_scenario",
  "arguments": {
    "scenario": "stepped_shaft",
    "output_path": "C:\\Temp\\kompas-mcp\\shaft.m3d",
    "close_after_save": true,
    "params": {
      "name": "Shaft",
      "designation": "SHAFT-001",
      "material": "Steel 45",
      "sketch": {
        "axis_line_style": "axial",
        "profile_line_style": "normal",
        "dimensions": true,
        "constraints": true
      },
      "steps": [
        {"length": 20, "diameter": 12},
        {"length": 30, "diameter": 18},
        {"length": 15, "diameter": 10}
      ]
    }
  }
}
```

Эскиз строится отдельным слоем `sketch`: ось вращения по умолчанию получает
системный стиль `ksCSAxial = 3`, профиль - `ksCSNormal = 1`. Live-запись
применяет управляющие размеры, ограничения и внешние переменные так, чтобы
эскиз оставался полностью параметризованным и перестраиваемым.

Геометрия, стиль оси, свойства детали, сохранение и освобождение файла проверены
живым smoke-test. Свойства `name`, `designation`, `material` применяются после
создания геометрии и сохраняются после повторного открытия файла.

Поверх этого слоя можно строить цепочки. Пример эксцентрикового сценария через
публичный `workflow`:

```json
{
  "tool": "create_part_from_scenario",
  "arguments": {
    "scenario": "workflow",
    "output_path": "C:\\Temp\\kompas-mcp\\eccentric-chain.m3d",
    "close_after_save": true,
    "params": {
      "name": "EccentricChain",
      "operations": [
        {
          "id": "rev01",
          "scenario": "stepped_shaft",
          "params": {
            "name": "Primary shaft",
            "parameter_prefix": "REV01",
            "steps": [
              {"length": 20, "diameter": 16},
              {"length": 25, "diameter": 26},
              {"length": 15, "diameter": 20}
            ]
          }
        },
        {
          "id": "pt_center",
          "scenario": "point",
          "params": {
            "mode": "center_of_object",
            "point_name": "PT_CENTER",
            "reference": {
              "ref": "rev01.end_face"
            }
          }
        },
        {
          "id": "pt_ecc",
          "scenario": "point",
          "params": {
            "mode": "offset_from_point",
            "point_name": "PT_ECC",
            "reference": {
              "ref": "pt_center.point"
            },
            "offset": {"dx": 0, "dy": 8, "dz": 0}
          }
        },
        {
          "id": "lcs_ecc",
          "scenario": "lcs",
          "params": {
            "mode": "point",
            "lcs_name": "LCS_ECC",
            "reference": {
              "output_ref": "pt_ecc.point"
            }
          }
        },
        {
          "id": "rev02",
          "scenario": "stepped_shaft",
          "params": {
            "name": "Secondary shaft",
            "parameter_prefix": "REV02",
            "placement": {
              "base": {
                "mode": "csys_ref",
                "reference": {
                  "output_ref": "lcs_ecc.lcs"
                }
              }
            },
            "steps": [
              {"length": 22, "diameter": 10},
              {"length": 18, "diameter": 14}
            ]
          }
        }
      ]
    }
  }
}
```

Сейчас workflow уже подходит для практичных цепочек на основе `stepped_shaft`,
`point` и `lcs`. Для связей между шагами лучше использовать публичные outputs
вида `rev01.end_face`, `pt_ecc.point`, `lcs_ecc.lcs`. Более общие внешние
feature-references ещё развиваются.

### Workflow Links

Публичный контракт ссылок в `workflow` сейчас такой:

- строковый токен: `op.output`
- объектная форма: `{ "ref": "op.output" }`
- эквивалентная форма: `{ "output_ref": "op.output" }`
- совместимость со старым стилем: `{ "operation": "rev01", "output": "end_face" }`

Практически лучше использовать именно `ref` или `output_ref`, потому что они
лучше читаются в длинных цепочках.

Операции сейчас экспортируют такие базовые outputs:

- `stepped_shaft`: `body`, `sketch`, `axis`, `start_face`, `end_face`
- `point`: `point`
- `lcs`: `lcs`

У `stepped_shaft` также доступны selector-based outputs по ступеням:

- `step_1_start_face`, `step_1_end_face`
- `step_2_start_face`, `step_2_end_face`
- `shoulder_1_face`
- `step_1_outer_face`, `step_2_outer_face`

Поддерживаются и компактные алиасы того же смысла:

- `step1_end_face`
- `shoulder1_face`
- `step2_outer_face`

Плюс есть общие selector-алиасы:

- `end_face` = `far_end_face`
- `start_face` = ближний торец

Типичные ссылки между шагами:

```json
{
  "reference": {
    "ref": "rev01.end_face"
  }
}
```

```json
{
  "reference": {
    "output_ref": "pt_ecc.point"
  }
}
```

```json
{
  "placement": {
    "base": {
      "mode": "csys_ref",
      "reference": {
        "output_ref": "lcs_ecc.lcs"
      }
    }
  }
}
```

Экспорты самого workflow задаются тем же контрактом:

```json
{
  "exports": {
    "primary_body": "rev01.body",
    "primary_end_face": "rev01.end_face",
    "eccentric_point": "pt_ecc.point",
    "eccentric_lcs": "lcs_ecc.lcs"
  }
}
```

Если ссылка или selector указаны неверно, preview и live теперь возвращают
ошибку с самим токеном ссылки и списком доступных outputs/selector'ов.

## Тесты

Быстрые проверки без живой сессии КОМПАС:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
```

## Notes

- По умолчанию используется встроенный Python КОМПАСа:
  `C:\ProgramData\ASCON\KOMPAS-3D\23\Python 3\App\python.exe`
- При необходимости можно переопределить:
  - `KOMPAS_PYTHON`
  - `KOMPAS_BRIDGE_SCRIPT`
  - `KOMPAS_RULES_PATH`
