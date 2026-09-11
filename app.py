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
FRAME_URL = "https://i.postimg.cc/CFn8kCvh/New-16-7-69.png"

user_states = {}

# รองรับการเลื่อนภาพทั้งแกน X/Y และซูมภาพ
def generate_cover(bg_image_bytes, text_lines, x_offset=0, y_offset=0, zoom=1.0):
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

def parse_adjust_command(text):
    """แปลงคำสั่งปรับภาพจาก LINE ให้เป็นคำสั่งมาตรฐาน"""
    cmd = text.strip().lower()

    # คำสั่งเดิม: +50 / -50 / 50 = ปรับแกน Y เหมือนเวอร์ชันเดิม
    if re.fullmatch(r'[+-]?\d+', cmd):
        return ('y_delta', int(cmd))

    # คำสั่งเลื่อนภาพแบบอ่านง่าย รองรับทั้งมี/ไม่มีช่องว่าง เช่น ซ้าย50, ซ้าย 50
    move_patterns = [
        (r'^(?:ซ้าย|left)\s*([+-]?\d+)\s*(?:px)?$', 'x_delta', -1),
        (r'^(?:ขวา|right)\s*([+-]?\d+)\s*(?:px)?$', 'x_delta', 1),
        (r'^(?:ขึ้น|up)\s*([+-]?\d+)\s*(?:px)?$', 'y_delta', -1),
        (r'^(?:ลง|down)\s*([+-]?\d+)\s*(?:px)?$', 'y_delta', 1),
    ]
    for pattern, action, direction in move_patterns:
        m = re.fullmatch(pattern, cmd)
        if m:
            return (action, direction * abs(int(m.group(1))))

    # ตั้งค่าซูมโดยตรง เช่น "ซูม 1.2" หรือ "zoom 1.2"
    m = re.fullmatch(r'(?:ซูม|zoom)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:x)?$', cmd)
    if m:
        value = float(m.group(1))
        # ถ้าพิมพ์ 120 ให้ตีความเป็น 120% = 1.20 เท่า
        if value > 10:
            value /= 100.0
        return ('zoom_set', value)

    # ซูมเข้า/ออกเป็นเปอร์เซ็นต์ เช่น "ซูมเข้า 10", "ซูมออก 10"
    m = re.fullmatch(r'(?:ซูมเข้า|zoom\s*in)\s*([0-9]+(?:\.[0-9]+)?)?\s*%?$', cmd)
    if m:
        percent = float(m.group(1) or 10)
        return ('zoom_percent', percent)

    m = re.fullmatch(r'(?:ซูมออก|zoom\s*out)\s*([0-9]+(?:\.[0-9]+)?)?\s*%?$', cmd)
    if m:
        percent = float(m.group(1) or 10)
        return ('zoom_percent', -percent)

    if cmd in ('รีเซ็ต', 'reset', 'รีเซ็ตรูป', 'reset image'):
        return ('reset', None)

    return None


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
    )


def adjustment_help_text(state=None):
    # ข้อความช่วยจำแบบสั้น เพื่อไม่ให้แชต LINE รก
    hint = "💡 ขยับภาพ: ซ้าย50 | ขวา50 | ขึ้น50 | ลง50 | ซูม120 | รีเซ็ต"
    if not state:
        return hint

    return (
        hint
        + f"\nตำแหน่ง: X {state.get('x_offset', 0):+d} | "
          f"Y {state.get('y_offset', 0):+d} | ซูม {state.get('zoom', 1.0):.2f}x"
    )


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    uid = event.source.user_id
    text = event.message.text.strip()

    # 1. ถ้ามีรูปค้างอยู่ ให้ลองตีความเป็นคำสั่งปรับตำแหน่ง/ซูมก่อน
    if uid in user_states and user_states[uid].get('image_id'):
        command = parse_adjust_command(text)
        if command:
            action, value = command
            state = user_states[uid]
            state.setdefault('x_offset', 0)
            state.setdefault('y_offset', 0)
            state.setdefault('zoom', 1.0)

            if action == 'x_delta':
                state['x_offset'] += int(value)
            elif action == 'y_delta':
                state['y_offset'] += int(value)
            elif action == 'zoom_set':
                state['zoom'] = max(0.25, min(float(value), 4.0))
            elif action == 'zoom_percent':
                state['zoom'] *= (1.0 + float(value) / 100.0)
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

    # 2. หากไม่ใช่คำสั่งปรับภาพ ให้ถือว่าเป็นพาดหัวข่าวใหม่
    user_states[uid] = {
        'texts': event.message.text.split('\n'),
        'image_id': None,
        'x_offset': 0,
        'y_offset': 0,
        'zoom': 1.0,
    }
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="รับทราบพาดหัวข่าวแล้วครับ! ส่งรูปประกอบข่าวมาได้เลย 🖼️"))


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    uid = event.source.user_id
    if uid not in user_states or not user_states[uid].get('texts'):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาพิมพ์หัวข้อข่าวก่อนส่งรูปภาพนะครับ"))
        return

    try:
        content = line_bot_api.get_message_content(event.message.id)
        img_b = content.content

        # บันทึกรูปต้นฉบับและรีเซ็ตตำแหน่ง/ซูมสำหรับรูปใหม่
        user_states[uid]['image_id'] = event.message.id
        user_states[uid]['x_offset'] = 0
        user_states[uid]['y_offset'] = 0
        user_states[uid]['zoom'] = 1.0

        res_img = generate_cover(
            img_b,
            user_states[uid]['texts'],
            x_offset=0,
            y_offset=0,
            zoom=1.0,
        )
        url = upload_to_cloudinary(res_img)

        line_bot_api.reply_message(
            event.reply_token,
            [
                ImageSendMessage(original_content_url=url, preview_image_url=url),
                TextSendMessage(text="เสร็จเรียบร้อย! ✨\n\n" + adjustment_help_text(user_states[uid]) + "\n\nหรือพิมพ์พาดหัวข่าวใหม่เพื่อเริ่มรูปถัดไปได้เลยครับ")
            ]
        )
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"เกิดข้อผิดพลาดในการอัปโหลดรูป: {str(e)}"))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
