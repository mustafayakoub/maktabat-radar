@echo off
rem مسحٌ واحدٌ يكتبُ سجلَّ الوصول — هذا ما تستدعيه مهمّةُ ويندوز كلَّ ساعة
setlocal
cd /d "%~dp0.."
set PYTHONPATH=src
set PYTHONIOENCODING=utf-8
if not exist "data\logs" mkdir "data\logs"
for /f "tokens=1-3 delims=/- " %%a in ("%date%") do set D=%%c-%%b-%%a
python -m maktabat.scan --quiet %* >> "data\logs\scan-%D%.log" 2>&1
endlocal
