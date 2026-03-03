import os
import requests
from io import BytesIO
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage, ImageSendMessage
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

app = Flask(__name__)

# ==========================================
# 1. API Keys
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = 'A2I4k7+oJf6pGXFzvQCjzRr8Bpk2SZWDmBn3m0IXXzYj3q1EEjJAFZbsqaKXnN+n20j6EtKWQbxCoBUEED5D4pgW5BfMfesrSUCYz8IuS/EWc+beF9gGYsYI2RR7LOYdV7eDTrrbi9VcWyr5I7OsdQdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'b7ac02ec7b085a0e1a37841679ee32c4'
IMGBB_API_KEY = '66827500c20f99afb6779ba1730855b8'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ลิงก์กรอบรูป CM108
FRAME_URL = "https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEiOOtphYnEgsG_Q_5Ht_nM8h4hBJkTlJ0HvXwVOlixbfIkYC4y4NTIxcfl58PvyUi9Tj9azFCGGRCK3ysLAyX3yzXVHRmfbtsau733we6uQ3DE6csoMtWBMG2TNS2i-8aOtvIKTpzkCIyh3avLpViH74sW5SnwEZCkkToZeB4Q6VO-cxHafdputo5SmSxE/s0/frame_cm108.png"

user_states = {}

def generate_cover(bg_image_bytes, text_lines):
    base_width, base_height = 1080, 1350
    
    # 1. โหลดรูปพื้นหลัง
    try:
        bg = Image.open(BytesIO(bg_image_bytes)).convert("RGB")
    except Exception as e:
        print(f"Error opening background: {e}")
        raise ValueError("ไม่สามารถอ่านไฟล์รูปภาพที่ส่งมาได้")

    canvas = Image.new('RGB', (base_width, base_height), color='black')
    
    # จัดตำแหน่งรูปพื้นหลัง (Center Crop)
    bg_ratio = bg.width / bg.height
    canvas_ratio = base_width / base_height
    if bg_ratio > canvas_ratio:
        new_w = int(base_height * bg_ratio)
        bg = bg.resize((new_w, base_height), Image.Resampling.LANCZOS)
        left = (new_w - base_width) / 2
        bg = bg.crop((left, 0, left + base_width, base_height))
    else:
        new_h = int(base_width / bg_ratio)
        bg = bg.resize((base_width, new_h), Image.Resampling.LANCZOS)
        top = (new_h - base_height) / 2
        bg = bg.crop((0, top, base_width, top + base_height))
    canvas.paste(bg, (0, 0))
    
    # 2. วาด Gradient สีดำด้านล่าง (ยกให้สูงขึ้นเพื่อรองรับข้อความ)
    gradient = Image.new('RGBA', (base_width, base_height), (0,0,0,0))
    draw_grad = ImageDraw.Draw(gradient)
    grad_h = 900
    for y in range(base_height - grad_h, base_height):
        alpha = int(255 * ((y - (base_height - grad_h)) / grad_h))
        draw_grad.line([(0, y), (base_width, y)], fill=(0, 0, 0, alpha))
    canvas = Image.alpha_composite(canvas.convert('RGBA'), gradient)
    
    # 3. วางกรอบรูป CM108 (ต้องวางก่อนวาดตัวหนังสือ!)
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(FRAME_URL, headers=headers, timeout=15)
        if resp.status_code == 200:
            fr = Image.open(BytesIO(resp.content)).convert("RGBA")
            fr = fr.resize((base_width, base_height), Image.Resampling.LANCZOS)
            canvas = Image.alpha_composite(canvas, fr)
    except Exception as e:
        print(f"Frame Error: {e}")

    # 4. จัดการฟอนต์และวาดข้อความ (วาดหลังสุดเพื่อให้อยู่บนสุด)
    try:
        font_path = "Prompt-Bold.ttf"
        f_large = ImageFont.truetype(font_path, 95)
        f_med = ImageFont.truetype(font_path, 55)
        f_date = ImageFont.truetype(font_path, 34)
    except:
        f_large = ImageFont.load_default()
        f_med = f_large
        f_date = f_large

    draw = ImageDraw.Draw(canvas)
    
    # บรรทัด 1 (ขยับขึ้นมาที่ 600)
    t1 = text_lines[0] if len(text_lines) > 0 else ""
    if t1:
        bbox = draw.textbbox((0, 0), t1, font=f_large)
        w = bbox[2] - bbox[0]
        draw.text(((base_width-w)/2, 650), t1, font=f_large, fill="#4bfafc", stroke_width=5, stroke_fill="black")
    
    # บรรทัด 2 (ขยับขึ้นมาที่ 710)
    t2 = text_lines[1] if len(text_lines) > 1 else ""
    if t2:
        bbox = draw.textbbox((0, 0), t2, font=f_large)
        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        x, y = (base_width-w)/2, 760
        draw.rounded_rectangle([(x-30, y-15), (x+w+30, y+h+35)], radius=16, fill="#0bc8fa")
        draw.text((x, y), t2, font=f_large, fill="#ffffff", stroke_width=5, stroke_fill="black")
        
    # บรรทัด 3 (ขยับขึ้นมาที่ 850)
    t3 = text_lines[2] if len(text_lines) > 2 else ""
    if t3:
        bbox = draw.textbbox((0, 0), t3, font=f_med)
        w = bbox[2]-bbox[0]
        draw.text(((base_width-w)/2, 900), t3, font=f_med, fill="#ff9012", stroke_width=3, stroke_fill="black")

    # วันที่แบบไทย (ขยับขึ้นมาที่ 950)
    thai_m = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    now = datetime.now()
    d_str = f"- {now.day} {thai_m[now.month-1]} {now.year + 543} -"
    bbox = draw.textbbox((0, 0), d_str, font=f_date)
    w = bbox[2]-bbox[0]
    draw.text(((base_width-w)/2, 1000), d_str, font=f_date, fill="white")
    
    out = BytesIO()
    canvas.convert('RGB').save(out, format='JPEG', quality=95)
    return out.getvalue()

def upload_to_imgbb(img_bytes):
    url = f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}"
    r = requests.post(url, files={'image': img_bytes})
    return r.json()['data']['url']

# เพิ่มเส้นทางหน้าแรก เพื่อแก้ปัญหา Render แจ้งเตือนเรื่อง Port
@app.route("/")
def home():
    return "LINE Bot is running smoothly!"

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
    user_states[event.source.user_id] = event.message.text.split('\n')
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="รับทราบพาดหัวข่าวแล้วครับ! ส่งรูปพื้นหลังมาได้เลย 🖼️"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    uid = event.source.user_id
    if uid not in user_states:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาพิมพ์หัวข้อข่าวก่อนส่งรูปภาพนะครับ"))
        return
    
    try:
        content = line_bot_api.get_message_content(event.message.id)
        img_b = content.content
        
        res_img = generate_cover(img_b, user_states[uid])
        url = upload_to_imgbb(res_img)
        
        line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=url, preview_image_url=url))
        del user_states[uid]
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"เกิดข้อผิดพลาด: {str(e)}"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
