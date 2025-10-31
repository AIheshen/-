# 置顶区域翻译工具
## 永久置顶，多区域翻译
### tesseract-ocr-w64-setup-5.5.0.20241111 (1).exe
tesseract-ocr必须安装才能正常使用，
用于识别屏幕不影响其他内容
直接将翻译工具.py用终端打包即可点击使用
win+r输cmd回车
打包代码：

- cd D:\MyExe02（文件所在位置）
- pyinstaller --onefile --windowed --add-data "C:\Program Files\Tesseract-OCR\tesseract.exe;." --name "Subtask翻译器 v9.0" "翻译工具.py"）'''
## 得到翻译工具.exe
