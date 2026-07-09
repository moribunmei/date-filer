@echo off
chcp 65001 > nul
set PY=C:\Users\morif\AppData\Local\Programs\Python\Python314\python.exe

echo DateFiler をビルドします...
%PY% -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name DateFiler ^
    --clean ^
    main.py

echo.
if exist dist\DateFiler.exe (
    echo ビルド成功: dist\DateFiler.exe
) else (
    echo ビルド失敗
)
pause
