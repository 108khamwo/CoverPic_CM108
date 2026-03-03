import os
import requests
from io import BytesIO
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage, ImageSendMessage
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime

app = Flask(__name__)

# ==========================================
# 1. ตั้งค่า API Keys (ใส่ให้ครบเรียบร้อยแล้ว)
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = 'A2I4k7+oJf6pGXFzvQCjzRr8Bpk2SZWDmBn3m0IXXzYj3q1EEjJAFZbsqaKXnN+n20j6EtKWQbxCoBUEED5D4pgW5BfMfesrSUCYz8IuS/EWc+beF9gGYsYI2RR7LOYdV7eDTrrbi9VcWyr5I7OsdQdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'b7ac02ec7b085a0e1a37841769ee32c4'
IMGBB_API_KEY = '66827500c20f99afb6779ba1730855b8'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# URL สำหรับกรอบรูป CM108 (จาก HTML ของคุณ)
FRAME_URL = "https://wsrv.nl/?url=blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEiOOtphYnEgsG_Q_5Ht_nM8h4hBJkTlJ0HvXwVOlixbfIkYC4y4NTIxcfl58PvyUi9Tj9azFCGGRCK3ysLAyX3yzXVHRmfbtsau733we6uQ3DE6csoMtWBMG2TNS2i-8aOtvIKTpzkCIyh3avLpViH74sW5SnwEZCkkToZeB4Q6VO-cxHafdputo5SmSxE/s16000/%E0%B8%81%E0%B8%A3%E0%B8%AD%E0%B8%9A%E0%B9%80%E0%B8%9B%E0%B8%A5%E0%B9%88%E0%B8%B2.png&output=png"

# เก็บข้อความชั่วคราวแยกตาม User
user_states = {}

# ==========================================
# 2. ฟังก์ชันหลัก: สร้างภาพปกข่าว
# ==========================================
def generate_cover(bg_image_bytes, text_lines):
    base_width, base_height = 1080, 1350
    canvas = Image.new('RGB', (base_width, base_height), color='black')
    
    # 2.1 จัดการรูปพื้นหลัง
    bg = Image.open(BytesIO(bg_image_bytes)).convert("RGB")
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
    
    # 2.2 วาด Gradient สีดำด้านล่าง
    gradient = Image.new('RGBA', (base_width, base_height), (0,0,0,0))
    draw_grad = ImageDraw.Draw(gradient)
    grad_height = 740
    start_y = base_height - grad_height
    for y in range(start_y, base_height):
        alpha = int(255 * ((y - start_y) / grad_height))
        draw_grad.line([(0, y), (base_width, y)], fill=(0, 0, 0, alpha))
    canvas = Image.alpha_composite(canvas.convert('RGBA'), gradient)
    
    # 2.3 จัดการฟอนต์ (ต้องมีไฟล์ Prompt-Bold.ttf ในเครื่อง)
    try:
        font_path = "Prompt-Bold.ttf"
        font_large = ImageFont.truetype(font_path, 95)
        font_med = ImageFont.truetype(font_path, 55)
        font_date = ImageFont.truetype(font_path, 34)
    except:
        font_large = ImageFont.load_default()
        font_med = font_large
        font_date = font_large

    draw = ImageDraw.Draw(canvas)
    
    # 2.4 วาดข้อความ (พิกัดเลียนแบบ HTML)
    # บรรทัด 1
    t1 = text_lines[0] if len(text_lines) > 0 else ""
    if t1:
        bbox = draw.textbbox((0, 0), t1, font=font_large)
        w = bbox[2] - bbox[0]
        draw.text(((base_width - w)/2, 850), t1, font=font_large, fill="#4bfafc", stroke_width=4, stroke_fill="black")
    
    # บรรทัด 2 (มีไฮไลท์)
    t2 = text_lines[1] if len(text_lines) > 1 else ""
    if t2:
        bbox = draw.textbbox((0, 0), t2, font=font_large)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = (base_width - w)/2, 960
        draw.rounded_rectangle([(x-30, y-15), (x+w+30, y+h+35)], radius=16, fill="#0bc8fa")
        draw.text((x, y), t2, font=font_large, fill="#ffffff", stroke_width=4, stroke_fill="black")
        
    # บรรทัด 3
    t3 = text_lines[2] if len(text_lines) > 2 else ""
    if t3:
        bbox = draw.textbbox((0, 0), t3, font=font_med)
        w = bbox[2] - bbox[0]
        draw.text(((base_width - w)/2, 1100), t3, font=font_med, fill="#ff9012", stroke_width=3, stroke_fill="black")

    # วันที่
    thai_months = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    now = datetime.now()
    date_str = f"- {now.day} {thai_months[now.month-1]} {now.year + 543} -"
    bbox = draw.textbbox((0, 0), date_str, font=font_date)
    w = bbox[2] - bbox[0]
    draw.text(((base_width - w)/2, 1200), date_str, font=font_date, fill="white")
    
    # 2.5 วางกรอบ CM108
    resp = requests.get(FRAME_URL)
    frame = Image.open(BytesIO(resp.content)).convert("RGBA")
    frame = frame.resize((base_width, base_height), Image.Resampling.LANCZOS)
    canvas = Image.alpha_composite(canvas, frame)
    
    output = BytesIO()
    canvas.convert('RGB').save(output, format='JPEG', quality=90)
    return output.getvalue()

# ==========================================
# 3. ฟังก์ชันอัปโหลดรูปขึ้น ImgBB
# ==========================================
def upload_to_imgbb(image_bytes):
    url = f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}"
    resp = requests.post(url, files={'image': image_bytes})
    return resp.json()['data']['url']

# ==========================================
# 4. Webhook Server
# ==========================================
@app.route("/callback", methods=['POST'])
def callback():
    sig = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_states[event.source.user_id] = event.message.text.split('\n')
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="รับทราบพาดหัวข่าวแล้วครับ! ✍️\nกรุณาส่งรูปภาพพื้นหลังมาได้เลยครับ"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    if user_id not in user_states:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาพิมพ์ข้อความพาดหัวข่าวก่อนนะครับ"))
        return
        
    # ดึงรูปจาก LINE
    content = line_bot_api.get_message_content(event.message.id)
    img_bytes = b"".join(content.iter_content())
    
    try:
        # สร้างรูปและอัปโหลด
        final_img = generate_cover(img_bytes, user_states[user_id])
        url = upload_to_imgbb(final_img)
        
        # ส่งกลับ
        line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=url, preview_image_url=url))
        del user_states[user_id]
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"เกิดข้อผิดพลาด: {str(e)}"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))