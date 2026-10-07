@echo off
rem مسحٌ واحدٌ يكتبُ سجلَّ الوصول — هذا ما تستدعيه مهمّةُ ويندوز الدوريّة.
rem ⚠ اسمُ ملفِّ السجلِّ يُؤخَذُ من بايثون لا من %date%: صيغةُ %date% تتبعُ لغةَ النظام
rem    فتُنتِجُ «scan-07-10-Wed.log» على جهازٍ وإنجليزيّةً على آخرَ ولا تُرتَّبُ زمنيًّا.
setlocal
cd /d "%~dp0.."
set PYTHONPATH=src
set PYTHONIOENCODING=utf-8
if not exist "data\logs" mkdir "data\logs"
for /f %%i in ('python -c "import time;print(time.strftime('%%Y-%%m'))"') do set STAMP=%%i
python -m maktabat.scan --quiet %* >> "data\logs\scan-%STAMP%.log" 2>&1

rem ورفعُ لقطةِ الرادارِ الخاصّةِ — لا يجري إلّا إن كتبتَ المفتاحَ بيدك في secret.key
if exist "secret.key" python -m maktabat.snapshot --push >> "data\logs\scan-%STAMP%.log" 2>&1
endlocal
