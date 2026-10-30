@echo off
chcp 65001 >nul
python "%~dp0lanbook_pdf.py" %*
pause
