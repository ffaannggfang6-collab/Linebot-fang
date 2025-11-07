import os
from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, TextSendMessage,
    ImageSendMessage, UnsendEvent
)
from datetime import datetime
import pytz
from PIL import Image

app = Flask(__name__)

# ===== LINE CONFIG =====
CHANNEL_ACCESS_TOKEN = "CHJScm6eOVvEqpKzbP7Y0fYj5tVRlaA72LjvZH5Zzye9FzDZBROUF0sBVQgj31Pu52Xw9zoXTHz9syr3D6asy8RX7g+GXeHBKUr+eAHwQKtYz9pDsewuN8x1lwxp4bZeqj6C2cQ92/CBQB5nDac2owdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "5b32df6428ad0f8861a721bf688522c0"
YOUR_DOMAIN = "https://linebot-fang.onrender.com"

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ======= Memory =======
message_memory = {}    # เก็บข้อความเอาไว้ก่อนโดนยกเลิก
image_memory = {}      # เก็บภาพที่ส่งมา
chat_counter = {}      # นับข้อความ/ภาพต่อห้อง

# ======= Folder =======
IMAGE_FOLDER = "images"
os.makedirs(IMAGE_FOLDER, exist_ok=True)

# ====== Serve Images ======
@app.route('/images/<path:filename>')
def serve_image(filename):
    full = os.path.join(IMAGE_FOLDER, filename)
    if os.path.exists(full):
        return send_file(full, mimetype='image/jpeg')
    return "File not found", 404

# ====== Root ======
@app.route("/")
def home():
    return "LINE Bot ทำงานปกติ 🎉"

# ====== Webhook ======
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        print("Error:", e)
        abort(500)
    return "OK"


# ============= รับข้อความ =============
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    group_id = getattr(event.source, "group_id", user_id)
    msg_id = event.message.id
    text = event.message.text.strip()

    # Reset counter เมื่อเจอ ###
    if text == "###":
        chat_counter[group_id] = 0
        return

    # ไม่เก็บถ้าเป็น emoji / . / @
    if text in [".", "@"] or len(text) == 1 and not text.isalnum():
        return

    # บันทึกข้อความ (กันยกเลิก)
    message_memory[msg_id] = {
        "user_id": user_id,
        "text": text
    }

    # เริ่มนับเฉพาะข้อความจริง
    chat_counter[group_id] = chat_counter.get(group_id, 0) + 1


# ============= รับรูปภาพ =============
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    group_id = getattr(event.source, "group_id", user_id)
    msg_id = event.message.id

    # ดาวน์โหลดไฟล์ภาพ
    content = line_bot_api.get_message_content(msg_id)
    file_path = os.path.join(IMAGE_FOLDER, f"{msg_id}.jpg")

    with open(file_path, "wb") as f:
        for chunk in content.iter_content():
            f.write(chunk)

    image_memory[msg_id] = {
        "user_id": user_id,
        "path": file_path
    }

    # นับภาพเป็น 1 บิน
    chat_counter[group_id] = chat_counter.get(group_id, 0) + 1


# ============= ดักข้อความ/ภาพที่ถูกลบ =============
@handler.add(UnsendEvent)
def handle_unsend(event):
    msg_id = event.unsend.message_id
    source = event.source

    # เป้าหมายตอบกลับ
    target = (
        getattr(source, "group_id", None)
        or getattr(source, "room_id", None)
        or getattr(source, "user_id", None)
    )

    now = datetime.now(pytz.timezone("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M:%S")

    # ====== กรณีภาพถูกลบ ======
    if msg_id in image_memory:
        data = image_memory.pop(msg_id)
        try:
            profile = line_bot_api.get_profile(data["user_id"])
            user_name = profile.display_name
        except:
            user_name = "ไม่ทราบชื่อ"

        reply = (
            "[ ภาพที่ถูกยกเลิก ]\n"
            f"• ผู้ส่ง: {user_name}\n"
            f"• เวลา: {now}\n"
            f"• ภาพ: (ส่งภาพต้นฉบับกลับมา)"
        )

        file_name = os.path.basename(data["path"])
        url = f"https://{YOUR_DOMAIN}/images/{file_name}"

        line_bot_api.push_message(target, TextMessage(text=reply))
        line_bot_api.push_message(target, ImageSendMessage(
            original_content_url=url,
            preview_image_url=url
        ))
        return

    # ====== กรณีข้อความถูกลบ ======
    if msg_id in message_memory:
        data = message_memory.pop(msg_id)
        try:
            profile = line_bot_api.get_profile(data["user_id"])
            user_name = profile.display_name
        except:
            user_name = "ไม่ทราบชื่อ"

        reply = (
            "[ ข้อความที่ถูกยกเลิก ]\n"
            f"• ผู้ส่ง: {user_name}\n"
            f"• เวลา: {now}\n"
            f"• ข้อความ: {data['text']}"
        )

        line_bot_api.push_message(target, TextMessage(text=reply))
        return

    # ถ้าไม่พบข้อมูล
    line_bot_api.push_message(target, TextMessage("[ ข้อความที่ถูกยกเลิก ]\n• ไม่พบต้นฉบับ"))


# ======= Run (สำหรับ local) =======
if __name__ == "__main__":
    app.run(port=5000)
