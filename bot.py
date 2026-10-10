import os
import logging
from io import BytesIO

import requests
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]  # set this in Replit Secrets, never hardcode it

# per-user state: what action they picked from the menu
user_mode: dict[int, str] = {}

MAIN_MENU = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("✍️ Исправить текст", callback_data="fix")],
        [InlineKeyboardButton("🎥 Скачать TikTok", callback_data="tiktok")],
        [InlineKeyboardButton("🖼 Коллаж из историй", callback_data="collage")],
    ]
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_mode[update.effective_user.id] = ""
    await update.message.reply_text("Привет! Выбери, что нужно сделать:", reply_markup=MAIN_MENU)


async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user_mode[uid] = query.data

    prompts = {
        "fix": "Пришли текст — исправлю ошибки.",
        "tiktok": "Пришли ссылку на видео в TikTok.",
        "collage": "Пришли фото — разобью на 3 части для историй.",
    }
    await query.message.reply_text(prompts[query.data])


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    mode = user_mode.get(uid, "")
    text = update.message.text

    if mode == "tiktok":
        await handle_tiktok(update, text)
    elif mode == "fix":
        await handle_fix(update, text)
    else:
        await update.message.reply_text("Сначала выбери действие: /start")


async def handle_fix(update: Update, text: str):
    await update.message.chat.send_action("typing")
    try:
        r = requests.post(
            "https://api.languagetool.org/v2/check",
            data={"text": text, "language": "ru"},
            timeout=15,
        )
        matches = r.json().get("matches", [])
        if not matches:
            await update.message.reply_text("Ошибок не нашёл 👍")
            return

        fixed = text
        for m in sorted(matches, key=lambda m: m["offset"], reverse=True):
            if m["replacements"]:
                repl = m["replacements"][0]["value"]
                s, length = m["offset"], m["length"]
                fixed = fixed[:s] + repl + fixed[s + length :]

        await update.message.reply_text(f"Исправленный текст:\n\n{fixed}")
    except Exception:
        await update.message.reply_text("Не получилось проверить текст, попробуй ещё раз.")


async def handle_tiktok(update: Update, url: str):
    await update.message.chat.send_action("upload_video")
    try:
        r = requests.get("https://www.tikwm.com/api/", params={"url": url}, timeout=20)
        data = r.json()["data"]
        await update.message.reply_video(data["play"], caption="Готово, без водяного знака ✅")
    except Exception:
        await update.message.reply_text("Не получилось скачать это видео, проверь ссылку.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if user_mode.get(uid) != "collage":
        return

    await update.message.chat.send_action("upload_photo")
    photo = update.message.photo[-1]
    file = await photo.get_file()
    buf = BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)
    img = Image.open(buf).convert("RGB")

    parts = 3
    w, h = img.size
    piece_w = w // parts
    for i in range(parts):
        left = i * piece_w
        right = w if i == parts - 1 else (i + 1) * piece_w
        piece = img.crop((left, 0, right, h))
        out = BytesIO()
        piece.save(out, format="JPEG", quality=95)
        out.seek(0)
        out.name = f"part_{i + 1}.jpg"
        await update.message.reply_photo(out, caption=f"Часть {i + 1} из {parts} — выкладывай по порядку")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()


if __name__ == "__main__":
    main()
