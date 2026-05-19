import os
import base64
import requests
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
import asyncio

class AnalyzerStates(StatesGroup):
    wait_photo = State()

plugin_router = Router()

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Функция перевода картинки в формат Base64, который понимает Ollama Vision
def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

@plugin_router.message(Command("analyze"))
async def cmd_analyze_start(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
    await message.answer("👁 Отправьте мне любую фотографию, и я подробно опишу, что на ней изображено:")
    await state.set_state(AnalyzerStates.wait_photo)

@plugin_router.message(AnalyzerStates.wait_photo, F.photo)
async def process_photo_analysis(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    status = await message.answer("📥 Загружаю фото и передаю в Ollama Vision...")
    
    # Скачиваем фото на сервер
    file_id = message.photo[-1].file_id
    file = await bot.get_file(file_id)
    file_path = os.path.join(DOWNLOAD_DIR, f"analyze_{message.message_id}.jpg")
    await bot.download_file(file.file_path, file_path)
    
    try:
        # 1. Кодируем картинку
        base64_image = encode_image_to_base64(file_path)
        
        await status.edit_text("🤖 Локальный ИИ (Llava) внимательно изучает изображение...")
        
        # Запрос к Llava Vision
        ollama_url = "http://localhost:11434/api/generate"
        payload = {
            "model": "moondream",
            "prompt": "Describe this image in detail. What objects, people, colors, and background do you see?",
            "images": [base64_image],
            "stream": False
        }
        
        response = requests.post(ollama_url, json=payload, timeout=60)
        result = response.json()
        raw_description = result.get("response", "")
        
        if not raw_description:
            return await status.edit_text("❌ Модель не смогла проанализировать снимок.")
            
        await status.edit_text("✍️ Ollama (Qwen) переводит и красиво оформляет отчет...")
        
        # 2. Отправляем английский разбор в твою Qwen для идеального русского перевода
        translation_prompt = (
            f"Переведи этот анализ изображения на красивый, чистый русский язык. "
            f"Сделай текст структурированным и приятным для чтения. Вот анализ: {raw_description}"
        )
        from ai_handler import ask_local_ai
        # Вызываем твою синхронную функцию из ai_handler (без await)
                # Оборачиваем синхронную функцию в асинхронный фоновый поток, чтобы бот не зависал
        final_russian_text = await asyncio.to_thread(ask_local_ai, translation_prompt)

        
        # Отправляем идеальный результат в Telegram
        await status.edit_text(f"📊 **Результат анализа Ollama Vision:**\n\n{final_russian_text}")
        
    except Exception as e:
        await status.edit_text(f"💥 Ошибка при анализе ИИ: {str(e)}")

        
    finally:
        # Всегда удаляем временное фото, чтобы не забивать диск
        if os.path.exists(file_path):
            os.remove(file_path)

def register_plugin(main_plugins_router: Router, bot: Bot, admin_id: int):
    main_plugins_router.include_router(plugin_router)
