import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, TextSendMessage, UnsendEvent
)
from datetime import datetime
import pytz

app = Flask(__name__)

# ======= ตั้งค่า (เปลี่ยนเป็นของฟ่าง) =======
CHANNEL_ACCESS_TOKEN = "CHJScm6eOVvEqpKzbP7Y0fYj5tVRlaA72LjvZH5Zzye9FzDZBROUF0sBVQgj31Pu52Xw9zoXTHz9syr3D6asy8RX7g+GXeHBKUr+eAHwQKtYz9pDsewuN8x1lwxp4bZeqj6C2cQ92/CBQB5nDac2owdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "5b32df6428ad0f8861a721bf688522c0"
YOUR_DOMAIN = "https://linebot-fang.onrender.com"

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ======= หน่วยความจำแบบ in-memory =======
# เก็บข้อมูลข้อความ/ภาพตาม message id
message_log = {}        # { message_id: {"type":"text"/"image", "text": "...", "user_id": "...", "time": datetime } }

# สถิติของแต่ละกลุ่ม/แชท
stats = {}              # { chat_id: {"msg_count":int, "img_count":int, "deleted_text":int, "deleted_img":int, "bill_amount":int} }

# helper - ensure stats structure
def ensure_stats(chat_id):
    if chat_id not in stats:
        stats[chat_id] = {
            "msg_count": 0,
            "img_count": 0,
            "deleted_text": 0,
            "deleted_img": 0,
            "bill_amount": 0
        }

# ======= หน้าเช็คสถานะ =======
@app.route("/")
def home():
    return "LINE Bot Running ✅"

# ======= Webhook =======
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        # Log and return 500 so Render shows error
        print("Error in webhook handler:", e)
        abort(500)
    return "OK"

# ======= รับข้อความ (Text) =======
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    try:
        user_id = event.source.user_id
        chat_id = getattr(event.source, "group_id", None) or getattr(event.source, "room_id", None) or user_id

        ensure_stats(chat_id)
        stats[chat_id]["msg_count"] += 1

        msg_id = event.message.id
        text = event.message.text or ""

        # เก็บ log เพื่อใช้เวลา unsend
        message_log[msg_id] = {
            "type": "text",
            "text": text,
            "user_id": user_id,
            "time": datetime.now(pytz.timezone("Asia/Bangkok"))
        }

        # ----- คำสั่งเกี่ยวกับบิล -----
        # รูปแบบ: "บิล 200" หรือ "บิล:200"
        lowered = text.strip().lower()
        if lowered.startswith("บิล"):
            # พยายามดึงจำนวน
            # split by space or colon
            parts = text.replace(":", " ").split()
            if len(parts) >= 2:
                try:
                    amount = int(parts[1])
                    stats[chat_id]["bill_amount"] += amount
                    reply = f"✅ บันทึกบิล {amount} บาทแล้ว\nยอดรวมตอนนี้: {stats[chat_id]['bill_amount']} บาท"
                except ValueError:
                    reply = "❌ รูปแบบบิลไม่ถูก (ตัวอย่าง: บิล 200)"
            else:
                reply = "❌ รูปแบบบิลไม่ถูก (ตัวอย่าง: บิล 200)"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

        # ----- คำสั่งสรุปบิล -----
        if lowered == "สรุปบิล":
            total = stats[chat_id].get("bill_amount", 0)
            reply = f"📊 สรุปยอดบิลทั้งหมด\nรวม: {total} บาท"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

        # ----- คำสั่งสรุปสถิติ (optional) -----
        if lowered == "สรุปสถิติ":
            s = stats[chat_id]
            reply = (
                f"📋 สถิติแชท\n"
                f"• ข้อความทั้งหมด: {s['msg_count']} รายการ\n"
                f"• ภาพทั้งหมด: {s['img_count']} รายการ\n"
                f"• ข้อความที่ถูกลบ: {s['deleted_text']} รายการ\n"
                f"• ภาพที่ถูกลบ: {s['deleted_img']} รายการ\n"
                f"• ยอดบิลรวม: {s['bill_amount']} บาท"
            )
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

        # ----- default auto-reply (แสดงลำดับ) -----
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ข้อความที่ {stats[chat_id]['msg_count']} ✅"))

    except Exception as e:
        print("Error in handle_text:", e)


# ======= รับภาพ (Image) =======
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        user_id = event.source.user_id
        chat_id = getattr(event.source, "group_id", None) or getattr(event.source, "room_id", None) or user_id

        ensure_stats(chat_id)
        stats[chat_id]["img_count"] += 1

        msg_id = event.message.id

        # เก็บเป็น "<image>" แทนเนื้อหา
        message_log[msg_id] = {
            "type": "image",
            "text": "<image>",
            "user_id": user_id,
            "time": datetime.now(pytz.timezone("Asia/Bangkok"))
        }

        # ไม่ตอบกลับทันที (ลดการรบกวน)
        # ถ้าต้องการตอบกลับแสดง thumbnail/ข้อความ ให้เพิ่มที่นี่

    except Exception as e:
        print("Error in handle_image:", e)


# ======= เมื่อมีการยกเลิก (Unsend) =======
@handler.add(UnsendEvent)
def handle_unsend(event):
    try:
        # message_id ที่ถูกลบ
        msg_id = event.unsend.message_id

        # ข้อมูลแชท (group/room/private)
        source = event.source
        # หา chat id ที่เหมาะสมสำหรับเก็บสถิติและส่งกลับ
        chat_id = getattr(source, "group_id", None) or getattr(source, "room_id", None) or getattr(source, "user_id", None)

        ensure_stats(chat_id)

        # ดึงข้อมูลที่เราบันทึกไว้ (ถ้ามี)
        info = message_log.get(msg_id)

        # ดึงชื่อผู้ส่ง (ถ้าได้)
        user_id = None
        if info and "user_id" in info:
            user_id = info["user_id"]
        else:
            # fallback ไปที่ source.user_id ถ้ามี
            user_id = getattr(source, "user_id", None)

        user_name = "ไม่ทราบชื่อ"
        try:
            if user_id:
                profile = line_bot_api.get_profile(user_id)
                user_name = profile.display_name
        except Exception as e:
            # บางกรณี group/room อาจมีข้อจำกัดเรื่อง profile
            print("Could not get profile:", e)

        # เวลาไทย (เวลาที่ unsend เกิดขึ้น)
        tz = pytz.timezone("Asia/Bangkok")
        time_now = datetime.now(tz).strftime("%d/%m/%Y %H:%M:%S")

        # ตรวจประเภทและอัปเดตสถิติการถูกลบ
        if info is None:
            # ไม่พบข้อมูลเดิม
            deleted_content = "ไม่พบข้อมูลข้อความ"
        else:
            if info.get("type") == "image":
                deleted_content = "ภาพที่ถูกลบ"
                stats[chat_id]["deleted_img"] += 1
            else:
                deleted_content = info.get("text", "ไม่พบข้อมูลข้อความ")
                stats[chat_id]["deleted_text"] += 1

        # เตรียมสรุปยอดจากสถิติปัจจุบัน (ข้อความ/ภาพที่ถูกลบ)
        text_count = stats[chat_id].get("deleted_text", 0)
        image_count = stats[chat_id].get("deleted_img", 0)
        total_deleted = text_count + image_count

        # ฟอร์แมตรายงานตามที่ฟ่างต้องการ
        reply = (
            "[ ข้อความที่ถูกยกเลิก ]\n"
            f"• ผู้ส่ง: {user_name}\n"
            f"• เวลา: {time_now}\n"
            f"• ข้อความ/ภาพ: {deleted_content}\n\n"
            "✨สรุปบิล✨\n"
            f"• ข้อความ: {text_count} รายการ\n"
            f"• ภาพ: {image_count} รายการ\n"
            f"🌷รวมทั้งหมด: {total_deleted} รายการ  📬"
        )

        # ส่งกลับเข้ากลุ่ม / ห้อง / ผู้ใช้ตาม source
        if getattr(source, "group_id", None):
            target = source.group_id
        elif getattr(source, "room_id", None):
            target = source.room_id
        else:
            target = user_id or source.user_id

        # push_message รับ chat id สำหรับกลุ่ม/room/user (line-bot-sdk รองรับ)
        try:
            line_bot_api.push_message(target, TextSendMessage(text=reply))
        except Exception as e:
            print("Error pushing message:", e)

    except Exception as e:
        print("Error in handle_unsend:", e)


# ======= ถ้ารันแบบ local for debug =======
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
