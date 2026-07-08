# TranslateNowel

Локальное приложение для перевода Korean-to-Russian EPUB-романа: CLI pipeline, SQLite state, PySide6 GUI, reference-aware rewrite и отчёты качества.

Проект рассчитан на локальные LLM через LM Studio/OpenAI-compatible API или Ollama. Cloud API по умолчанию не используются. Рабочие данные (`workdir`, EPUB, SQLite, approved glossary, reference files) не должны попадать в git.

## Быстрый Старт

```powershell
uv pip install -e .[dev]
.\scripts\epub-translate.cmd --help
```

Проверь `config.yaml`:

- `project.input_epub`: исходный EPUB
- `project.workdir`: рабочая папка, обычно `workdir`
- `models.draft_translate`: быстрая модель для черновика
- `models.revise`: более сильная модель для rewrite
- `reference.translation_dir`: папка с 60 переведёнными reference-главами
- `pipeline.max_concurrent_requests`: параллельные запросы для черновика
- `revision.batch_blocks`: сколько абзацев отправлять в один rewrite-запрос

Перед реальным запуском LM Studio должен быть поднят на `http://127.0.0.1:1234/v1/chat/completions`, а нужная модель должна быть загружена.

## Базовый Полный Flow

```powershell
.\scripts\epub-translate.cmd inspect --config config.yaml
.\scripts\epub-translate.cmd import-reference --config config.yaml
.\scripts\epub-translate.cmd analyze-reference --config config.yaml --max-reference-chapters 60
.\scripts\epub-translate.cmd build-glossary --config config.yaml
```

После `build-glossary` вручную проверь черновик глоссария и создай/обнови:

```text
workdir/glossary.approved.yaml
```

Затем:

```powershell
.\scripts\epub-translate.cmd validate-glossary --config config.yaml
.\scripts\epub-translate.cmd draft-translate --config config.yaml --chapters 1-315 --concurrency 4
.\scripts\epub-translate.cmd check-draft --config config.yaml --chapters 1-315
.\scripts\epub-translate.cmd revise --config config.yaml --chapters 1-315 --use-reference --batch-blocks 24
.\scripts\epub-translate.cmd final-check --config config.yaml --chapters 1-315
.\scripts\epub-translate.cmd build-final --config config.yaml --mode uniform-machine --override-high-issues
```

## Частые Команды

Черновой прогон быстрой моделью:

```powershell
.\scripts\epub-translate.cmd draft-translate --config config.yaml --chapters 1-315 --concurrency 4
```

Продолжить черновой прогон с места остановки:

```powershell
.\scripts\epub-translate.cmd draft-translate --config config.yaml --chapters 1-315 --concurrency 4
```

Перегенерировать машинный черновик, не трогая ручные правки:

```powershell
.\scripts\epub-translate.cmd draft-translate --config config.yaml --chapters 1-315 --concurrency 4 --overwrite-model-drafts
```

Rewrite сильной моделью с reference-подкреплением:

```powershell
.\scripts\epub-translate.cmd revise --config config.yaml --chapters 1-315 --use-reference --batch-blocks 24 --profile accurate
```

Rewrite сильной моделью без reference:

```powershell
.\scripts\epub-translate.cmd revise --config config.yaml --chapters 1-315 --no-use-reference --batch-blocks 24 --profile accurate
```

Перегенерировать уже существующий машинный rewrite, не трогая `human_final_edit`:

```powershell
.\scripts\epub-translate.cmd revise --config config.yaml --chapters 1-3 --use-reference --batch-blocks 24 --overwrite-revised
```

Проверить качество только выбранных глав:

```powershell
.\scripts\epub-translate.cmd check-draft --config config.yaml --chapters 1-3
.\scripts\epub-translate.cmd final-check --config config.yaml --chapters 1-3
```

Сравнить draft/revised с reference по доступным reference-главам:

```powershell
.\scripts\epub-translate.cmd benchmark-reference --config config.yaml --chapters 1-3
```

Открыть GUI-мониторинг и review:

```powershell
.\scripts\epub-translate.cmd gui --config config.yaml
```

Собрать текущий черновой EPUB:

```powershell
.\scripts\epub-translate.cmd build-draft --config config.yaml
```

Собрать финальный EPUB:

```powershell
.\scripts\epub-translate.cmd build-final --config config.yaml --mode uniform-machine --override-high-issues
```

## Reference-Aware Rewrite

Для первых 60 глав reference используется как подкрепление:

- imported reference chapters лежат в SQLite и `workdir/reference/chapter_XXXX.txt`
- `analyze-reference` создаёт style guide, examples и glossary candidates
- `revise --use-reference` добавляет в prompt same-chapter reference context
- batch rewrite отправляет несколько соседних абзацев за один запрос
- `benchmark-reference` сравнивает агрегированные метрики draft/revised против reference, не включая copyrighted text в отчёт

Если модель имеет `Parallel 1`, не увеличивай concurrency для rewrite. Ускорение достигается через `--batch-blocks`, например:

```powershell
.\scripts\epub-translate.cmd revise --config config.yaml --chapters 4-10 --use-reference --batch-blocks 24
```

Если batch слишком большой и модель начинает возвращать пустой/битый JSON, уменьши размер:

```powershell
.\scripts\epub-translate.cmd revise --config config.yaml --chapters 4-10 --use-reference --batch-blocks 12
```

## Progress И Resume

`draft-translate` пишет progress в `pipeline_jobs`; GUI Dashboard показывает:

- общий прогресс
- translated/failed/skipped/pending
- concurrency
- ETA

CLI тоже показывает progress bar в stderr. Отключить:

```powershell
.\scripts\epub-translate.cmd draft-translate --config config.yaml --chapters 1-315 --no-progress
```

Все этапы пишут состояние в SQLite. После остановки запускай команду заново без overwrite-флагов:

```powershell
.\scripts\epub-translate.cmd draft-translate --config config.yaml --chapters 1-315 --concurrency 4
.\scripts\epub-translate.cmd revise --config config.yaml --chapters 1-315 --use-reference --batch-blocks 24
```

## Выходные Файлы

Основные артефакты:

- `workdir/work.sqlite`: состояние pipeline
- `workdir/book.draft.ru.epub`: черновой EPUB
- `workdir/book.final.ru.epub`: финальный EPUB
- `workdir/draft_quality_report.csv`
- `workdir/draft_quality_report.html`
- `workdir/final_quality_report.csv`
- `workdir/final_quality_report.html`
- `workdir/reference_benchmark_report.csv`
- `workdir/reference_benchmark_report.html`

## Полный Список Команд

### `inspect`

Читает EPUB, извлекает главы/HTML-блоки и создаёт SQLite state.

```powershell
.\scripts\epub-translate.cmd inspect --config config.yaml
```

Dry run:

```powershell
.\scripts\epub-translate.cmd inspect --config config.yaml --dry-run
```

### `import-reference`

Импортирует reference-переводы из `reference.translation_dir`.

```powershell
.\scripts\epub-translate.cmd import-reference --config config.yaml
```

### `analyze-reference`

Анализирует импортированные reference-главы, создаёт style guide, examples и glossary candidates.

```powershell
.\scripts\epub-translate.cmd analyze-reference --config config.yaml --max-reference-chapters 60
```

Без LLM:

```powershell
.\scripts\epub-translate.cmd analyze-reference --config config.yaml --no-use-llm
```

### `build-glossary`

Создаёт draft-артефакты глоссария для ручной проверки.

```powershell
.\scripts\epub-translate.cmd build-glossary --config config.yaml
```

### `validate-glossary`

Проверяет `workdir/glossary.approved.yaml` и сохраняет approved terms в SQLite.

```powershell
.\scripts\epub-translate.cmd validate-glossary --config config.yaml
```

### `benchmark-reference`

Сравнивает агрегированные метрики draft/revised с reference-главами.

```powershell
.\scripts\epub-translate.cmd benchmark-reference --config config.yaml --chapters 1-3
```

### `draft-translate`

Генерирует машинный черновик.

```powershell
.\scripts\epub-translate.cmd draft-translate --config config.yaml --chapters 1-315 --concurrency 4
```

Полезные флаги:

- `--chapters 1-3`
- `--concurrency 4`
- `--overwrite-model-drafts`
- `--progress / --no-progress`
- `--dry-run`

### `check-draft`

Проверяет черновик на пустые блоки, Hangul, glossary misses, suspicious length ratio и paragraph mismatch.

```powershell
.\scripts\epub-translate.cmd check-draft --config config.yaml --chapters 1-3
```

### `revise`

Переписывает черновик сильной моделью. Поддерживает reference-aware batch rewrite.

```powershell
.\scripts\epub-translate.cmd revise --config config.yaml --chapters 1-3 --use-reference --batch-blocks 24 --profile accurate
```

Без reference:

```powershell
.\scripts\epub-translate.cmd revise --config config.yaml --chapters 1-3 --no-use-reference --batch-blocks 24
```

Полезные флаги:

- `--use-reference / --no-use-reference`
- `--batch-blocks 1..32`
- `--overwrite-revised`
- `--profile accurate`
- `--dry-run`

### `final-check`

Проверяет итоговый текст с precedence:

```text
human_final_edit > revised_translation > human_draft_edit > draft_translation
```

```powershell
.\scripts\epub-translate.cmd final-check --config config.yaml --chapters 1-3
```

### `build-draft`

Собирает draft EPUB из текущих `draft_translation`/`human_draft_edit`.

```powershell
.\scripts\epub-translate.cmd build-draft --config config.yaml
```

### `build-final`

Собирает final EPUB.

```powershell
.\scripts\epub-translate.cmd build-final --config config.yaml --mode uniform-machine
```

Если нужно собрать при оставшихся high issues:

```powershell
.\scripts\epub-translate.cmd build-final --config config.yaml --mode uniform-machine --override-high-issues
```

Hybrid mode использует reference-главы как final для reference range:

```powershell
.\scripts\epub-translate.cmd build-final --config config.yaml --mode hybrid --override-high-issues
```

### `gui`

Открывает PySide6 GUI: Dashboard, Chapters, Issue Queue, Glossary, Reference Examples, Edit History, Logs.

```powershell
.\scripts\epub-translate.cmd gui --config config.yaml
```

### `repair-issue`

Пробует исправить конкретный issue через модель revision.

```powershell
.\scripts\epub-translate.cmd repair-issue --config config.yaml --issue-id 123
```

### `run-pipeline`

Запускает общий pipeline: inspect, draft, check, revise, final-check.

```powershell
.\scripts\epub-translate.cmd run-pipeline --config config.yaml
```

Для контролируемого качества лучше запускать этапы вручную, особенно `draft-translate`, `check-draft`, `revise` и `benchmark-reference`.

## Dry Run

Большинство команд поддерживают `--dry-run`.

```powershell
.\scripts\epub-translate.cmd draft-translate --config config.yaml --chapters 1-3 --dry-run
.\scripts\epub-translate.cmd revise --config config.yaml --chapters 1-3 --use-reference --batch-blocks 24 --dry-run
.\scripts\epub-translate.cmd benchmark-reference --config config.yaml --chapters 1-3 --dry-run
```

## Проверки Разработчика

```powershell
.\.venv\Scripts\python.exe -m compileall src
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\epub-translate.cmd --help
```

## Важные Замечания

- SQLite поднимается автоматически, отдельный SQL-сервер не нужен.
- Не запускай два `draft-translate` одновременно на один `workdir/work.sqlite`.
- Для LM Studio model `Parallel 4` можно использовать `draft-translate --concurrency 4`.
- Для сильной модели с `Parallel 1` используй batch rewrite, а не concurrency.
- `--overwrite-model-drafts` и `--overwrite-revised` не трогают ручные human edits.
- Если LM Studio недоступен, pipeline останавливается автоматически и не создаёт тысячи model-error issues.
- Если PowerShell ломает Unicode, используй `.\scripts\epub-translate.cmd`.
