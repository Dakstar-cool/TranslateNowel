from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from epub_llm_translate.cli import app

from .test_config_db_glossary import write_config


def test_cli_dry_run(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["inspect", "--config", str(config_path), "--dry-run"])
    assert result.exit_code == 0
    assert "dry_run" in result.output


def test_gui_offscreen_smoke(tmp_path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    config_path = write_config(tmp_path)
    from PySide6.QtWidgets import QApplication

    from epub_llm_translate.gui.main_window import MainWindow

    app_obj = QApplication.instance() or QApplication([])
    window = MainWindow(config_path)
    assert window.windowTitle()
    window.close()
    assert app_obj is not None

