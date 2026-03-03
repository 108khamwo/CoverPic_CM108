import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage

app = Flask(__name__)

# ==========================================
# 1. API Keys 
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = 'A2I4k7+oJf6pGXFzvQCjzRr8Bpk2SZWDmBn3m0IXXzYj3q1EEjJAFZbsqaKXnN+n20j6EtKWQbxCoBUEED5D4pgW5BfMfesrSUCYz8IuS/EWc+beF9gGYsYI2RR7LOYdV7eDTrrbi9VcWyr5I7OsdQdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'b7ac02ec7b085a0e1a37841679ee32c4'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ==========================================
# 2. ให้บริการหน้าเว็บ Web App (NEW GEN)
# ==========================================
@app.route("/")
def home():
    # ดึงไฟล์ index.html (โค้ดเว็บทำปกใหม่ของคุณ) ขึ้นมาแสดงผล
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return "<h1>ยังไม่พบไฟล์หน้าเว็บ</h1><p>กรุณาอัปโหลดไฟล์ทำปกของคุณลงใน GitHub และตั้งชื่อไฟล์ว่า <b>index.html</b></p>"

# ==========================================
# 3. ระบบเชื่อมต่อ LINE Bot (Webhook)
# ==========================================
@app.route("/callback", methods=['POST'])
def callback():
    sig = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    # เปลี่ยนให้บอทส่งลิงก์เข้าหน้าเว็บแทน
    web_url = "https://cm108covernews.onrender.com/"
    reply_msg = f"✨ ระบบทำปก CM108 อัปเกรดใหม่แล้ว!\n\nระบบใหม่มีฟีเจอร์จัดเลย์เอาต์, ซูมภาพ, และใส่แบนเนอร์ได้อย่างอิสระ รบกวนคลิกเข้าใช้งานผ่านเว็บไซต์ด้านล่างนี้ได้เลยครับ\n👇👇👇\n{web_url}"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    web_url = "https://cm108covernews.onrender.com/"
    reply_msg = f"ระบบทำปกย้ายไปที่เว็บไซต์แล้วครับ 🖼️\nคลิกที่นี่เพื่ออัปโหลดรูปลงในระบบใหม่ได้เลย:\n{web_url}"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
