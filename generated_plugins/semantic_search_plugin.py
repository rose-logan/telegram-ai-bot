import os
import json
import math
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import ContentType

# Импортируйте вашу функцию получения коннекта к БД
# from database import get_db_connection 
import sqlite3

router = Router()

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
DB_PATH = "semantic_search.db" # Путь к вашей БД из корня

# --- МАТЕМАТИЧЕСКИЕ ФУНКЦИИ ДЛЯ СЕМАНТИЧЕСКОГО СРАВНЕНИЯ ---

def cosine_similarity(v1, v2):
    """Вычисляет косинусное сходство между двумя векторами"""
    dot_product = sum(x * y for x, y in zip(v1, v2))
    magnitude1 = math.sqrt(sum(x * x for x in v1))
    magnitude2 = math.sqrt(sum(x * x for x in v2))
    if not magnitude1 or not magnitude2:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)

async def get_embedding(text: str) -> list:
    """Запрашивает вектор (эмбеддинг) текста у локальной Ollama"""
    payload = {
        "model": EMBED_MODEL,
        "prompt": text
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_EMBED_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("embedding", [])
    except Exception as e:
        print(f"Ошибка получения эмбеддинга: {e}")
    return []

# --- ХЭНДЛЕРЫ АЙОГРАМА ---

@router.message(F.content_type == ContentType.TEXT, ~F.text.startswith("/"))
async def handle_incoming_channel_posts(message: types.Message):
    """
    Хэндлер-перехватчик. Если юзербот пересылает посты в чат управления,
    мы их автоматически векторизуем и сохраняем в базу.
    """
    # Если у вас есть проверка, что сообщение пришло именно от юзербота/из каналов, добавьте её сюда
    text_to_index = message.text
    if len(text_to_index.strip()) < 10: 
        return # Игнорируем слишком короткие сообщения

    # Получаем вектор для пришедшего поста
    embedding = await get_embedding(text_to_index)
    if not embedding:
        return

    # Сохраняем в базу данных
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO semantic_posts (channel_id, message_id, text, embedding) VALUES (?, ?, ?, ?)",
            (str(message.chat.id), message.message_id, text_to_index, json.dumps(embedding))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка сохранения поста в индекс: {e}")


@router.message(Command("local_search"))
async def cmd_semantic_search(message: types.Message):
    """
    Команда поиска. Пример: /search проблемы с видеокартой nvidia
    """
    # Вычленяем сам запрос из команды
    query = message.text["/local_search ":] if message.text.startswith("/search ") else message.text[8:]
    query = query.strip()
    
    if not query:
        await message.reply("Введите поисковый запрос после команды. Пример:\n`/search лаги в играх`")
        return

    status_msg = await message.reply("🔍 Анализирую смысл запроса через Ollama...")
    
    # Получаем вектор поискового запроса
    query_vector = await get_embedding(query)
    if not query_vector:
        await status_msg.edit_text("❌ Не удалось векторизовать запрос (проверьте, запущена ли Ollama).")
        return

    await status_msg.edit_text("🧠 Ищу похожие по смыслу посты в базе данных...")

    # Извлекаем все посты из базы для сравнения
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, message_id, text, embedding FROM semantic_posts")
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка обращения к БД: {e}")
        return

    if not rows:
        await status_msg.edit_text("📭 База данных семантического поиска пока пуста.")
        return

    # Считаем сходство для каждого поста
    scored_results = []
    for row in rows:
        ch_id, msg_id, text, emb_json = row
        try:
            post_vector = json.loads(emb_json)
            similarity = cosine_similarity(query_vector, post_vector)
            
            # Порог схожести. 0.6 — обычно хороший баланс для модели nomic
            if similarity > 0.55: 
                scored_results.append((similarity, ch_id, msg_id, text))
        except:
            continue

    # Сортируем результаты по убыванию схожести (самые релевантные — сверху)
    scored_results.sort(key=lambda x: x[0], reverse=True)

    if not scored_results:
        await status_msg.edit_text("Ничего не найдено по смыслу. Попробуйте перефразировать.")
        return

    # Берем топ-3 лучших совпадения и формируем ответ
    response_text = f"🎯 **Топ совпадений по запросу:** *«{query}»*\n\n"
    for idx, (score, ch_id, msg_id, text) in enumerate(scored_results[:3], 1):
        # Обрезаем слишком длинный текст для превью
        preview = text[:150] + "..." if len(text) > 150 else text

        
        # Если чат публичный или у вас сохранены ссылки, можно сделать красивую ссылку на пост.
        # Пока выведем как текст с указанием процента схожести.
        response_text += f"{idx}. **Сходство: {score*100:.1f}%**\n📄 {preview}\n\n"

    await status_msg.edit_text(response_text, parse_mode="Markdown")

# Функция регистрации для вашей системы динамических плагинов
def register_plugin(dp, *args, **kwargs):
    dp.include_router(router)
