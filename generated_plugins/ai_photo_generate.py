import os
import aiohttp
import ollama  # Библиотека для работы с Ollama
from aiogram import Router, Dispatcher, Bot
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import OLLAMA_MODEL, PLUGINS_DIR # Импорты из вашего конфига

# Конфигурация локального сервера Fooocus
FOOOCUS_BASE_URL = "http://127.0.0.1:7865"
# Используем /run/predict вместо /api/predict для обхода ограничений Gradio
FOOOCUS_API_URL = f"{FOOOCUS_BASE_URL}/run/predict"
TEMP_DIR = "temp_voice"

router = Router()

async def expand_prompt_with_qwen(user_prompt: str) -> str:
    """
    Использует Qwen для перевода и расширения промта до уровня Midjourney/SDXL.
    Если Ollama недоступна, возвращает оригинальный промт.
    """
    system_instruction = (
        "You are an expert prompt engineer for Stable Diffusion XL and Fooocus. "
        "Your task is to take the user's request (which might be in Russian), translate it into English, "
        "and expand it into a detailed, high-quality image prompt. "
        "Add professional descriptive tags (e.g., lighting, cinematic, photorealistic, 8k, detailed). "
        "CRITICAL: Output ONLY the final English prompt text. Do not include any intro, explanations, or markdown blocks."
    )
    
    try:
        # Исправлено: ollama.generate возвращает объект напрямую при использовании await, 
        # обращаться к нему как к генератору не нужно.
        response = await ollama.generate(
            model=OLLAMA_MODEL,
            prompt=f"Expand this image request: {user_prompt}",
            system=system_instruction,
            options={
                "temperature": 0.5,
                "num_predict": 150
            }
        )
        
        # Проверяем, в каком формате вернулся ответ (словарь или объект)
        if isinstance(response, dict):
            expanded_text = response.get('response', '').strip()
        else:
            expanded_text = getattr(response, 'response', '').strip()

        # Чистим артефакты разметки нейросети
        expanded_text = expanded_text.replace("```", "").replace('"', '').strip()
        return expanded_text if expanded_text else user_prompt
    except Exception as e:
        print(f"[Ошибка Ollama/Qwen]: {e}")
        return user_prompt

async def fetch_fooocus_image(english_prompt: str) -> str | None:
    """Асинхронный запрос к API Fooocus для генерации изображения через /run/predict"""
    json_payload = {
        "data": [
            english_prompt,       # Улучшенный промт на английском
            "",                   # Negative Prompt
            ["Fooocus Enhance", "Fooocus Cinematic"], # Стили по умолчанию
            "Speed",              # Performance (Speed/Quality)
            "1024×1024",          # Aspect Ratio
            1,                    # Количество изображений
            "png",                # Формат файла
            -1,                   # Случайный сид
            True,                 # Read Wildcards
            2,                    # Sharpness
            4,                    # Guidance Scale
            False                 # Developer Mode
        ],
        "fn_index": 1             # Индекс главной функции генерации в Fooocus
    }
    
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.post(FOOOCUS_API_URL, json=json_payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"[Ошибка Fooocus] Сервер вернул код {response.status}: {error_text}")
                    return None
                
                result = await response.json()
                
                # Разбор структуры ответа /run/predict
                data_list = result.get("data", [])
                if not data_list or not isinstance(data_list, list):
                    print(f"[Ошибка Fooocus] В ответе пустой 'data': {result}")
                    return None
                
                # В ответе /run/predict под индексом 0 обычно лежит список сгенерированных файлов
                first_element = data_list[0]
                if isinstance(first_element, list) and len(first_element) > 0:
                    file_info = first_element[0]
                else:
                    file_info = first_element
                
                # Забираем имя/путь файла
                if isinstance(file_info, dict) and "name" in file_info:
                    img_url_rel = file_info["name"]
                else:
                    print(f"[Ошибка Fooocus] Неверный формат file_info: {file_info}")
                    return None
                
                # Формируем прямую ссылку для скачивания файла с локального веб-сервера Gradio
                img_download_url = f"{FOOOCUS_BASE_URL}/file={img_url_rel}"
                
                # Создаем временную папку, если её нет
                os.makedirs(TEMP_DIR, exist_ok=True)
                output_path = os.path.join(TEMP_DIR, os.path.basename(img_url_rel))
                
                # Скачиваем готовый файл
                async with session.get(img_download_url) as img_resp:
                    if img_resp.status == 200:
                        with open(output_path, "wb") as f:
                            f.write(await img_resp.read())
                        return output_path
                    else:
                        print(f"[Ошибка скачивания файла] Код: {img_resp.status}")
                        return None
                        
        except Exception as e:
            print(f"[Исключение Fooocus API]: {e}")
            return None

@router.message(Command("generate"))
async def cmd_generate_image(message: Message):
    user_prompt = message.text.replace("/generate", "").strip()
    
    if not user_prompt:
        await message.answer("ℹ️ Отправьте команду вместе с текстом. Пример:\n`/generate капибара в шляпе`", parse_mode="Markdown")
        return

    status_msg = await message.answer("🧠 *Ollama (Qwen) обрабатывает и улучшает ваш запрос...*", parse_mode="Markdown")

    # Перевод и расширение промта с помощью Qwen
    english_prompt = await expand_prompt_with_qwen(user_prompt)
    
    await status_msg.edit_text(f"🎨 *Промт оптимизирован!* Начинаю генерацию в Fooocus...\n\n📋 *En prompt:* `_{english_prompt}_`", parse_mode="Markdown")

    # Генерация в Fooocus по английскому промту
    output_path = await fetch_fooocus_image(english_prompt)

    if output_path and os.path.exists(output_path):
        try:
            await status_msg.edit_text("✨ *Рисунок готов!* Отправляю в чат...")
        except Exception:
            pass
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📢 Опубликовать в канал Sol Chat", callback_data="publish_to_channel")
        builder.adjust(1)
        
        photo_file = FSInputFile(output_path)
        
        await message.reply_photo(
            photo=photo_file,
            caption=f"🤖 **Сгенерировано локально!**\n\n📝 *Ваш запрос:* {user_prompt}\n🚀 *Промт для ИИ:* `{english_prompt}`",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        
        # Удаляем временную копию
        try:
            os.remove(output_path)
        except Exception:
            pass
    else:
        await status_msg.edit_text("❌ *Ошибка генерации.* Проверьте консоль серверов Ollama или Fooocus (ошибка записана в лог бота).")
        
    try:
        await status_msg.delete()
    except Exception:
        pass

# Функция регистрации роутера менеджером плагинов
def register_plugin(dp: Dispatcher, bot: Bot, admin_id: int):
    dp.include_router(router)
