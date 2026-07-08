@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"%~dp0..\.venv\Scripts\epub-translate.exe" %*
