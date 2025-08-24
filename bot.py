import os, asyncio, tempfile, subprocess, shlex, re
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = os.getenv("8229961911:AAFbSsmCRVHfSW_7918Em4TANakcirORz_0")  # your token comes from BotFather
OUTPUT_EXT = ".mp4"

FFMPEG_COMMON = (
    "-map 0:v:0 "
    "-c:v libx265 "
    "-pix_fmt yuv420p10le "
    "-preset medium "
    "-crf 24 "
    "-x265-params profile=main10:level-idc=4.0 "
    "-map 0:a? -c:a aac -b:a 128k "
    "-map 0:s? -c:s copy "
    "-movflags +faststart "
    "-map_metadata 0 "
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me a video and I’ll compress it with x265 10-bit (CRF 24).")

def _safe_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._- ")[:120]

async def run_ffmpeg(cmd: str, duration: float, status_msg):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    progress_pat = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
    last_percent = -1
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode(errors="ignore")
        m = progress_pat.search(text)
        if m:
            h, m_, s = map(float, m.groups())
            seconds = h * 3600 + m_ * 60 + s
            if duration > 0:
                percent = int((seconds / duration) * 100)
                if percent != last_percent and percent % 10 == 0:  # update every 10%
                    last_percent = percent
                    try:
                        await status_msg.edit_text(f"🎛️ Compressing… {percent}%")
                    except:
                        pass
    return await proc.wait()

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    file_obj = msg.video or msg.document
    if not file_obj:
        await msg.reply_text("Send a video file.")
        return

    with tempfile.TemporaryDirectory() as td:
        in_path = os.path.join(td, _safe_name(file_obj.file_name or "input.mp4"))
        out_path = os.path.join(td, "compressed" + OUTPUT_EXT)

        status = await msg.reply_text("⬇️ Downloading…")
        tg_file = await file_obj.get_file()
        await tg_file.download_to_drive(in_path)

        # Get duration
        probe_cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {shlex.quote(in_path)}'
        proc = await asyncio.create_subprocess_shell(probe_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        dur_out, _ = await proc.communicate()
        try:
            duration = float(dur_out.decode().strip())
        except:
            duration = 0

        await status.edit_text("🎛️ Starting compression…")
        cmd = f'ffmpeg -y -hide_banner -i {shlex.quote(in_path)} {FFMPEG_COMMON} {shlex.quote(out_path)}'
        rc = await run_ffmpeg(cmd, duration, status)

        if rc != 0 or not os.path.exists(out_path):
            await status.edit_text("❌ Compression failed.")
            return

        await status.edit_text("⬆️ Uploading…")
        await msg.reply_document(document=open(out_path, "rb"), caption="Compressed ✅ (x265 Main10 CRF24)")
        await status.delete()

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    print("Bot is running...")
    app.run_polling()

if name == "main":
    main()
