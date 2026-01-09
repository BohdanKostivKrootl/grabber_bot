import asyncio
import glob
import os
import random
import re
import shutil
from typing import List, Tuple
import httpx
import yt_dlp
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Your BotFather token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "your_token")
PC_TYPE = os.getenv("PC_TYPE", "server")
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

async def gallery_dl_download_media(url: str, base_dir: str = "downloads/photos") -> Tuple[List[str], List[str], str]:
    """
    Uses gallery-dl to download media (TikTok, Instagram, etc.) into base_dir/<site>/<unique_folder>.
    Returns (image_paths, audio_paths, post_dir).
    """
    os.makedirs(base_dir, exist_ok=True)

    # Detect site type (e.g. 'tiktok' or 'instagram')
    if "tiktok.com" in url:
        site_dir = os.path.join(base_dir, "tiktok")
    elif "instagram.com" in url:
        site_dir = os.path.join(base_dir, "instagram")
    else:
        site_dir = base_dir  # fallback

    os.makedirs(site_dir, exist_ok=True)
    before = set(os.listdir(site_dir))

    # Build base command
    cmd = ["gallery-dl", "-d", base_dir]

    # Add cookies depending on PC_TYPE
    if PC_TYPE == "server":
        cmd += ["--cookies-from-browser", "firefox"]
    elif PC_TYPE == "desktop":
        cmd += ["--cookies-from-browser", "vivaldi"]

    cmd.append(url)

    # Run gallery-dl command
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        print("❌ gallery-dl failed:", stderr.decode())
        return [], [], ""

    # Detect new folder created
    after = set(os.listdir(site_dir))
    new_folders = list(after - before)
    if not new_folders:
        print(f"❌ No new folder found in {site_dir}")
        return [], [], ""

    post_dir = os.path.join(site_dir, new_folders[0])

    # Collect files
    all_files = [p for p in glob.glob(os.path.join(post_dir, "*.*")) if os.path.isfile(p)]
    img_exts = (".jpg", ".jpeg", ".png", ".webp")
    audio_exts = (".mp3", ".m4a", ".aac", ".wav", ".ogg")

    images = [p for p in all_files if p.lower().endswith(img_exts)]
    audios = [p for p in all_files if p.lower().endswith(audio_exts)]

    # Sort by modification time
    images.sort(key=os.path.getmtime)
    audios.sort(key=os.path.getmtime)

    return images, audios, post_dir

async def expand_url(url: str) -> str:
    """Follow redirects and return the final expanded URL."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            # HEAD is faster, but some servers (like TikTok) reject it, so fallback to GET
            try:
                response = await client.head(url)
            except httpx.HTTPStatusError:
                response = await client.get(url)
            return str(response.url)
    except Exception as e:
        print(f"❌ Failed to expand URL: {e}")
        return url  # fallback to original if anything fails

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global COUNTER

    if not update.message or not update.message.text:
        return None

    # Group ad logic
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
            
            # Randomly choose between the two ads
            ad_choice = random.choice([
                ("src/app/taras_ad.jpg", "🚀 Реклама для Тараса!"),
                ("src/app/katya_ad.jpg", "🌠 Реклама для Каті!")
            ])
            
            await update.message.reply_photo(ad_choice[0], caption=ad_choice[1])
            print(f"HERE COMES AD!!! ({ad_choice[0]})")

    text: str = update.message.text
    match = re.search(r"(https?://[^\s]+)", text)
    if match:
        text = match.group(1)
    else:
        return None

    # Skip Instagram stories
    if "instagram.com/stories" in text:
        await update.message.reply_text("⚠️ Instagram stories are not supported.")
        return

    if any(site in text for site in SUPPORTED_SITES):
        # Send temporary "Downloading..." message
        waiting_msg = await update.message.reply_text("⏳ Downloading...")

        expanded_url = await expand_url(text)
        # Handle photos
        if "tiktok.com" in expanded_url or "instagram.com" in expanded_url:
            try:
                images, audios, post_dir = await gallery_dl_download_media(expanded_url)

                if images:
                    if len(images) == 1:
                        image_path = images[0]

                        # ✅ If audio exists — combine into video using ffmpeg
                        if audios:
                            audio_path = audios[0]
                            output_video = os.path.splitext(image_path)[0] + "_with_audio.mp4"

                            # ffmpeg command to create video from single image + audio
                            cmd = [
                                "ffmpeg", "-y",
                                "-loop", "1",                # loop image
                                "-i", image_path,
                                "-i", audio_path,
                                "-c:v", "libx264",
                                "-c:a", "aac",
                                "-b:a", "192k",
                                "-shortest",                 # stop when audio ends
                                "-pix_fmt", "yuv420p",
                                output_video
                            ]

                            proc = await asyncio.create_subprocess_exec(
                                *cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            await proc.communicate()

                            # Send generated video
                            with open(output_video, "rb") as video_file:
                                await update.message.reply_video(video_file)

                            # Cleanup files and folder
                            os.remove(output_video)
                            if post_dir and os.path.exists(post_dir):
                                shutil.rmtree(post_dir, ignore_errors=True)
                            await waiting_msg.delete()
                            return None

                        else:
                            # No audio, send image as usual
                            with open(image_path, "rb") as img_file:
                                await update.message.reply_photo(img_file)
                            if post_dir and os.path.exists(post_dir):
                                shutil.rmtree(post_dir, ignore_errors=True)
                            await waiting_msg.delete()
                            return None
                    else:
                        # Send multiple images as a media group (Telegram allows up to 10 per group)
                        from telegram import InputMediaPhoto

                        media_group = []
                        for img_path in images:
                            media_group.append(InputMediaPhoto(open(img_path, "rb")))

                        await update.message.reply_media_group(media_group)
                        if post_dir and os.path.exists(post_dir):
                            shutil.rmtree(post_dir, ignore_errors=True)
                        await waiting_msg.delete()
                        return None
                elif audios:
                    await update.message.reply_text("🎵 Audio found, but no images — skipping upload.")
                    await waiting_msg.delete()
                    return None

            except Exception as e:
                print("⚠️ gallery-dl failed:", e)

        # ✅ Create downloads folder if missing
        os.makedirs("downloads", exist_ok=True)

        # ✅ Unique filename per download
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        ydl_opts = {
            "format": "best[ext=mp4][height<=720]/mp4",
            "outtmpl": f"downloads/%(id)s_{timestamp}.%(ext)s",
            "merge_output_format": "mp4",
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
                {"key": "FFmpegMetadata"},
            ],
        }

        # due to different cookies requirements on the linux server
        if PC_TYPE == "desktop":
            ydl_opts.update({"cookies": "cookies.txt"})
        elif PC_TYPE == "server":
            ydl_opts.update({"cookiesfrombrowser": ("firefox",)})

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
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
            print("❌ Error:", e)
            await waiting_msg.delete()
            await update.message.reply_text("❌ Oops, error occurred 😬")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).connect_timeout(60).read_timeout(180).write_timeout(180).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    print("Bot started!")
    main()
