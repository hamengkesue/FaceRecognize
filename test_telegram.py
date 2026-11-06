"""
Utility script to verify Telegram Bot API connectivity and photo delivery.
"""

import sys
from datetime import datetime
import numpy as np
import cv2
import requests

from src.config import Config

def test_telegram_alert():
    print("=" * 60)
    print("      UJI COBA INTEGRASI TELEGRAM BOT ALERT      ")
    print("=" * 60)

    token = Config.TELEGRAM_BOT_TOKEN
    chat_id = Config.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        print("[ERROR] Token Telegram belum dikonfigurasi di file .env!")
        print("  - Pastikan TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID telah diisi.")
        print("  - Dapatkan token dari @BotFather dan ID Anda dari @userinfobot.")
        return False

    print(f"Token: {token[:8]}...{token[-4:] if len(token) > 12 else ''}")
    print(f"Chat ID: {chat_id}")
    print("\n[1/2] Memeriksa validitas bot token ke server Telegram...")

    try:
        me_resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
        if me_resp.status_code == 200:
            bot_info = me_resp.json().get("result", {})
            print(f"  -> Bot Terverifikasi: @{bot_info.get('username')} ({bot_info.get('first_name')})")
        else:
            print(f"  [GAGAL] Token bot tidak valid: {me_resp.text}")
            return False
    except Exception as e:
        print(f"  [GAGAL] Tidak dapat menghubungi server Telegram: {e}")
        return False

    print("\n[2/2] Mengirim foto uji coba simulasi penyusup ke chat Anda...")

    # Generate a dummy test image
    test_img = np.zeros((480, 640, 3), dtype=np.uint8)
    # Dark slate background
    test_img[:] = (35, 30, 30)
    # Draw green border and title
    cv2.rectangle(test_img, (40, 40), (600, 440), (46, 204, 113), 3)
    cv2.putText(test_img, "TEST ALERT - LAPTOP FACE GUARD", (60, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (46, 204, 113), 2)
    cv2.putText(test_img, f"Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", (60, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.putText(test_img, "Integrasi notifikasi Telegram berhasil 100%!", (60, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    _, img_encoded = cv2.imencode(".jpg", test_img)
    img_bytes = img_encoded.tobytes()

    caption = (
        "✅ *UJI COBA NOTIFIKASI TELEGRAM BERHASIL*\n\n"
        "Sistem *Personal Laptop Face Guard* Anda telah berhasil terhubung dengan bot ini.\n"
        f"🕒 *Waktu Uji:* `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
        "🔒 Jika ada orang lain yang menyentuh laptop Anda, foto bukti akan mendarat di chat ini secara otomatis."
    )

    try:
        send_resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "Markdown"
            },
            files={"photo": ("test_alert.jpg", img_bytes, "image/jpeg")},
            timeout=10
        )
        if send_resp.status_code == 200:
            print("  -> PESAN DAN FOTO BERHASIL TERKIRIM KE TELEGRAM ANDA!")
            print("  -> Silakan periksa aplikasi Telegram di ponsel Anda sekarang.")
            return True
        else:
            print(f"  [GAGAL] Pengiriman ditolak oleh Telegram ({send_resp.status_code}): {send_resp.text}")
            return False
    except Exception as e:
        print(f"  [GAGAL] Kesalahan saat mengirim ke Telegram: {e}")
        return False

if __name__ == "__main__":
    test_telegram_alert()

