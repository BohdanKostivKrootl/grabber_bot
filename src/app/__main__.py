import os
import yt_dlp
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Your BotFather token
TELEGRAM_TOKEN = "8305754426:AAFiKu9EwWXPKMyHrfDcNmxbBOsRlQwIReU"
GROUP_CHAT_ID = -1002331394665
COUNTER = 0

# List of supported sites
SUPPORTED_SITES = [
    "tiktok.com", 
    "instagram.com", 
    "youtube.com/shorts", 
    "youtube.com/watch", 
    "youtu.be"
]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global COUNTER

    if not update.message or not update.message.text:
        return None

    if (
        update.message.chat_id == GROUP_CHAT_ID
        and update.message
        and update.message.text
        and any(site in update.message.text for site in SUPPORTED_SITES)
    ):
        COUNTER += 1
        print("COUNTER", COUNTER)
        if COUNTER == 5:
            COUNTER = 0
            await update.message.reply_photo("src/app/ad.jpg", caption="🚀 Реклама для Тараса!")
            print("HERE COMES AD!!!")

    text = update.message.text

    # 1️⃣ Skip Instagram stories
    if "instagram.com/stories" in text:
        await update.message.reply_text("⚠️ Instagram stories are not supported.")
        return

    if any(site in text for site in SUPPORTED_SITES):
        # Send temporary "Downloading..." message
        waiting_msg = await update.message.reply_text("⏳ Downloading...")

        ydl_opts = {
            "format": "best[ext=mp4][height<=720]/mp4",
            "outtmpl": "video.%(ext)s",
            "cookies": "cookies.txt",
            "merge_output_format": "mp4",
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",  # ensures final mp4 container
                },
                {
                    "key": "FFmpegMetadata",  # injects proper metadata
                },
            ],
        }


        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # First extract info (without download) to check duration
                info = ydl.extract_info(text, download=False)

                # 2️⃣ YouTube duration check (< 300 seconds)
                if ("youtube.com" in text or "youtu.be" in text) and info.get("duration", 0) > 300: # type: ignore
                    await waiting_msg.delete()
                    await update.message.reply_text("⚠️ Only YouTube videos shorter than 5 minutes are supported.")
                    return

                # Now download
                info = ydl.extract_info(text, download=True)
                filename = ydl.prepare_filename(info)

            # Send video
            with open(filename, "rb") as f:
                await update.message.reply_video(f)

            os.remove(filename)

            # Delete the "Downloading..." message
            await waiting_msg.delete()

        except Exception as e:
            # Delete "Downloading..." message and send error notice
            await waiting_msg.delete()
            await update.message.reply_text("❌ Oops, error occurred 😬")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    print("Bot started!")
    main()
