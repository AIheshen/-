# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
from threading import Thread
from PIL import ImageGrab
import pytesseract
import cv2
import numpy as np
import json
import os
import time
import websocket
import hmac
import hashlib
import base64
from datetime import datetime, timezone
import ssl

# ==================== 配置 ====================
TESSDATA_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
REGION_FILE = os.path.join(os.path.dirname(__file__), 'subtask_region.json')
pytesseract.pytesseract.tesseract_cmd = TESSDATA_PATH
# ==============================================

class RegionSelector:
    def __init__(self, callback, title="拖拽框选区域"):
        self.callback = callback
        self.start_x = self.start_y = 0
        self.rect = None

        self.root = tk.Toplevel()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.3)
        self.root.configure(bg='gray')
        self.root.attributes('-topmost', True)

        self.canvas = tk.Canvas(self.root, highlightthickness=0, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.create_text(20, 20, anchor='nw', text=title, fill="white", font=('Segoe UI', 14, 'bold'), tags="hint")

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Escape>", lambda e: self.root.destroy())

    def on_press(self, event):
        self.start_x, self.start_y = event.x_root, event.y_root
        if self.rect: self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(0, 0, 0, 0, outline='#ff6b6b', width=3, dash=(5, 5))

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x_root, event.y_root)

    def on_release(self, event):
        x1 = min(self.start_x, event.x_root)
        y1 = min(self.start_y, event.y_root)
        x2 = max(self.start_x, event.x_root)
        y2 = max(self.start_y, event.y_root)
        self.root.destroy()
        if x2 - x1 > 80 and y2 - y1 > 40:
            self.callback((x1, y1, x2, y2))
        else:
            messagebox.showwarning("区域太小", "请框选更大的区域！")
            self.callback(None)


class ScreenTranslator:
    def __init__(self, root):
        self.root = root
        self.root.title("Subtask翻译器 v9.0")
        self.root.geometry("580x920")
        self.root.resizable(True, True)
        self.root.minsize(500, 460)
        self.root.configure(bg='#f8f4f0')

        # ========== 永久置顶 ==========
        self.root.attributes('-topmost', True)
        self.root.update()
        # ===============================

        self.is_ai_mode = False
        self.current_api = 0
        self.apis = [
            {"name": "API1 (默认)", "type": "ftapi"},
            {"name": "API2 (百度)", "type": "baidu"},
            {"name": "API3 (本地)", "type": "fallback"}
        ]

        self.main_region = None
        self.all_regions = []
        self.manual_frame_collapsed = False

        self.create_widgets()
        self.load_or_select_main_region()

    def create_widgets(self):
        # === 标题栏（无 × 按钮）===
        title_frame = tk.Frame(self.root, bg='#f5d0c9', height=40)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        tk.Label(title_frame, text="Subtask翻译器 v9.0", font=('Segoe UI', 11, 'bold'), fg='#5a5a5a', bg='#f5d0c9')\
            .pack(side=tk.LEFT, padx=16, pady=10)

        # === 主容器 ===
        self.content_frame = tk.Frame(self.root, bg='#f8f4f0')
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        # === 模式切换按钮 ===
        mode_frame = tk.Frame(self.content_frame, bg='#f8f4f0')
        mode_frame.pack(fill=tk.X, pady=(0, 12))
        self.mode_btn = self.create_rounded_button(mode_frame, text="翻译模式", command=self.toggle_mode, bg='#d4bebe')
        self.mode_btn.pack(side=tk.LEFT)

        # === 翻译模式内容 ===
        self.trans_mode = tk.Frame(self.content_frame, bg='#f8f4f0')

        # API选择
        api_f = tk.Frame(self.trans_mode, bg='#f8f4f0')
        api_f.pack(fill=tk.X, pady=(0, 10))
        tk.Label(api_f, text="API:", font=('Segoe UI', 9), fg='#5a5a5a', bg='#f8f4f0').pack(side=tk.LEFT)
        self.api_var = tk.StringVar(value=self.apis[0]["name"])
        api_combo = ttk.Combobox(api_f, textvariable=self.api_var, values=[a["name"] for a in self.apis],
                                 state="readonly", width=14, font=('Segoe UI', 9))
        api_combo.pack(side=tk.LEFT, padx=(6, 0))
        api_combo.bind('<<ComboboxSelected>>', self.on_api_change)
        self.create_rounded_button(api_f, text="测试API", command=self.test_api, bg='#d4bebe').pack(side=tk.LEFT, padx=(6, 0))

        # 结果区
        res_lf = tk.Frame(self.trans_mode, bg='#f8f4f0')
        res_lf.pack(fill=tk.X, pady=(0, 6))
        tk.Label(res_lf, text="翻译结果", font=('Segoe UI', 10, 'bold'), fg='#5a5a5a', bg='#f8f4f0').pack(side=tk.LEFT)
        self.create_rounded_button(res_lf, text="复制全部", command=self.copy_all_results, bg='#d4bebe').pack(side=tk.RIGHT)

        self.translated_text = scrolledtext.ScrolledText(
            self.trans_mode, height=12, font=('Consolas', 9),
            bg='#fefefe', fg='#333', relief='solid', bd=1,
            insertbackground='#d4bebe', selectbackground='#d4bebe'
        )
        self.translated_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 按钮区
        btn_frame = tk.Frame(self.trans_mode, bg='#f8f4f0')
        btn_frame.pack(fill=tk.X)
        btns = [
            ("扫描主框", lambda: self.scan_regions(False), '#d4bebe'),
            ("新增扫描框", self.add_extra_region, '#90d4c1'),
            ("翻译整页", lambda: self.scan_regions(True), '#a8c4d9'),
            ("重新框选", self.reselect_main, '#ffb3b3'),
            ("清空", self.clear_all, '#c9b8b8'),
        ]
        for text, cmd, color in btns:
            btn = self.create_rounded_button(btn_frame, text=text, command=cmd, bg=color)
            btn.pack(side=tk.LEFT if text != "清空" else tk.RIGHT, padx=2, fill=tk.X, expand=True)

        # 手动翻译区
        self.manual_frame = tk.Frame(self.trans_mode, bg='#f0ece8', relief='solid', bd=1)
        self.manual_frame.pack(fill=tk.X, pady=(12, 0))
        m_title = tk.Frame(self.manual_frame, bg='#e5ddd9', height=32)
        m_title.pack(fill=tk.X)
        m_title.pack_propagate(False)
        tk.Label(m_title, text="手动翻译", font=('Segoe UI', 9, 'bold'), fg='#5a5a5a', bg='#e5ddd9').pack(side=tk.LEFT, padx=12, pady=6)
        self.toggle_btn = tk.Button(m_title, text="Down", command=self.toggle_manual, bg='#e5ddd9', fg='#5a5a5a', font=('Segoe UI', 12), relief='flat', bd=0, width=3)
        self.toggle_btn.pack(side=tk.RIGHT, padx=8, pady=6)
        self.manual_content = tk.Frame(self.manual_frame, bg='#f0ece8')
        self.manual_content.pack(fill=tk.X, padx=12, pady=10)

        # 英→中
        f1 = tk.Frame(self.manual_content, bg='#f0ece8')
        f1.pack(fill=tk.X, pady=(0, 6))
        tk.Label(f1, text="英→中", font=('Segoe UI', 9, 'bold'), fg='#666', bg='#f0ece8').pack(anchor='w')
        e1 = tk.Frame(f1, bg='#f0ece8')
        e1.pack(fill=tk.X)
        self.en_input = tk.Entry(e1, font=('Segoe UI', 9), relief='solid', bd=1, bg='#fefefe')
        self.en_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.en_input.bind("<Return>", lambda e: self.manual_translate_en_to_zh())
        self.create_rounded_button(e1, text="翻译", command=self.manual_translate_en_to_zh, bg='#d4bebe').pack(side=tk.RIGHT)

        # 中→英
        f2 = tk.Frame(self.manual_content, bg='#f0ece8')
        f2.pack(fill=tk.X, pady=(0, 6))
        tk.Label(f2, text="中→英", font=('Segoe UI', 9, 'bold'), fg='#666', bg='#f0ece8').pack(anchor='w')
        e2 = tk.Frame(f2, bg='#f0ece8')
        e2.pack(fill=tk.X)
        self.zh_input = tk.Entry(e2, font=('Segoe UI', 9), relief='solid', bd=1, bg='#fefefe')
        self.zh_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.zh_input.bind("<Return>", lambda e: self.manual_translate_zh_to_en())
        self.create_rounded_button(e2, text="翻译", command=self.manual_translate_zh_to_en, bg='#d4bebe').pack(side=tk.RIGHT)

        # 结果
        res_f = tk.Frame(self.manual_content, bg='#f0ece8')
        res_f.pack(fill=tk.X)
        self.manual_result = tk.Label(res_f, text="", fg='#8a7f7f', font=('Segoe UI', 9), bg='#f0ece8', anchor='w')
        self.manual_result.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.create_rounded_button(res_f, text="复制", command=self.copy_manual_result, bg='#d4bebe').pack(side=tk.RIGHT)

        # === AI模式内容 ===
        self.ai_mode = tk.Frame(self.content_frame, bg='#f8f4f0')
        ai_title = tk.Label(self.ai_mode, text="AI对话模式", font=('Segoe UI', 11, 'bold'), fg='#5a5a5a', bg='#f8f4f0')
        ai_title.pack(anchor='w', pady=(0, 10))

        chat_container = tk.Frame(self.ai_mode, bg='#fefefe', relief='solid', bd=1)
        chat_container.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.ai_chat = scrolledtext.ScrolledText(
            chat_container, font=('Segoe UI', 10), bg='#fefefe', fg='#333',
            relief='flat', bd=0, wrap=tk.WORD, state=tk.DISABLED, padx=12, pady=12
        )
        self.ai_chat.pack(fill=tk.BOTH, expand=True)
        self.ai_chat.tag_config("user", foreground="#d32f2f", font=('Segoe UI', 10, 'bold'))
        self.ai_chat.tag_config("ai", foreground="#388e3c", font=('Segoe UI', 10, 'bold'))

        # 输入 + 发送按钮
        input_frame = tk.Frame(self.ai_mode, bg='#f8f4f0')
        input_frame.pack(fill=tk.X, pady=(0, 8))

        self.ai_input = tk.Text(input_frame, height=3, font=('Segoe UI', 10), bg='#fefefe', fg='#333',
                               relief='solid', bd=1, insertbackground='#d4bebe')
        self.ai_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.ai_input.bind("<Control-Return>", lambda e: self.send_ai_message())

        self.send_btn = self.create_rounded_button(input_frame, text="发送", command=self.send_ai_message, bg='#d4bebe')
        self.send_btn.pack(side=tk.RIGHT, ipadx=20, padx=(0, 10))

        self.append_ai_message("AI", "你好！我是讯飞星火大模型，有什么可以帮你？")

        # === 状态栏 ===
        self.status = tk.Label(self.content_frame, text="就绪", fg='#8a9b7f', font=('Segoe UI', 8), bg='#f8f4f0', anchor='w')
        self.status.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        self.show_trans_mode()

    def create_rounded_button(self, parent, text, command, bg):
        btn = tk.Button(parent, text=text, command=command,
                        bg=bg, fg='#5a5a5a', font=('Segoe UI', 9, 'bold'),
                        relief='flat', bd=0, highlightthickness=0,
                        activebackground=self.darken(bg), activeforeground='#5a5a5a',
                        padx=18, pady=10)
        btn.bind("<Enter>", lambda e: btn.config(bg=self.darken(bg)))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    def darken(self, hex_color):
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        return f"#{max(0, r-20):02x}{max(0, g-20):02x}{max(0, b-20):02x}"

    def toggle_mode(self):
        self.is_ai_mode = not self.is_ai_mode
        if self.is_ai_mode:
            self.show_ai_mode()
            self.mode_btn.config(text="翻译模式")
        else:
            self.show_trans_mode()
            self.mode_btn.config(text="AI对话")

    def show_trans_mode(self):
        self.ai_mode.pack_forget()
        self.trans_mode.pack(fill=tk.BOTH, expand=True)

    def show_ai_mode(self):
        self.trans_mode.pack_forget()
        self.ai_mode.pack(fill=tk.BOTH, expand=True)

    def append_ai_message(self, sender, text):
        self.ai_chat.config(state=tk.NORMAL)
        self.ai_chat.insert(tk.END, f"{sender}: ", sender.lower())
        self.ai_chat.insert(tk.END, f"{text}\n\n")
        self.ai_chat.see(tk.END)
        self.ai_chat.config(state=tk.DISABLED)

    def send_ai_message(self):
        text = self.ai_input.get(1.0, tk.END).strip()
        if not text: return
        self.append_ai_message("我", text)
        self.ai_input.delete(1.0, tk.END)
        self.send_btn.config(state='disabled', text="发送中...")
        Thread(target=self.call_xinghuo_api, args=(text,), daemon=True).start()

    def call_xinghuo_api(self, question):
        APP_ID = "f0b9fba6"
        API_KEY = "b14a01cd9e716535a860497ff606a459"
        API_SECRET = "YWQ5YWExMjUwZDBiYjBhOWI4YjFlYzRh"
        ASSISTANT_ID = "ed648gp3sn8u_v1"
        HOST = "spark-openapi.cn-huabei-1.xf-yun.com"
        PATH = f"/v1/assistants/{ASSISTANT_ID}"
        URL = f"wss://{HOST}{PATH}"

        def generate_auth_url():
            date = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
            request_line = f"GET {PATH} HTTP/1.1"
            signature_origin = f"host: {HOST}\ndate: {date}\n{request_line}"
            signature_sha = hmac.new(API_SECRET.encode('utf-8'), signature_origin.encode('utf-8'), hashlib.sha256).digest()
            signature_sha_b64 = base64.b64encode(signature_sha).decode('utf-8')
            authorization_origin = f'api_key="{API_KEY}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_b64}"'
            authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode('utf-8')
            return f"{URL}?authorization={authorization}&date={date}&host={HOST}"

        def on_message(ws, message):
            try:
                data = json.loads(message)
                code = data.get("header", {}).get("code", -1)
                if code != 0:
                    self.append_ai_message("AI", f"错误: {data['header'].get('message', '未知错误')} (code: {code})")
                    return
                text_list = data.get("payload", {}).get("choices", {}).get("text", [])
                for item in text_list:
                    if item.get("role") == "assistant":
                        content = item.get("content", "")
                        if content:
                            self.append_ai_message("AI", content)
            except Exception as e:
                self.append_ai_message("AI", f"解析错误: {e}")
            finally:
                self.root.after(0, lambda: self.send_btn.config(state='normal', text="发送"))

        def on_error(ws, error):
            self.append_ai_message("AI", f"连接错误: {error}")
            self.root.after(0, lambda: self.send_btn.config(state='normal', text="发送"))

        def on_close(ws, *args):
            self.root.after(0, lambda: self.send_btn.config(state='normal', text="发送"))

        def on_open(ws):
            payload = {
                "header": {"app_id": APP_ID},
                "parameter": {"chat": {"domain": "general", "temperature": 0.5, "max_tokens": 2048}},
                "payload": {"message": {"text": [{"role": "user", "content": question}]}}
            }
            ws.send(json.dumps(payload))

        try:
            ws_url = generate_auth_url()
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=30)
        except Exception as e:
            self.append_ai_message("AI", f"连接异常: {e}")
            self.root.after(0, lambda: self.send_btn.config(state='normal', text="发送"))

    def update_status(self, text):
        self.status.config(text=text)
        self.root.update_idletasks()

    def load_or_select_main_region(self):
        if os.path.exists(REGION_FILE):
            try:
                with open(REGION_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                r = (data['left'], data['top'], data['right'], data['bottom'])
                if all(isinstance(x, int) for x in r) and r[0] < r[2] and r[1] < r[3]:
                    self.main_region = r
                    self.all_regions = [r]
                    self.update_status("已加载主区域")
                    return
            except: pass
        self.reselect_main()

    def reselect_main(self):
        self.update_status("请框选主区域...")
        messagebox.showinfo("主区域", "3秒后拖拽框选【主识别区域】")
        time.sleep(3)
        def on_select(region):
            if region:
                self.main_region = region
                self.all_regions = [region]
                with open(REGION_FILE, 'w', encoding='utf-8') as f:
                    json.dump({'left': region[0], 'top': region[1], 'right': region[2], 'bottom': region[3]}, f, indent=2)
                self.update_status("主区域已保存")
        selector = RegionSelector(on_select, "拖拽框选【主区域】")
        self.root.wait_window(selector.root)

    def add_extra_region(self):
        self.update_status("请框选新增区域...")
        def on_select(region):
            if region and region not in self.all_regions:
                self.all_regions.append(region)
                self.update_status(f"已添加区域 {len(self.all_regions)}")
        selector = RegionSelector(on_select, "拖拽框选【新增区域】")
        self.root.wait_window(selector.root)

    def ocr_region(self, bbox):
        try:
            img = ImageGrab.grab(bbox=bbox)
            img_np = np.array(img)
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)
            _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            text = pytesseract.image_to_string(thresh, lang='eng')
            if not text.strip():
                text = pytesseract.image_to_string(img_np, lang='eng')
            return text.strip()
        except Exception as e:
            return f"[OCR错误: {e}]"

    def scan_regions(self, include_full=False):
        self.translated_text.delete(1.0, tk.END)
        def run():
            results = []
            for i, bbox in enumerate(self.all_regions):
                title = "[主区域]" if i == 0 else f"[新增区域 {i}]"
                self.update_status(f"识别 {title}...")
                text = self.ocr_region(bbox)
                trans = self.translate_text(text, 'zh') if text else "[未识别]"
                results.append(f"{title}\n{trans}\n")
            if include_full:
                self.update_status("识别整页...")
                text = self.ocr_region(None)
                trans = self.translate_text(text, 'zh') if text else "[未识别]"
                results.append(f"[整页]\n{trans}\n")
            self.translated_text.insert(1.0, "\n".join(results))
            self.translated_text.see(1.0)
            self.update_status(f"完成！共 {len(results)} 项")
        Thread(target=run, daemon=True).start()

    def translate_text(self, text, target='zh'):
        if not text.strip(): return ""
        if self.current_api == 0:
            try:
                r = requests.get("https://ftapi.pythonanywhere.com/translate", params={
                    "sl": "en" if target == 'zh' else "zh-cn",
                    "dl": "zh-cn" if target == 'zh' else "en",
                    "text": text
                }, timeout=10)
                if r.ok: return r.json().get('destination-text', '[失败]')
            except: pass
        return f"[本地]\n{text}"

    def manual_translate_en_to_zh(self):
        text = self.en_input.get().strip()
        if not text: return
        def run():
            self.manual_result.config(text="翻译中...")
            trans = self.translate_text(text, 'zh')
            self.manual_result.config(text=f"→ {trans}")
        Thread(target=run, daemon=True).start()

    def manual_translate_zh_to_en(self):
        text = self.zh_input.get().strip()
        if not text: return
        def run():
            self.manual_result.config(text="翻译中...")
            trans = self.translate_text(text, 'en')
            self.manual_result.config(text=f"→ {trans}")
        Thread(target=run, daemon=True).start()

    def copy_manual_result(self):
        t = self.manual_result.cget("text")
        if "→" in t:
            self.root.clipboard_clear()
            self.root.clipboard_append(t.split("→", 1)[1].strip())
            self.update_status("已复制")

    def copy_all_results(self):
        content = self.translated_text.get(1.0, tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.update_status("已复制全部")

    def clear_all(self):
        self.translated_text.delete(1.0, tk.END)
        self.en_input.delete(0, tk.END)
        self.zh_input.delete(0, tk.END)
        self.manual_result.config(text="")
        self.update_status("已清空")

    def on_api_change(self, event):
        for i, api in enumerate(self.apis):
            if api["name"] == self.api_var.get():
                self.current_api = i
                self.update_status(f"切换到 {api['name']}")
                break

    def test_api(self):
        def run():
            self.update_status("测试中...")
            result = self.translate_text("hello", 'zh')
            self.update_status("测试成功" if "你好" in result else "测试失败")
        Thread(target=run, daemon=True).start()

    def toggle_manual(self):
        if self.manual_frame_collapsed:
            self.manual_content.pack(fill=tk.X, padx=12, pady=10)
            self.toggle_btn.config(text="Up")
            self.manual_frame_collapsed = False
        else:
            self.manual_content.pack_forget()
            self.toggle_btn.config(text="Down")
            self.manual_frame_collapsed = True


if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenTranslator(root)
    root.mainloop()