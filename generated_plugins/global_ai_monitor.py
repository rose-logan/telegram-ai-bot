import os
import asyncio
import aiohttp
from aiogram import Router, types
from aiogram.filters import Command
from telethon.tl.functions.messages import SearchGlobalRequest
from telethon.tl.types import InputMessagesFilterEmpty, InputPeerEmpty

# Импортируем функцию получения клиента из вашего client_manager.py
from client_manager import get_current_client 

router = Router()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:1.5b"
ADMIN_ID = 8636650501  # Ваш Telegram ID из config.py

# Хранилище глобальных тем: { "тема": "описание_для_ии" }
GLOBAL_KEYWORDS = {}
# Хранилище уже отправленных сообщений, чтобы не спамить дубликатами
SENT_MESSAGE_IDS = set()

# Переменная для контроля фоновой задачи
monitor_task = None

async def ask_ollama_filter(post_text: str, keyword: str) -> bool:
    """Проверяет пост через qwen2.5:1.5b на релевантность ключевому слову"""
    prompt = (
        f"Ты — умный новостной фильтр. Твоя задача — определить, относится ли текст к теме: '{keyword}'.\n"
        f"Если текст поста реально содержит важную информацию или новости по теме, ответь строго одним словом: ДА.\n"
        f"Если это просто спам, реклама или не относится к теме, ответь строго одним словом: НЕТ.\n"
        f"Не пиши ничего, кроме слов ДА или НЕТ.\n\n"
        f"Текст поста:\n{post_text}"
    )
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    answer = data.get("response", "").strip().upper()
                    return "ДА" in answer or "YES" in answer
    except Exception as e:
        print(f"Ошибка Ollama в глобальном мониторинге: {e}")
    return False


async def global_search_worker():
    """Фоновый воркер, который циклично ищет посты по всему Telegram"""
    print("🚀 Фоновый воркер глобального ИИ-мониторинга запущен!")
    from main import bot  # Импортируем бота из главного файла для отправки сообщений

    while True:
        try:
            if not GLOBAL_KEYWORDS:
                await asyncio.sleep(10)  # Если тем нет, просто ждем
                continue

            telethon_client = get_current_client()
            if not telethon_client or not telethon_client.is_connected():
                await asyncio.sleep(20)
                continue

            # Проходим по всем ключевым словам в списке мониторинга
            for keyword in list(GLOBAL_KEYWORDS.keys()):
                # Делаем глобальный поиск свежих сообщений (offset_rate=0 для Telethon)
                search_result = await telethon_client(SearchGlobalRequest(
                    q=keyword,
                    filter=InputMessagesFilterEmpty(),
                    min_date=None,
                    max_date=None,
                    offset_id=0,
                    offset_peer=InputPeerEmpty(),
                    limit=5,
                    offset_rate=0
                ))

                for msg in search_result.messages:
                    if not msg.message or msg.peer_id.__class__.__name__ != 'PeerChannel':
                        continue

                    # Создаем уникальный ключ для проверки на дубликаты
                    msg_key = f"{msg.peer_id.channel_id}_{msg.id}"
                    if msg_key in SENT_MESSAGE_IDS:
                        continue

                    # Если сообщение новое — маркируем как прочитанное
                    SENT_MESSAGE_IDS.add(msg_key)

                    # Анализируем текст через qwen2.5:1.5b
                    is_ok = await ask_ollama_filter(msg.message, keyword)
                    if is_ok:
                        try:
                            entity = await telethon_client.get_entity(msg.peer_id)
                            link = f"https://t.me{entity.username}/{msg.id}" if getattr(entity, 'username', None) else "Приватный канал"
                            ch_title = entity.title
                        except Exception:
                            link = "Ссылка скрыта"
                            ch_title = "Глобальный канал"

                        alert = (
                            f"🌐 ✨ **Глобальный ИИ-Мониторинг обнаружил пост!**\n\n"
                            f"📢 **Источник:** {ch_title}\n"
                            f"🔑 **Ключевое слово:** `{keyword}`\n"
                            f"🔗 **Ссылка:** {link}\n\n"
                            f"📝 **Текст:**\n_{msg.message[:400]}..._"
                        )
                        await bot.send_message(chat_id=ADMIN_ID, text=alert, parse_mode="Markdown", disable_web_page_preview=True)
                
                # Небольшая пауза между разными ключевыми словами, чтобы не поймать флуд-рейт от Telegram
                await asyncio.sleep(5)

        except Exception as e:
            print(f"Ошибка в цикле глобального мониторинга: {e}")
        
        # Интервал проверки глобального поиска (например, каждые 5 минут / 300 секунд)
        # Можно уменьшить для тестов, но Telegram может выдать FloodWait, если искать слишком часто
        await asyncio.sleep(300)


@router.message(Command("monitor_global"))
async def cmd_monitor_global(message: types.Message):
    """
    Добавление темы в глобальный фоновый ИИ-мониторинг
    Пример: /monitor_global cyberpunk orion
    """
    global monitor_task
    
    query = message.text[15:].strip() if message.text.startswith("/monitor_global ") else message.text[16:].strip()
    if not query:
        await message.reply("⚠️ Укажите тему или фразу.\nПример: `/monitor_global обновление киберпанк`")
        return

    GLOBAL_KEYWORDS[query] = True
    await message.reply(
        f"🌐 **Глобальный ИИ-мониторинг запущен!**\n\n"
        f"Юзербот каждые 5 минут будет сканировать весь Telegram на фразу: `{query}`.\n"
        f"Модель {OLLAMA_MODEL} отфильтрует мусор и пришлет уведомление сюда."
    )

    # Запускаем фоновую задачу asyncio, если она еще не была запущена
    if monitor_task is None or monitor_task.done():
        monitor_task = asyncio.create_task(global_search_worker())


def register_plugin(dp, *args, **kwargs):
    dp.include_router(router)
