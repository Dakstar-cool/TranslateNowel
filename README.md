# EPUB LLM Translate

Local personal Korean-to-Russian EPUB translation application.

The app is designed for a local workflow only. It stores pipeline state in SQLite,
uses local model backends, and provides a PySide6 desktop review UI that can run
while the pipeline continues in a separate process.

## Quick Start

```powershell
uv pip install -e .[dev]
epub-translate --help
epub-translate inspect --config config.yaml
epub-translate import-reference --config config.yaml
epub-translate analyze-reference --config config.yaml
epub-translate build-glossary --config config.yaml
epub-translate validate-glossary --config config.yaml
epub-translate draft-translate --config config.yaml --chapters 1-315
epub-translate check-draft --config config.yaml
epub-translate revise --config config.yaml --profile accurate --use-reference --chapters 1-315
epub-translate final-check --config config.yaml
epub-translate build-final --config config.yaml --mode uniform-machine
epub-translate gui --config config.yaml
```

Start from `config.example.yaml`, copy it to `config.yaml`, and point it at your
local EPUB, reference directory, and local model endpoints.

## Data Safety

- No cloud APIs are used by default.
- Reference translations are used for glossary, style, short examples, and
  benchmark validation.
- Reference chapters are not inserted into the final book unless `hybrid` build
  mode is selected.
- The pipeline never overwrites human edits automatically.
- SQLite WAL mode is enabled for concurrent GUI and pipeline access.

## Hardware Profile

The default example configuration targets a local workstation with an NVIDIA GPU
with 12 GB VRAM and 32 GB system RAM. Runtime can be long; the pipeline is built
to resume from persistent SQLite state.

## Validation

```powershell
uv pip install -e .[dev]
python -m compileall src
epub-translate --help
epub-translate inspect --config config.example.yaml --dry-run
epub-translate import-reference --config config.example.yaml --dry-run
epub-translate analyze-reference --config config.example.yaml --dry-run
epub-translate build-glossary --config config.example.yaml --dry-run
epub-translate benchmark-reference --config config.example.yaml --dry-run
epub-translate draft-translate --config config.example.yaml --chapters 1-315 --dry-run
epub-translate check-draft --config config.example.yaml --dry-run
epub-translate revise --config config.example.yaml --profile accurate --use-reference --chapters 1-315 --dry-run
epub-translate repair-issue --config config.example.yaml --issue-id 1 --dry-run
epub-translate final-check --config config.example.yaml --dry-run
epub-translate build-final --config config.example.yaml --mode uniform-machine --dry-run
epub-translate build-final --config config.example.yaml --mode hybrid --dry-run
epub-translate gui --config config.example.yaml --dry-run
pytest -q
```

`validate-glossary` intentionally fails until `workdir/glossary.approved.yaml`
exists and passes validation.

## Windows PowerShell Encoding

If PowerShell shows paths or table borders as mojibake, run commands through the
UTF-8 wrapper:

```powershell
.\scripts\epub-translate.ps1 inspect --config config.yaml
```
