@echo off
chcp 65001 >nul
echo ================================
echo   正在打包：翻译工具.exe
echo   图标：D:\MyExe02\favicon.ico
echo ================================

:: 清理旧文件
rd /s /q build dist 2>nul
del /f /q 翻译工具.spec 2>nul

:: 打包命令
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name="翻译工具" ^
    --icon="D:\MyExe02\favicon.ico" ^
    --add-data "C:\Program Files\Tesseract-OCR\tesseract.exe;." ^
    --add-data "C:\Program Files\Tesseract-OCR\tessdata;tessdata" ^
    --hidden-import=pytesseract ^
    --hidden-import=cv2 ^
    --hidden-import=PIL ^
    "翻译工具.py"

echo.
echo ================================
echo   打包完成！
echo   文件位置：dist\翻译工具.exe
echo ================================
pause