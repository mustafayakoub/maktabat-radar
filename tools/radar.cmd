@echo off
rem رادار المكتبات — تشغيلُ الصفحة المحلّيّة (انقر نقرتين)
setlocal
cd /d "%~dp0.."
set PYTHONPATH=src
set PYTHONIOENCODING=utf-8
python -m maktabat.server %*
endlocal
