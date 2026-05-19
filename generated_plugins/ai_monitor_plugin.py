import os
import aiohttp
from aiogram import Router, types
from aiogram.filters import Command
from telethon import events

# Импортируем вашего клиента из client_manager
from client_manager import get_current_client 

router = Router()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:1.5b"
ADMIN_ID = 8636650501  # Ваш ID из config.py для отправки алертов

# Словарь для хранения активных фоновых подписок юзербота
# Формат: { "имя_канала": "целевая_тема_или_слово" }
MONITORED_CHANNELS = {}

async def ask_ollama_filter(post_text: str, target_topic: str) -> bool:
    """Проверяет пост через qwen2.5:1.5b. Возвращает True, если тема совпала"""
    prompt = (
        f"Ты — строгий фильтр новостей. Твоя задача — определить, относится ли текст поста к теме: '{target_topic}'.\n"
        f"Если текст поста напрямую или по смыслу связан с этой темой, ответь строго одним словом: 'ДА'.\n"
        f"Если текст не связан с темой, ответь строго одним словом: 'НЕТ'.\n"
        f"Не пиши никаких лишних слов, пояснений или знаков препинания.\n\n"
        f"Текст поста:\n{post_text}"
    )
    
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
                    answer = data.get("response", "").strip().upper()
                    return "ДА" in answer or "YES" in answer
    except Exception as e:
        print(f"Ошибка Ollama в мониторинге: {e}")
    return False


async def handle_new_channel_message(event):
    """Фоновый обработчик Telethon для каждого нового сообщения в каналах"""
    if not event.message or not event.message.message:
        return

    # Определяем, откуда пришло сообщение
    try:
        chat = await event.get_chat()
        channel_username = getattr(chat, 'username', None)
        channel_title = chat.title
    except Exception:
        return

    # Проверяем, стоит ли этот канал на мониторинге
    target_key = f"@{channel_username}" if channel_username else None
    
    if target_key and target_key in MONITORED_CHANNELS:
        topic = MONITORED_CHANNELS[target_key]
        post_text = event.message.message
        
        # Передаем пост в локальную Ollama для анализа смысла
        is_relevant = await ask_ollama_filter(post_text, topic)
        
        if is_relevant:
            # Если тема совпала, юзербот берет ссылку и отправляет вам алерт через aiogram-бота
            link = f"https://t.me{channel_username}/{event.message.id}"
            alert_text = (
                f"🚨 **ИИ-Мониторинг зафиксировал совпадение!**\n\n"
                f"📢 **Канал:** {channel_title} ({target_key})\n"
                f"🎯 **Искомая тема:** `{topic}`\n"
                f"🔗 **Ссылка на пост:** {link}\n\n"
                f"📝 **Превью текста:**\n_{post_text[:300]}..._"
            )
            
            # Отправляем уведомление админу (доступ к bot можно получить из контекста или импортировать)
            from main import bot
            try:
                await bot.send_message(chat_id=ADMIN_ID, text=alert_text, parse_mode="Markdown", disable_web_page_preview=True)
            except Exception as e:
                print(f"Не удалось отправить уведомление админу: {e}")


@router.message(Command("monitor"))
async def cmd_ai_monitor(message: types.Message):
    """
    Включение фонового мониторинга канала
    Пример: /monitor @cyber_pic_art секс
    """
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("⚠️ Формат: `/monitor [@юзернейм_канала] [тема_или_слово]`")
        return

    channel_target = args[1]
    topic = args[2]

    status_msg = await message.reply(f"📡 Запускаю фоновый ИИ-мониторинг канала {channel_target} на тему `{topic}`...")

    try:
        telethon_client = get_current_client()
        if not telethon_client:
            await status_msg.edit_text("❌ Юзербот не активен в текущей сессии.")
            return

        if not telethon_client.is_connected():
            await telethon_client.connect()

        # Сохраняем настройки в память плагина
        MONITORED_CHANNELS[channel_target] = topic

        # Вешаем событие перехвата новых сообщений в Telethon (если еще не висит)
        # Telethon безопасно перезаписывает или добавляет один и тот же обработчик
        telethon_client.remove_event_handler(handle_new_channel_message, events.NewMessage)
        telethon_client.add_event_handler(handle_new_channel_message, events.NewMessage)

        await status_msg.edit_text(
            f"✅ **Мониторинг успешно запущен!**\n\n"
            f"Юзербот теперь слушает канал {channel_target}.\n"
            f"Как только выйдет пост про `{topic}`, модель {OLLAMA_MODEL} пришлет вам разбор."
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Не удалось поставить канал на мониторинг: {e}")


def register_plugin(dp, *args, **kwargs):
    dp.include_router(router)
