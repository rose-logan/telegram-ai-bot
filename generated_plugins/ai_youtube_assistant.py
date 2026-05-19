import os
import asyncio
from aiogram import Router, types
from aiogram.filters import Command
import yt_dlp

# Импортируем вашу готовую рабочую функцию из ai_handler
from ai_handler import transcribe_voice_to_text

router = Router()

TEMP_DIR = "temp_voice"
FFMPEG_PATH = "ffmpeg.exe"  # Убедитесь, что лежит в корне рядом с main.py

def download_audio_from_url(url: str, output_path: str) -> bool:
    """Скачивает аудиодорожку из видео, используя FFmpeg из папки temp_voice"""
    # Получаем абсолютный путь к папке temp_voice, где лежат рабочие ffmpeg и ffprobe
    temp_voice_dir = os.path.abspath("temp_voice")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f"{output_path}.%(ext)s",
        'quiet': True,
        'no_warnings': True,
        # Указываем точный путь к папке temp_voice, где yt-dlp найдет оба файла
        'ffmpeg_location': temp_voice_dir, 
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"Ошибка скачивания через yt-dlp: {e}")
        return False



@router.message(Command("youtube"))
async def cmd_youtube_summary(message: types.Message):
    """
    Обработка видео по команде. 
    Пример: /youtube https://youtu.be
    """
    # Вытаскиваем ссылку из команды
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("⚠️ Укажите ссылку на видеоролик после команды!\nПример: `/youtube https://youtu.be...`")
        return

    url = args[1].strip()
    status_msg = await message.reply("📥 Начинаю скачивание аудиодорожки из видео через yt-dlp...")

    # Создаем папку для временных файлов, если её нет
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    base_audio_path = os.path.join(TEMP_DIR, f"yt_{message.message_id}")
    real_mp3_path = f"{base_audio_path}.mp3"

    try:
        # Скачиваем аудио в отдельном потоке, чтобы бот не завис
        success = await asyncio.to_thread(download_audio_from_url, url, base_audio_path)
        
        if not success or not os.path.exists(real_mp3_path):
            await status_msg.edit_text("❌ Не удалось извлечь аудиодорожку из этой ссылки. Проверьте её корректность.")
            return

        await status_msg.edit_text("🎙️ Аудио успешно скачано. Передаю в Whisper и Ollama для анализа...")

        # Вызываем вашу оригинальную функцию, которая сама сделает транскрибацию и ИИ-пост
        ai_response = await asyncio.to_thread(transcribe_voice_to_text, real_mp3_path)

        if not ai_response or "Не удалось" in ai_response:
            await status_msg.edit_text("❌ Ошибка при обработке аудио нейросетью.")
            return

        # Отправляем вам готовый сгенерированный пост
                # Импортируем сборщик клавиатур
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📢 Опубликовать в канал Sol Chat", callback_data="post_to_channel_action")
        
        # Отправляем вам готовый сгенерированный пост С КНОПКОЙ
        await status_msg.edit_text(
            text=f"🎯 **Результат анализа видеоролика:**\n\n{ai_response}",
            reply_markup=builder.as_markup() # Привязываем кнопку
        )


    except Exception as e:
        await status_msg.edit_text(f"❌ Произошла ошибка в плагине: {e}")
        
    finally:
        # Обязательно удаляем временный mp3 файл, чтобы не забивать диск
        if os.path.exists(real_mp3_path):
            try:
                os.remove(real_mp3_path)
            except Exception:
                pass

# Функция регистрации для вашей динамической системы
def register_plugin(dp, *args, **kwargs):
    dp.include_router(router)
