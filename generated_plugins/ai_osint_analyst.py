import os
import base64
import aiohttp
from aiogram import Router, types
from aiogram.filters import Command

router = Router()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_VISION_MODEL = "moondream"  # Ваша легкая модель
TEMP_DIR = "temp_voice"

async def analyze_image_with_ollama(image_path: str, prompt: str) -> str:
    """Кодирует картинку в Base64 без ошибок и отправляет в Ollama Vision"""
    try:
        with open(image_path, "rb") as image_file:
            # Исправлен срез и убран лишний пробел в кодировке utf-8
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
        payload = {
            "model": OLLAMA_VISION_MODEL,
            "prompt": prompt,
            "images": [base64_image],
            "stream": False
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", "")
    except Exception as e:
        return f"Ошибка Ollama Vision: {e}"
    return "Не удалось получить ответ от ИИ."

import subprocess
FFMPEG_PATH = "ffmpeg.exe"  # Путь к вашему рабочему ffmpeg в корне
def extract_frame_from_video(video_path: str, output_path: str) -> bool:
    """Вырезает первый кадр из видео с помощью FFmpeg"""
    try:
        command = [
            FFMPEG_PATH, "-y",
            "-i", video_path,
            "-vframes", "1",
            "-f", "image2",
            output_path
        ]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception as e:
        print(f"Ошибка извлечения кадра через FFmpeg: {e}")
        return False

@router.message(Command("vision"))
async def cmd_vision_analysis(message: types.Message):
    """
    Анализ изображений и видео по команде через REPLY.
    Пример: Ответить на фото/видео командой `/vision какой текст на экране?`
    """
    # Проверяем, что команда отправлена как ОТВЕТ
    if not message.reply_to_message:
        await message.reply("⚠️ Ответьте этой командой на фото или видеоролик!")
        return

    reply = message.reply_to_message
    is_photo = bool(reply.photo)
    is_video = bool(reply.video or reply.document and reply.document.mime_type.startswith("video/"))

    if not is_photo and not is_video:
        await message.reply("⚠️ Команда работает только как ответ на фото или видео!")
        return

    # Вытаскиваем вопрос пользователя
    user_question = message.text[7:].strip()
    if not user_question:
        system_prompt = (
            "Подробно опиши на русском языке, что изображено на этой картинке. "
            "Если на ней есть текст, найди его и переведи на русский."
        )
    else:
        system_prompt = f"Ответь на вопрос по этой картинке строго на русском языке: {user_question}"

    status_msg = await message.reply("🎬 Обрабатываю медиафайл для отправки в moondream...")
    
    os.makedirs(TEMP_DIR, exist_ok=True)
    media_path = os.path.join(TEMP_DIR, f"input_{message.message_id}")
    photo_path = os.path.join(TEMP_DIR, f"vision_{message.message_id}.jpg")
    
    try:
        if is_photo:
            # Если это фото, скачиваем напрямую
            file_info = await message.bot.get_file(reply.photo[-1].file_id)
            await message.bot.download_file(file_info.file_path, photo_path)
        else:
            # Если это видео, скачиваем его и режем первый кадр через ffmpeg
            await status_msg.edit_text("📥 Скачиваю видеоролик...")
            video_file_id = reply.video.file_id if reply.video else reply.document.file_id
            file_info = await message.bot.get_file(video_file_id)
            
            # Сохраняем видео во временный файл
            media_path += ".mp4"
            await message.bot.download_file(file_info.file_path, media_path)
            
            await status_msg.edit_text("🎞️ Вырезаю кадр из видео через FFmpeg...")
            if not extract_frame_from_video(media_path, photo_path):
                await status_msg.edit_text("❌ Не удалось извлечь кадр из видео.")
                return

                await status_msg.edit_text("🧠 Moondream сканирует изображение (Шаг 1/2)...")
        
        # Заставляем Moondream работать на родном английском — так она сделает меньше ошибок
        moondream_prompt = "Describe this image in detail. If it is a code or terminal screenshot, copy as many words, errors, and lines as you can see clearly."
        raw_english_description = await analyze_image_with_ollama(photo_path, moondream_prompt)
        
        if not raw_english_description.strip() or "Ошибка" in raw_english_description:
            await status_msg.edit_text("❌ Moondream не смогла разобрать изображение.")
            return

        await status_msg.edit_text("🤖 qwen2.5:1.5b обрабатывает контекст и переводит (Шаг 2/2)...")
        
        # Формируем промпт для текстовой qwen2.5:1.5b
        qwen_prompt = (
            f"Ты — высококлассный программист и переводчик. Перед тобой сырое, возможно несвязное описание скриншота "
            f"с кодом или интерфейсом, полученное от модели распознавания зрения. Твоя задача — исправить логические ошибки "
            f"в описании, понять, о какой ошибке/коде идет речь, структурировать информацию и выдать красивый, "
            f"понятный и связный ответ на русском языке.\n"
            f"Если пользователь задавал конкретный вопрос: '{user_question if user_question else 'Что на экране?'}' — ответь на него.\n\n"
            f"Сырое описание от Vision-модели:\n{raw_english_description}"
        )
        
        # Отправляем текст в вашу основную текстовую модель (используем url для генерации текста)
        payload = {
            "model": "qwen2.5:1.5b",
            "prompt": qwen_prompt,
            "stream": False
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    ai_response = data.get("response", "Не удалось обработать текст через Qwen.")
                else:
                    ai_response = f"Ошибка Qwen: статус {response.status}"

        await status_msg.edit_text(f"🎯 **Результат ИИ-анализа (Moondream + Qwen):**\n\n{ai_response}")

        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка анализа медиафайла: {e}")
    finally:
        # Очистка диска
        for path in [media_path, media_path + ".mp4", photo_path]:
            if os.path.exists(path):
                try: os.remove(path)
                except: pass

def register_plugin(dp, *args, **kwargs):
    dp.include_router(router)
