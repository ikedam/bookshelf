@ECHO OFF
SET PATH=C:\cygwin64\bin;%PATH%
FOR /F %%P in ('cygpath %~dp0') DO SET PWD=%%P
bash -login -c "cd %PWD% && python index.py --mobi --comics"
pause
