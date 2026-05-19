import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import Command

# Импортируем функцию получения клиента из вашего client_manager.py
from client_manager import get_current_client 

router = Router()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:1.5b" 

async def ask_ollama(prompt: str) -> str:
    """Отправляет запрос в локальную Ollama к модели qwen2.5:1.5b"""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", "")
    except Exception as e:
        return f"Ошибка работы Ollama: {e}"
    return "Не удалось получить ответ от ИИ."


@router.message(Command("search"))
async def cmd_channel_ai_search(message: types.Message):
    """
    Поиск информации внутри конкретного канала с ИИ-выжимкой от qwen2.5:1.5b
    Пример: /search @durov линзы
    """
    # Разбиваем аргументы команды
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.reply(
            "⚠️ Неверный формат!\n"
            "Используйте: `/search [ссылка/юзернейм_канала] [ваш запрос]`\n\n"
            "Пример: `/search @cyberpunk_news лаги`"
        )
        return

    channel_target = args[1]
    query = args[2]

    status_msg = await message.reply(f"📡 Юзербот подключается к каналу {channel_target}...")

    try:
        telethon_client = get_current_client()
        if not telethon_client:
            await status_msg.edit_text("❌ Нет активного аккаунта юзербота. Авторизуйтесь.")
            return

        if not telethon_client.is_connected():
            await telethon_client.connect()

        # Ищем посты по ключевому слову конкретно внутри заданного канала
        raw_posts = []
        async for msg in telethon_client.iter_messages(channel_target, search=query, limit=10):
            if msg.message:
                link = f"https://t.me{channel_target.replace('@', '')}/{msg.id}" if '@' in channel_target else "Ссылка приватного канала"
                clean_text = msg.message.replace('\n', ' ')[:250]
                raw_posts.append(f"🔗 Пост: {link}\nТекст: {clean_text}...")

        if not raw_posts:
            await status_msg.edit_text(f"❌ В канале {channel_target} ничего не найдено по запросу «{query}».")
            return

        await status_msg.edit_text(f"🧠 Найдено постов: {len(raw_posts)}. Модель {OLLAMA_MODEL} анализирует данные...")

        # Формируем промпт для нейросети
        all_found_text = "\n\n---\n\n".join(raw_posts)
        prompt = (
            f"Ты — полезный ИИ-ассистент. Отвечай строго на русском языке.\n"
            f"Пользователь ищет информацию по запросу: '{query}' внутри конкретного канала.\n"
            f"Проанализируй следующие найденные посты, убери мусор и сформируй краткий структурированный ответ.\n\n"
            f"Найденные сообщения:\n\n{all_found_text}"
        )

        ai_analysis = await ask_ollama(prompt)
        await status_msg.edit_text(f"🎯 **Результаты анализа канала {channel_target}:**\n\n{ai_analysis}", disable_web_page_preview=True)

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка при поиске в канале: {e}")

def register_plugin(dp, *args, **kwargs):
    dp.include_router(router)
