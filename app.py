import os
import requests
from io import BytesIO
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage, ImageSendMessage
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import cloudinary
import cloudinary.uploader

app = Flask(__name__)

# ==========================================
# 1. API Keys (อัปเดตใหม่ ปลอดภัยด้วย Environment Variables)
# ==========================================
# ดึงค่าจาก Environment Variables ของระบบ (Render) แทนการใส่ลงไปตรงๆ
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

# [ตั้งค่า Cloudinary ตรงนี้]
cloudinary.config( 
  cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'), 
  api_key = os.environ.get('CLOUDINARY_API_KEY'), 
  api_secret = os.environ.get('CLOUDINARY_API_SECRET') 
)

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ลิงก์กรอบรูป CM108
FRAME_URL = "https://i.ibb.co/BKwvcK5c/New-16-7-69.png"

user_states = {}

def generate_cover(bg_image_bytes, text_lines):
    base_width, base_height = 1080, 1350
    
    try:
        bg = Image.open(BytesIO(bg_image_bytes)).convert("RGB")
    except Exception as e:
        print(f"Error opening background: {e}")
        raise ValueError("ไม่สามารถอ่านไฟล์รูปภาพที่ส่งมาได้")

    canvas = Image.new('RGB', (base_width, base_height), color='black')
    
    new_w = base_width
    new_h = int(bg.height * (base_width / bg.width))
    
    min_img_h = 800
    if new_h < min_img_h:
        new_h = min_img_h
        new_w = int(min_img_h * (bg.width / bg.height))
        bg = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - base_width) // 2
        bg = bg.crop((left, 0, left + base_width, new_h))
    else:
        bg = bg.resize((base_width, new_h), Image.Resampling.LANCZOS)
    
    canvas.paste(bg, (0, 0))
    
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
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(FRAME_URL, headers=headers, timeout=15)
        if resp.status_code == 200:
            fr = Image.open(BytesIO(resp.content)).convert("RGBA")
            fr = fr.resize((base_width, base_height), Image.Resampling.LANCZOS)
            canvas = Image.alpha_composite(canvas, fr)
    except Exception as e:
        print(f"Frame Error: {e}")

    font_path = "Prompt-Bold.ttf"
    draw = ImageDraw.Draw(canvas)
    
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

    def draw_stretched_text(canvas_img, xy, text, font, fill, stretch_ratio=1.08, text_shadow=0, **kwargs):
        temp_img = Image.new('RGBA', canvas_img.size, (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_img)
        
        if text_shadow > 0:
            temp_draw.text((xy[0] + text_shadow, xy[1] + text_shadow), text, font=font, fill="black", **kwargs)
            
        temp_draw.text(xy, text, font=font, fill=fill, **kwargs)
        
        bbox = temp_img.getbbox()
        if not bbox: return
        cropped = temp_img.crop(bbox)
        
        new_w = cropped.width
        new_h = int(cropped.height * stretch_ratio)
        stretched = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        paste_x = bbox[0]
        paste_y = bbox[3] - new_h
        
        canvas_img.alpha_composite(stretched, (paste_x, paste_y))

    # --- บรรทัดที่ 1 ---
    t1 = text_lines[0] if len(text_lines) > 0 else ""
    if t1:
        f_t1 = get_auto_font(t1, 110, 970) 
        y1_floor = 730 
        draw_stretched_text(canvas, (base_width/2, y1_floor), t1, font=f_t1, fill="#4bfafc", 
                            stretch_ratio=1.08, stroke_width=5, stroke_fill="black", anchor="ms")
    
    # --- บรรทัดที่ 2 ---
    t2 = text_lines[1] if len(text_lines) > 1 else ""
    if t2:
        f_t2 = get_auto_font(t2, 90, 960) 
        size2 = getattr(f_t2, "size", 90)
        y2_floor = 870 
        
        bbox = draw.textbbox((base_width/2, y2_floor), t2, font=f_t2, anchor="ms")
        
        box_thickness = 108
        box_top = y2_floor - (box_thickness * 0.95) - 10
        box_bottom = y2_floor + (box_thickness * 0.35) + 15
        pad_x = 25      
        
        shadow_offset = 4
        draw.rounded_rectangle([(bbox[0]-pad_x+shadow_offset, box_top+shadow_offset), 
                                (bbox[2]+pad_x+shadow_offset, box_bottom+shadow_offset)], 
                               radius=16, fill="black")
        
        draw.rounded_rectangle([(bbox[0]-pad_x, box_top), (bbox[2]+pad_x, box_bottom)], 
                               radius=16, fill="#0bc8fa", outline="black", width=5)
        
        y2_text_floor = 845 + (size2 * 0.3)
        
        draw_stretched_text(canvas, (base_width/2, y2_text_floor), t2, font=f_t2, fill="#ffffff", 
                            stretch_ratio=1.08, text_shadow=2, stroke_width=3, stroke_fill="black", anchor="ms")
        
    # --- บรรทัดที่ 3 ---
    t3 = text_lines[2] if len(text_lines) > 2 else ""
    if t3:
        f_t3 = get_auto_font(t3, 63, 960) 
        y3_floor = 1005 
        draw_stretched_text(canvas, (base_width/2, y3_floor), t3, font=f_t3, fill="#ff9012", 
                            stretch_ratio=1.08, stroke_width=3, stroke_fill="black", anchor="ms")

    thai_m = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    now = datetime.now()
    d_str = f"-{now.day} {thai_m[now.month-1]} {now.year + 543}-"
    
    # [จุดที่แก้] ขยับตำแหน่งฐานวันที่ลงนิดหน่อยเพื่อรับกับความสูงที่เพิ่มขึ้น (จาก 1060 เป็น 1065)
    y_date_floor = 1065 
    
    try:
        # ปรับขนาดฟอนต์เริ่มต้นให้เล็กลงนิดนึง (จาก 34 เป็น 32) เพื่อให้ตอนโดนยืดเส้นจะไม่หนาเกินไป
        f_date = ImageFont.truetype(font_path, 32)
        
        # [จุดที่แก้หลัก]
        # 1. เพิ่ม stretch_ratio เป็น 1.15 (ยืด 15%) เฉพาะส่วนวันที่
        # 2. ปรับตัวหนังสือให้โปร่งขึ้นโดยไม่ใส่เส้นขอบทึบๆ
        draw_stretched_text(canvas, (base_width/2, y_date_floor), d_str, font=f_date, fill="white", 
                            stretch_ratio=1.15, text_shadow=2, anchor="ms")
    except:
        draw.text((base_width/2, y_date_floor), d_str, fill="white", anchor="ms")
    
    out = BytesIO()
    canvas.convert('RGB').save(out, format='JPEG', quality=95)
    return out.getvalue()

# [เปลี่ยนแปลงใหม่] ฟังก์ชันอัปโหลดรูปผ่าน Cloudinary
def upload_to_cloudinary(img_bytes):
    # ส่งรูปภาพในรูปแบบ bytes ไปที่ Cloudinary
    response = cloudinary.uploader.upload(img_bytes, folder="cm108_covers")
    # ดึงลิงก์ URL แบบ Secure (https) กลับมา
    return response['secure_url']

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
        
        # สร้างรูป
        res_img = generate_cover(img_b, user_states[uid])
        
        # [แก้ไข] อัปโหลดผ่าน Cloudinary แทน ImgBB
        url = upload_to_cloudinary(res_img)
        
        line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=url, preview_image_url=url))
        del user_states[uid]
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"เกิดข้อผิดพลาดในการอัปโหลดรูป: {str(e)}"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
