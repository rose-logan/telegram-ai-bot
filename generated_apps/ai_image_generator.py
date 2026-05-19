import os
import random
import asyncio
import aiohttp
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from urllib.parse import quote  # Используем стандартный модуль Python вместо aiohttp.helpers

router = Router()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:1.5b"

# Адрес вашего локально запущенного Stable Diffusion (Fooocus)
# Если используете AUTOMATIC1111, смените порт на 7860
SD_API_URL = "http://127.0.0" 
TEMP_DIR = "temp_voice"

async def translate_prompt_via_qwen(russian_prompt: str) -> str:
    """Просит qwen2.5:1.5b перевести промпт на английский для Stable Diffusion"""
    prompt = (
        f"Ты — профессиональный переводчик промптов для Stable Diffusion XL. "
        f"Переведи следующее описание на английский язык. Добавь через запятую несколько качественных "
        f"деталей (например: cinematic, photorealistic, 8k, highly detailed). "
        f"Ответь СТРОГО только итоговым текстом на английском языке, без кавычек и пояснений.\n\n"
        f"Описание: {russian_prompt}"
    )
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", "").strip().replace('"', '').replace("'", "")
    except Exception as e:
        print(f"Ошибка перевода промпта: {e}")
    return russian_prompt


@router.message(Command("generate"))
async def cmd_generate_image(message: types.Message):
    """
    Локальная генерация картинки через Stable Diffusion (Fooocus) с автопереводом.
    """
    user_prompt = message.text[9:].strip() if message.text.startswith("/generate ") else message.text[10:].strip()
    
    if not user_prompt:
        await message.reply("⚠️ Укажите описание картинки после команды!\nПример: `/generate космонавт на луне`")
        return

    status_msg = await message.reply("🧠 qwen2.5:1.5b переводит и адаптирует промпт...")
    english_prompt = await translate_prompt_via_qwen(user_prompt)
    
    await status_msg.edit_text(f"🎨 Локальный Stable Diffusion (Fooocus) генерирует изображение на GTX 1080 Ti...\n📋 *Промпт:* `{english_prompt}`", parse_mode="Markdown")

    os.makedirs(TEMP_DIR, exist_ok=True)
    output_path = os.path.join(TEMP_DIR, f"sd_{message.message_id}.png")

    # API-запрос, полностью соответствующий актуальной структуре Gradio / Fooocus API
    payload = {
        "data": [
            english_prompt,                                      # Позитивный промпт
            "bad quality, blurry, low resolution, distorted",    # Негативный промпт
            "Fooocus V2",                                        # Стиль по умолчанию
            "Speed",                                             # Режим скорости (Speed / Quality / Extreme)
            "1024×1024",                                         # Разрешение (Идеально для SDXL)
            1,                                                   # Количество изображений
            random.randint(1, 9999999)                           # Случайный сид (seed)
        ]
    }

    try:
        # Увеличиваем таймаут до 120 секунд, так как в самый первый раз Fooocus может генерировать чуть дольше
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            async with session.post(SD_API_URL, json=payload) as response:
                if response.status != 200:
                    await status_msg.edit_text(f"❌ Ошибка локального SD сервера. Проверьте, завершился ли запуск в консоли Fooocus. Статус: {response.status}")
                    return
                
                result = await response.json()
                
                # Достаем ссылку на сгенерированное изображение из ответа Gradio API
                # Структура ответа содержит массив данных, где в "data" лежит информация о файле
                file_info = result["data"][0][0]  
                img_url_rel = file_info["name"]
                img_download_url = f"http://127.0.0{img_url_rel}"
                
                # Скачиваем полученную картинку во временную папку бота
                async with session.get(img_download_url) as img_resp:
                    if img_resp.status == 200:
                        with open(output_path, "wb") as f:
                            f.write(await img_resp.read())

        if os.path.exists(output_path):
            await status_msg.edit_text("✨ Рисунок готов! Отправляю...")
            photo_file = FSInputFile(output_path)
            
            builder = InlineKeyboardBuilder()
            builder.button(text="📢 Опубликовать в канал Sol Chat", callback_data="post_to_channel_action")
            builder.adjust(1)
            
            await message.reply_photo(
                photo=photo_file, 
                caption=f"🎨 **Сгенерировано локально:**\n_{user_prompt}_\n\n🤖 *Промпт для SD:* `{english_prompt}`",
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
            await status_msg.delete()
        else:
            await status_msg.edit_text("❌ Файл изображения не был сохранен.")

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка генерации: {e}\nУбедитесь, что run.bat в папке Fooocus запущен и открылся в браузере.")
    finally:
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except: pass

def register_plugin(dp, *args, **kwargs):
    dp.include_router(router)