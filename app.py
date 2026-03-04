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
    
    # --- การจัดตำแหน่งรูปพื้นหลังแบบชิดขอบบน (Top-Align) ---
    new_w = base_width
    new_h = int(bg.height * (base_width / bg.width))
    
    # ป้องกันรูปเตี้ยเกินไป (บังคับให้สูงอย่างน้อย 800px เพื่อให้คลุมถึงพาดหัว 1)
    min_img_h = 800
    if new_h < min_img_h:
        new_h = min_img_h
        new_w = int(min_img_h * (bg.width / bg.height))
        bg = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - base_width) // 2
        bg = bg.crop((left, 0, left + base_width, new_h))
    else:
        bg = bg.resize((base_width, new_h), Image.Resampling.LANCZOS)
    
    # วางรูปชิดขอบบนสุด
    canvas.paste(bg, (0, 0))
    
    # 2. วาดแถบสีดำ (ไล่ระดับสีดำแบบโค้ง Ease-In Gradient)
    gradient = Image.new('RGBA', (base_width, base_height), (0,0,0,0))
    draw_grad = ImageDraw.Draw(gradient)
    
    fade_start = 550
    fade_end = 715
    for y in range(fade_start, base_height):
        if y >= fade_end:
            alpha = 255
        else:
            ratio = (y - fade_start) / (fade_end - fade_start)
            alpha = int((ratio ** 2.5) * 255)
        alpha = min(255, max(0, alpha))
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

    # 4. จัดการฟอนต์และวาดข้อความ
    font_path = "Prompt-Bold.ttf"
    draw = ImageDraw.Draw(canvas)
    
    # ฟังก์ชันช่วยย่อขนาดฟอนต์อัตโนมัติ
    def get_auto_font(text, default_size, max_width):
        size = default_size
        try:
            font = ImageFont.truetype(font_path, size)
            while size > 10:
                bbox = draw.textbbox((0, 0), text, font=font)
                if (bbox[2] - bbox[0]) <= max_width:
                    break
                size -= 2 
                font = ImageFont.truetype(font_path, size)
            return font
        except:
            return ImageFont.load_default()

    # --- บรรทัดที่ 1 (พิกัด 740 ล็อกฐานเดิม) ---
    t1 = text_lines[0] if len(text_lines) > 0 else ""
    if t1:
        f_t1 = get_auto_font(t1, 120, 970) 
        y1_floor = 740 
        draw.text((base_width/2, y1_floor), t1, font=f_t1, fill="#4bfafc", stroke_width=5, stroke_fill="black", anchor="ms")
    
    # --- บรรทัดที่ 2 (พิกัด 880 + กรอบสีฟ้าความสูงคงที่) ---
    t2 = text_lines[1] if len(text_lines) > 1 else ""
    if t2:
        f_t2 = get_auto_font(t2, 100, 960) 
        size2 = getattr(f_t2, "size", 100)
        y2_floor = 880 
        
        bbox = draw.textbbox((base_width/2, y2_floor), t2, font=f_t2, anchor="ms")
        
        # คำนวณความสูงกรอบคงที่โดยอ้างอิงจากขนาดฟอนต์ 100 เสมอ ไม่ว่าตัวหนังสือจริงจะเล็กลงแค่ไหน
        box_top = y2_floor - (100 * 0.95) - 10
        box_bottom = y2_floor + (100 * 0.35) + 15
        pad_x = 25      
        
        # วาดเงาดำทึบของกล่อง
        shadow_offset = 8
        draw.rounded_rectangle([(bbox[0]-pad_x+shadow_offset, box_top+shadow_offset), 
                                (bbox[2]+pad_x+shadow_offset, box_bottom+shadow_offset)], 
                               radius=16, fill="black")
        
        # วาดกรอบสีฟ้า พร้อมเส้นขอบดำ
        draw.rounded_rectangle([(bbox[0]-pad_x, box_top), (bbox[2]+pad_x, box_bottom)], 
                               radius=16, fill="#0bc8fa", outline="black", width=5)
        
        # คำนวณชดเชยให้ข้อความขยับขึ้นไปอยู่กึ่งกลางกรอบเสมอเมื่อขนาดฟอนต์ถูกย่อ
        y2_text_floor = 850 + (size2 * 0.3)
        
        # เงาตัวหนังสือและตัวหนังสือจริง
        text_shadow = 5
        draw.text((base_width/2 + text_shadow, y2_text_floor + text_shadow), t2, font=f_t2, fill="black", stroke_width=5, stroke_fill="black", anchor="ms")
        draw.text((base_width/2, y2_text_floor), t2, font=f_t2, fill="#ffffff", stroke_width=5, stroke_fill="black", anchor="ms")
        
    # --- บรรทัดที่ 3 (พิกัด 1005) ---
    t3 = text_lines[2] if len(text_lines) > 2 else ""
    if t3:
        f_t3 = get_auto_font(t3, 70, 960) 
        y3_floor = 1005 
        draw.text((base_width/2, y3_floor), t3, font=f_t3, fill="#ff9012", stroke_width=3, stroke_fill="black", anchor="ms")

    # --- ส่วนของวันที่ (พิกัด 1060) ---
    thai_m = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    now = datetime.now()
    d_str = f"- {now.day} {thai_m[now.month-1]} {now.year + 543} -"
    y_date_floor = 1060
    try:
        f_date = ImageFont.truetype(font_path, 34)
        draw.text((base_width/2, y_date_floor), d_str, font=f_date, fill="white", anchor="ms")
    except:
        draw.text((base_width/2, y_date_floor), d_str, fill="white", anchor="ms")
    
    out = BytesIO()
    canvas.convert('RGB').save(out, format='JPEG', quality=95)
    return out.getvalue()

def upload_to_imgbb(img_bytes):
    url = f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}"
    r = requests.post(url, files={'image': img_bytes})
    return r.json()['data']['url']

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
