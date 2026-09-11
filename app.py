import os
import re
import requests
from io import BytesIO
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage, ImageSendMessage
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime
import time
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

# ==========================================
# รูปปกจาก GitHub (ใช้ URL เดิมได้แม้เปลี่ยนไฟล์รูปในภายหลัง)
# ==========================================
MAIN_COVER_URL = "https://raw.githubusercontent.com/108khamwo/CoverPic_CM108/main/cover-main.png"
CHIANGMAI_OVERLAY_URL = "https://raw.githubusercontent.com/108khamwo/CoverPic_CM108/main/chiangmai-overlay.png"

# ไฟล์สำรองในโปรเจกต์ กรณี GitHub โหลดไม่ได้ชั่วคราว
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_COVER_FALLBACK = os.path.join(BASE_DIR, "cover-main.png")
CHIANGMAI_OVERLAY_FALLBACK = os.path.join(BASE_DIR, "chiangmai-overlay.png")

user_states = {}


# คำ/ชื่อพื้นที่ที่ใช้ช่วยตรวจว่าข่าวเกี่ยวข้องกับจังหวัดเชียงใหม่
# ตั้งใจใช้เฉพาะคำที่ค่อนข้างชี้เฉพาะพื้นที่ เพื่อลดการติดป้ายผิดโดยไม่จำเป็น
CHIANGMAI_LOCATION_KEYWORDS = [
    # จังหวัด / เมือง
    "เชียงใหม่", "จ.เชียงใหม่", "จังหวัดเชียงใหม่", "เมืองเชียงใหม่", "ตัวเมืองเชียงใหม่",

    # 25 อำเภอของจังหวัดเชียงใหม่
    "เมืองเชียงใหม่", "จอมทอง", "แม่แจ่ม", "เชียงดาว", "ดอยสะเก็ด",
    "แม่แตง", "แม่ริม", "สะเมิง", "ฝาง", "แม่อาย", "พร้าว",
    "สันป่าตอง", "สันกำแพง", "สันทราย", "หางดง", "ฮอด",
    "ดอยเต่า", "อมก๋อย", "สารภี", "เวียงแหง", "ไชยปราการ",
    "แม่วาง", "แม่ออน", "ดอยหล่อ", "กัลยาณิวัฒนา",

    # จุด/สถานที่เชียงใหม่ที่พบในพาดหัวบ่อย
    "ดอยสุเทพ", "ดอยอินทนนท์", "ท่าแพ", "ประตูท่าแพ", "คูเมือง",
    "นิมมาน", "แม่โจ้", "ม่อนแจ่ม", "แม่กำปอง", "อ่างขาง",
    "มหาวิทยาลัยเชียงใหม่", "มช.", "กาดหลวง", "เวียงกุมกาม",
]


def is_chiangmai_news(text_lines):
    """ตรวจข่าวเชียงใหม่จากคำจังหวัด อำเภอ และสถานที่สำคัญในพาดหัว"""
    combined = " ".join(str(line) for line in (text_lines or [])).strip().lower()
    return any(keyword.lower() in combined for keyword in CHIANGMAI_LOCATION_KEYWORDS)


def should_use_chiangmai_overlay(text_lines, mode="auto"):
    """
    mode = auto : ตรวจจากเนื้อหาพาดหัวอัตโนมัติ
    mode = on   : บังคับแสดงแถบข่าวเชียงใหม่
    mode = off  : บังคับไม่แสดงแถบข่าวเชียงใหม่
    """
    mode = (mode or "auto").lower()
    if mode == "on":
        return True
    if mode == "off":
        return False
    return is_chiangmai_news(text_lines)


def load_overlay_image(url, fallback_path=None):
    """โหลด PNG จาก GitHub แบบกัน cache และ fallback ไปไฟล์ local หากโหลดไม่สำเร็จ"""
    headers = {
        'User-Agent': 'Mozilla/5.0 CM108-LineBot',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    }

    # เติม query ป้องกัน CDN/browser cache เมื่อมีการอัปโหลดรูปใหม่ทับชื่อเดิม
    separator = '&' if '?' in url else '?'
    fresh_url = f"{url}{separator}v={int(time.time())}"

    try:
        resp = requests.get(fresh_url, headers=headers, timeout=15)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception as e:
        print(f"Remote overlay load failed: {url} -> {e}")

    if fallback_path and os.path.exists(fallback_path):
        try:
            return Image.open(fallback_path).convert("RGBA")
        except Exception as e:
            print(f"Fallback overlay load failed: {fallback_path} -> {e}")

    return None

# รองรับการเลื่อนภาพทั้งแกน X/Y และซูมภาพ
def generate_cover(bg_image_bytes, text_lines, x_offset=0, y_offset=0, zoom=1.0, chiangmai_mode="auto"):
    base_width, base_height = 1080, 1350
    
    try:
        bg = Image.open(BytesIO(bg_image_bytes)).convert("RGB")
    except Exception as e:
        print(f"Error opening background: {e}")
        raise ValueError("ไม่สามารถอ่านไฟล์รูปภาพที่ส่งมาได้")

    canvas = Image.new('RGB', (base_width, base_height), color='black')
    
    # ---------------------------------------------------------
    # [ส่วนเพิ่มใหม่]: สร้างพื้นหลังแบบเบลอ (Blurred Background)
    # ---------------------------------------------------------
    bg_blur_w = base_width
    bg_blur_h = int(bg.height * (base_width / bg.width))
    
    # ถ้ารูปยาวไม่พอดีกับความสูง canvas ให้ตัดขอบ (Crop) ให้เต็มพื้นที่
    if bg_blur_h < base_height:
        bg_blur_h = base_height
        bg_blur_w = int(base_height * (bg.width / bg.height))
    
    bg_blur = bg.resize((bg_blur_w, bg_blur_h), Image.Resampling.LANCZOS)
    
    # จัดให้อยู่กึ่งกลาง
    left_blur = (bg_blur_w - base_width) // 2
    top_blur = (bg_blur_h - base_height) // 2
    bg_blur = bg_blur.crop((left_blur, top_blur, left_blur + base_width, top_blur + base_height))
    
    # ทำเบลอหนักๆ (ค่ารัศมี 30)
    bg_blur = bg_blur.filter(ImageFilter.GaussianBlur(radius=30))
    
    # วางพื้นหลังเบลอเป็นชั้นล่างสุด
    canvas.paste(bg_blur, (0, 0))
    # ---------------------------------------------------------

    # เตรียมรูปหลักเพื่อวางทับแบบมีพิกัด
    # ค่า zoom=1.0 จะให้ขนาด/ตำแหน่งเริ่มต้นใกล้เคียงระบบเดิม
    fit_w = base_width
    fit_h = int(bg.height * (base_width / bg.width))

    min_img_h = 800
    if fit_h < min_img_h:
        fit_h = min_img_h
        fit_w = int(min_img_h * (bg.width / bg.height))

    # จำกัดช่วงซูมเพื่อป้องกันค่าผิดพลาด/รูปใหญ่เกินจำเป็น
    zoom = max(0.25, min(float(zoom), 4.0))
    new_w = max(1, int(round(fit_w * zoom)))
    new_h = max(1, int(round(fit_h * zoom)))
    bg_main = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # จัดกึ่งกลางแนวนอนเป็นค่าเริ่มต้น แล้วค่อยบวก x_offset
    # การซูมจะขยาย/ย่อรอบจุดกึ่งกลางของรูป ไม่กระโดดไปทางมุมซ้ายบน
    base_x = (base_width - fit_w) // 2
    zoom_center_x = -((new_w - fit_w) // 2)
    zoom_center_y = -((new_h - fit_h) // 2)
    paste_x = base_x + zoom_center_x + int(x_offset)
    paste_y = zoom_center_y + int(y_offset)

    # x_offset: + เลื่อนไปขวา, - เลื่อนไปซ้าย
    # y_offset: + เลื่อนลง, - เลื่อนขึ้น
    canvas.paste(bg_main, (paste_x, paste_y))
    
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
    
    # ชั้นปกหลัก: โหลดจาก GitHub ก่อน และใช้ไฟล์ local เป็น fallback
    fr = load_overlay_image(MAIN_COVER_URL, MAIN_COVER_FALLBACK)
    if fr is not None:
        fr = fr.resize((base_width, base_height), Image.Resampling.LANCZOS)
        canvas = Image.alpha_composite(canvas, fr)

    # ชั้นที่ 2 สำหรับข่าวเชียงใหม่
    # โหมด auto จะตรวจชื่อจังหวัด/อำเภอ/สถานที่ในเชียงใหม่ และสามารถบังคับเปิด/ปิดได้จาก LINE
    if should_use_chiangmai_overlay(text_lines, chiangmai_mode):
        cm_overlay = load_overlay_image(CHIANGMAI_OVERLAY_URL, CHIANGMAI_OVERLAY_FALLBACK)
        if cm_overlay is not None:
            cm_overlay = cm_overlay.resize((base_width, base_height), Image.Resampling.LANCZOS)
            canvas = Image.alpha_composite(canvas, cm_overlay)

    font_path = os.path.join(BASE_DIR, "Prompt-Bold.ttf")
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

    t1 = text_lines[0] if len(text_lines) > 0 else ""
    if t1:
        f_t1 = get_auto_font(t1, 110, 970) 
        y1_floor = 730 
        draw_stretched_text(canvas, (base_width/2, y1_floor), t1, font=f_t1, fill="#4bfafc", 
                            stretch_ratio=1.08, stroke_width=5, stroke_fill="black", anchor="ms")
    
    t2 = text_lines[1] if len(text_lines) > 1 else ""
    if t2:
        f_t2 = get_auto_font(t2, 90, 960) 
        size2 = getattr(f_t2, "size", 100)
        y2_floor = 870 
        
        bbox = draw.textbbox((base_width/2, y2_floor), t2, font=f_t2, anchor="ms")
        
        box_thickness = 105
        box_top = y2_floor - (box_thickness * 0.95) - 10
        box_bottom = y2_floor + (box_thickness * 0.35) + 15
        pad_x = 25      
        
        shadow_offset = 8
        draw.rounded_rectangle([(bbox[0]-pad_x+shadow_offset, box_top+shadow_offset), 
                                (bbox[2]+pad_x+shadow_offset, box_bottom+shadow_offset)], 
                               radius=16, fill="black")
        
        draw.rounded_rectangle([(bbox[0]-pad_x, box_top), (bbox[2]+pad_x, box_bottom)], 
                               radius=16, fill="#0bc8fa", outline="black", width=5)
        
        y2_text_floor = 840 + (size2 * 0.3)
        
        draw_stretched_text(canvas, (base_width/2, y2_text_floor), t2, font=f_t2, fill="#ffffff", 
                            stretch_ratio=1.08, text_shadow=4, stroke_width=4, stroke_fill="black", anchor="ms")
        
    t3 = text_lines[2] if len(text_lines) > 2 else ""
    if t3:
        f_t3 = get_auto_font(t3, 63, 960) 
        y3_floor = 1005 
        draw_stretched_text(canvas, (base_width/2, y3_floor), t3, font=f_t3, fill="#ff9012", 
                            stretch_ratio=1.08, stroke_width=3, stroke_fill="black", anchor="ms")

    thai_m = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    now = datetime.now()
    d_str = f"-{now.day} {thai_m[now.month-1]} {now.year + 543}-"
    y_date_floor = 1060 
    
    try:
        f_date = ImageFont.truetype(font_path, 32)
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

def parse_chiangmai_cover_command(text):
    """คำสั่งเลือกแถบข่าวเชียงใหม่แบบชัดเจน เพื่อใช้แก้กรณีตรวจอัตโนมัติไม่ตรง"""
    cmd = text.strip().lower()
    if cmd in ("ปกเชียงใหม่", "แถบเชียงใหม่", "ใช้ปกเชียงใหม่"):
        return "on"
    if cmd in ("ปกทั่วไป", "ไม่ใช้ปกเชียงใหม่", "ปิดแถบเชียงใหม่"):
        return "off"
    if cmd in ("ปกอัตโนมัติ", "ปกauto", "ปก auto", "แถบอัตโนมัติ"):
        return "auto"
    return None


def parse_chiangmai_answer(text):
    """อ่านคำตอบสั้น ๆ ของคำถามว่าเป็นข่าวเชียงใหม่หรือไม่"""
    cmd = text.strip().lower()
    yes_answers = {"ใช่", "ใช่ครับ", "ใช่ค่ะ", "เป็น", "เป็นครับ", "เป็นค่ะ"}
    no_answers = {"ไม่ใช่", "ไม่ใช่ครับ", "ไม่ใช่ค่ะ", "ไม่", "ไม่ครับ", "ไม่ค่ะ"}
    if cmd in yes_answers:
        return True
    if cmd in no_answers:
        return False
    return None


def chiangmai_mode_text(state):
    mode = (state or {}).get('chiangmai_mode', 'auto')
    if mode == 'on':
        return "ปกเชียงใหม่: เปิด (บังคับ)"
    if mode == 'off':
        return "ปกเชียงใหม่: ปิด (บังคับ)"
    detected = is_chiangmai_news((state or {}).get('texts', []))
    return "ปกเชียงใหม่: อัตโนมัติ - " + ("ตรวจพบข่าวเชียงใหม่" if detected else "ไม่พบเงื่อนไขเชียงใหม่")


def parse_adjust_command(text):
    """แปลงคำสั่งปรับภาพ 1 คำสั่งให้เป็นคำสั่งมาตรฐาน"""
    cmd = text.strip().lower()

    # คำสั่งเดิม: +50 / -50 / 50 = ปรับแกน Y เหมือนเวอร์ชันเดิม
    if re.fullmatch(r'[+-]?\d+', cmd):
        return ('y_delta', int(cmd))

    # คำสั่งเลื่อนภาพ รองรับทั้งมี/ไม่มีช่องว่าง
    # เพิ่ม alias "บน" = ขึ้น และ "ล่าง" = ลง ให้พิมพ์ได้เป็นธรรมชาติขึ้น
    move_patterns = [
        (r'^(?:ซ้าย|left)\s*([+-]?\d+)\s*(?:px)?$', 'x_delta', -1),
        (r'^(?:ขวา|right)\s*([+-]?\d+)\s*(?:px)?$', 'x_delta', 1),
        (r'^(?:ขึ้น|บน|up)\s*([+-]?\d+)\s*(?:px)?$', 'y_delta', -1),
        (r'^(?:ลง|ล่าง|down)\s*([+-]?\d+)\s*(?:px)?$', 'y_delta', 1),
    ]
    for pattern, action, direction in move_patterns:
        m = re.fullmatch(pattern, cmd)
        if m:
            return (action, direction * abs(int(m.group(1))))

    # ซูมแบบเข้าใจง่าย โดยถือว่า 100% คือค่าปกติ
    # ซูม1 ... ซูม20 = เพิ่มจากค่าปัจจุบันทีละเปอร์เซ็นต์
    # ซูม90 / ซูม100 / ซูม110 = ตั้งค่าเป็นเปอร์เซ็นต์นั้นโดยตรง
    # ซูม1.2x = ตั้งเป็น 1.2 เท่า (120%)
    m = re.fullmatch(r'(?:ซูม|zoom)\s*([0-9]+(?:\.[0-9]+)?)\s*(x|%)?$', cmd)
    if m:
        value = float(m.group(1))
        suffix = m.group(2)

        if suffix == 'x':
            return ('zoom_set', value)
        if suffix == '%':
            return ('zoom_set', value / 100.0)

        if 0 < value <= 20:
            return ('zoom_delta', value)
        return ('zoom_set', value / 100.0)

    # ซูมเข้า/ออกเป็นเปอร์เซ็นต์แบบเพิ่ม/ลดจากค่าปัจจุบัน
    m = re.fullmatch(r'(?:ซูมเข้า|zoom\s*in)\s*([0-9]+(?:\.[0-9]+)?)?\s*%?$', cmd)
    if m:
        percent = float(m.group(1) or 1)
        return ('zoom_delta', percent)

    m = re.fullmatch(r'(?:ซูมออก|zoom\s*out)\s*([0-9]+(?:\.[0-9]+)?)?\s*%?$', cmd)
    if m:
        percent = float(m.group(1) or 1)
        return ('zoom_delta', -percent)

    if cmd in ('รีเซ็ต', 'reset', 'รีเซ็ตรูป', 'reset image'):
        return ('reset', None)

    return None


def parse_adjust_commands(text):
    """
    รองรับ 1 หรือ 2 คำสั่งในข้อความเดียว เช่น:
      ซ้าย20 ขึ้น10
      ขวา10 ซูม1
      ซ้าย20 | บน10

    คืนค่า (commands, error_message)
    - commands = list ของ (action, value)
    - ถ้าไม่ใช่ข้อความคำสั่งปรับภาพเลย จะคืน (None, None)
    """
    cmd = text.strip().lower()
    if not cmd:
        return None, None

    # กรณีคำสั่งเดียว ใช้ parser เดิมก่อน เพื่อคง compatibility
    single = parse_adjust_command(cmd)
    if single:
        return [single], None

    # รองรับคำว่า "และ" รวมถึงตัวคั่น | , ; /
    work = re.sub(r'\s+และ\s+', ' ', cmd)

    token_pattern = re.compile(
        r'(?:'
        r'(?:ซ้าย|left|ขวา|right|ขึ้น|บน|up|ลง|ล่าง|down)\s*[+-]?\d+\s*(?:px)?'
        r'|(?:ซูมเข้า|zoom\s*in|ซูมออก|zoom\s*out)\s*(?:[0-9]+(?:\.[0-9]+)?)?\s*%?'
        r'|(?:ซูม|zoom)\s*[0-9]+(?:\.[0-9]+)?\s*(?:x|%)?'
        r'|(?:รีเซ็ต|reset|รีเซ็ตรูป|reset\s*image)'
        r')',
        re.IGNORECASE,
    )

    matches = list(token_pattern.finditer(work))
    if not matches:
        # ถ้ามีคำขึ้นต้นที่ดูเหมือนคำสั่งปรับภาพ ให้แจ้งว่ารูปแบบไม่ถูกต้อง
        if re.search(r'(ซ้าย|ขวา|ขึ้น|บน|ลง|ล่าง|ซูม|รีเซ็ต|left|right|up|down|zoom|reset)', work, re.I):
            return None, 'ไม่เข้าใจคำสั่งปรับภาพครับ\nตัวอย่าง: ซ้าย20 ขึ้น10'
        return None, None

    # ตรวจว่าระหว่าง token มีแค่ช่องว่างหรือตัวคั่นที่อนุญาต
    leftovers = []
    last = 0
    for m in matches:
        leftovers.append(work[last:m.start()])
        last = m.end()
    leftovers.append(work[last:])
    leftover_text = ''.join(leftovers)
    if re.sub(r'[\s|,;/]+', '', leftover_text):
        return None, 'ไม่เข้าใจคำสั่งปรับภาพครับ\nตัวอย่าง: ซ้าย20 ขึ้น10'

    if len(matches) > 2:
        return None, 'สั่งปรับภาพได้สูงสุด 2 คำสั่งต่อครั้งครับ\nตัวอย่าง: ซ้าย20 ขึ้น10'

    commands = []
    for m in matches:
        parsed = parse_adjust_command(m.group(0))
        if not parsed:
            return None, 'ไม่เข้าใจคำสั่งปรับภาพครับ\nตัวอย่าง: ซ้าย20 ขึ้น10'
        commands.append(parsed)

    # รีเซ็ตควรใช้เดี่ยว ๆ เพื่อไม่ให้ความหมายกำกวม
    if len(commands) > 1 and any(action == 'reset' for action, _ in commands):
        return None, 'คำสั่ง รีเซ็ต ต้องใช้เดี่ยว ๆ ครับ'

    # ห้ามคำสั่งแกนเดียวกันที่สวนทางกัน
    def has_opposite(action_name):
        values = [value for action, value in commands if action == action_name and value is not None]
        return any(v < 0 for v in values) and any(v > 0 for v in values)

    if has_opposite('x_delta') or has_opposite('y_delta') or has_opposite('zoom_delta'):
        return None, (
            'ไม่สามารถใช้คำสั่งที่หักล้างกันในข้อความเดียวได้ครับ\n'
            'เช่น ซ้าย10 ขวา10 | ขึ้น10 ลง10 | ซูม1 ซูมออก1'
        )

    # ถ้าตั้งค่าซูมตรง ๆ 2 ครั้งในข้อความเดียว ให้ปฏิเสธเพราะปลายทางกำกวม
    if sum(1 for action, _ in commands if action == 'zoom_set') > 1:
        return None, 'กรุณากำหนดค่าซูมเพียง 1 ครั้งต่อข้อความครับ'

    return commands, None

def render_current_cover(uid):
    """สร้างปกใหม่จากสถานะล่าสุดของผู้ใช้"""
    state = user_states[uid]
    content = line_bot_api.get_message_content(state['image_id'])
    img_b = content.content
    return generate_cover(
        img_b,
        state['texts'],
        x_offset=state.get('x_offset', 0),
        y_offset=state.get('y_offset', 0),
        zoom=state.get('zoom', 1.0),
        chiangmai_mode=state.get('chiangmai_mode', 'auto'),
    )


def adjustment_help_text(state=None):
    # แสดงค่าซูมเป็นเปอร์เซ็นต์ เพื่อให้เข้าใจง่าย: 100% คือค่าปกติ
    hint = "💡 ต้องการขยับภาพ พิมพ์ เช่น ซ้าย10 | ขวา10 | ขึ้น10 | ลง10 | ซูม1 | ซูมออก1 | รีเซ็ต\n(รองรับ 2 คำสั่งพร้อมกัน เช่น ซ้าย20 ขึ้น10)"
    if not state:
        return hint

    zoom_percent = int(round(float(state.get('zoom', 1.0)) * 100))
    return (
        hint
        + f"\nตำแหน่งล่าสุด: X {state.get('x_offset', 0):+d} | "
          f"Y {state.get('y_offset', 0):+d} | ซูม {zoom_percent}%"
    )


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    uid = event.source.user_id
    text = event.message.text.strip()

    # 1. ถ้ามีรูปปกสร้างแล้ว ให้คำสั่งปรับภาพทำงานก่อนทุกเงื่อนไข
    # รองรับสูงสุด 2 คำสั่งในข้อความเดียว เช่น ซ้าย20 ขึ้น10 / ขวา10 ซูม1
    if uid in user_states and user_states[uid].get('image_id'):
        commands, adjust_error = parse_adjust_commands(text)

        if adjust_error:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=adjust_error)
            )
            return

        if commands:
            state = user_states[uid]
            # เมื่อมีภาพสร้างสำเร็จแล้ว ไม่ควรค้างสถานะรอคำตอบเชียงใหม่
            state['awaiting_chiangmai_answer'] = False
            state.setdefault('x_offset', 0)
            state.setdefault('y_offset', 0)
            state.setdefault('zoom', 1.0)

            # ทำทุกคำสั่งตามลำดับ แล้ว render เพียงครั้งเดียว
            for action, value in commands:
                if action == 'x_delta':
                    state['x_offset'] += int(value)
                elif action == 'y_delta':
                    state['y_offset'] += int(value)
                elif action == 'zoom_set':
                    state['zoom'] = max(0.25, min(float(value), 4.0))
                elif action == 'zoom_delta':
                    # เพิ่ม/ลดเป็นเปอร์เซ็นต์พอยต์ เช่น 100% + 2 = 102%
                    state['zoom'] += float(value) / 100.0
                    state['zoom'] = max(0.25, min(state['zoom'], 4.0))
                elif action == 'reset':
                    state['x_offset'] = 0
                    state['y_offset'] = 0
                    state['zoom'] = 1.0

            try:
                res_img = render_current_cover(uid)
                url = upload_to_cloudinary(res_img)
                line_bot_api.reply_message(
                    event.reply_token,
                    [
                        ImageSendMessage(original_content_url=url, preview_image_url=url),
                        TextSendMessage(text="ปรับรูปให้แล้วครับ ✨\n" + adjustment_help_text(state))
                    ]
                )
            except Exception as e:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"เกิดข้อผิดพลาดขณะปรับรูป: {str(e)}")
                )
            return

    # 2. ถ้าระบบกำลังรอคำตอบว่าเป็นข่าวเชียงใหม่หรือไม่ ให้รับ ใช่ / ไม่ใช่
    if uid in user_states and user_states[uid].get('awaiting_chiangmai_answer'):
        answer = parse_chiangmai_answer(text)
        if answer is not None:
            state = user_states[uid]
            state['chiangmai_mode'] = 'on' if answer else 'off'
            state['awaiting_chiangmai_answer'] = False
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาส่งรูปประกอบข่าวมาได้เลย 🖼️")
            )
            return

        # ระหว่างรอคำตอบ ไม่เอาข้อความอื่นไปสร้างเป็นพาดหัวใหม่โดยไม่ตั้งใจ
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="เป็นข่าวเชียงใหม่หรือไม่?")
        )
        return

    # 3. คำสั่งบังคับแถบข่าวเชียงใหม่ (ใช้ได้หลังพิมพ์พาดหัวแล้ว)
    cover_mode = parse_chiangmai_cover_command(text)
    if cover_mode is not None:
        if uid not in user_states or not user_states[uid].get('texts'):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาพิมพ์พาดหัวข่าวก่อน แล้วค่อยเลือก ปกเชียงใหม่ / ปกทั่วไป / ปกอัตโนมัติ")
            )
            return

        state = user_states[uid]
        state['chiangmai_mode'] = cover_mode
        state['awaiting_chiangmai_answer'] = False

        # ถ้ามีรูปอยู่แล้ว ให้สร้างภาพใหม่ทันทีด้วยโหมดที่เลือก
        if state.get('image_id'):
            try:
                res_img = render_current_cover(uid)
                url = upload_to_cloudinary(res_img)
                line_bot_api.reply_message(
                    event.reply_token,
                    [
                        ImageSendMessage(original_content_url=url, preview_image_url=url),
                        TextSendMessage(text=chiangmai_mode_text(state) + "\n" + adjustment_help_text(state))
                    ]
                )
            except Exception as e:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"เกิดข้อผิดพลาดขณะเปลี่ยนปก: {str(e)}")
                )
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=chiangmai_mode_text(state)))
        return

    # 4. หากไม่ใช่คำสั่งใด ให้ถือว่าเป็นพาดหัวข่าวใหม่
    texts = event.message.text.split('\n')
    detected_chiangmai = is_chiangmai_news(texts)
    user_states[uid] = {
        'texts': texts,
        'image_id': None,
        'x_offset': 0,
        'y_offset': 0,
        'zoom': 1.0,
        # ถ้าตรวจพบเชียงใหม่ ใช้แถบทันที / ถ้าไม่พบ รอให้ผู้ใช้ยืนยัน
        'chiangmai_mode': 'on' if detected_chiangmai else 'auto',
        'awaiting_chiangmai_answer': not detected_chiangmai,
    }

    if detected_chiangmai:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="กรุณาส่งรูปประกอบข่าวมาได้เลย 🖼️")
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="เป็นข่าวเชียงใหม่หรือไม่?")
        )


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    uid = event.source.user_id
    if uid not in user_states or not user_states[uid].get('texts'):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาพิมพ์หัวข้อข่าวก่อนส่งรูปภาพนะครับ"))
        return

    if user_states[uid].get('awaiting_chiangmai_answer'):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="เป็นข่าวเชียงใหม่หรือไม่?"))
        return

    try:
        content = line_bot_api.get_message_content(event.message.id)
        img_b = content.content

        # บันทึกรูปต้นฉบับและรีเซ็ตตำแหน่ง/ซูมสำหรับรูปใหม่
        user_states[uid]['image_id'] = event.message.id
        user_states[uid]['x_offset'] = 0
        user_states[uid]['y_offset'] = 0
        user_states[uid]['zoom'] = 1.0
        # เมื่อมาถึงขั้นสร้างภาพแล้ว ให้ยืนยันว่าไม่มีสถานะคำถามเชียงใหม่ค้างอยู่
        user_states[uid]['awaiting_chiangmai_answer'] = False

        res_img = generate_cover(
            img_b,
            user_states[uid]['texts'],
            x_offset=0,
            y_offset=0,
            zoom=1.0,
            chiangmai_mode=user_states[uid].get('chiangmai_mode', 'auto'),
        )
        url = upload_to_cloudinary(res_img)

        line_bot_api.reply_message(
            event.reply_token,
            [
                ImageSendMessage(original_content_url=url, preview_image_url=url),
                TextSendMessage(text="เสร็จเรียบร้อย! ✨\n\n" + adjustment_help_text(user_states[uid]))
            ]
        )
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"เกิดข้อผิดพลาดในการอัปโหลดรูป: {str(e)}"))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
