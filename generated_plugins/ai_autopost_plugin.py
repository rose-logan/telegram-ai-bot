import aiohttp
from aiogram import Router, F, types

router = Router()

OLLAMA_URL = "http://localhost:11434/api/generate"
# Укажите точный ID или публичный юзернейм вашего канала Sunny из настроек Telegram
CHANNEL_ID = "-1003975903271" 

async def format_text_for_channel(raw_text: str) -> str:
    """Просит qwen2.5:1.5b сделать текст привлекательным для канала"""
    prompt = (
        f"Перепиши этот текст так, чтобы получился красивый, вовлекающий пост для Telegram-канала. "
        f"Добавь подходящие эмодзи, разбей на абзацы, сделай цепляющий заголовок и в конце добавь 3-4 хэштега. "
        f"Текст:\n{raw_text}"
    )
    payload = {"model": "qwen2.5:1.5b", "prompt": prompt, "stream": False}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", raw_text)
    except Exception:
        pass
    return raw_text


@router.callback_query(F.data == "post_to_channel_action")
async def handle_autopost(callback: types.CallbackQuery):
    """Обработчик нажатия инлайн-кнопки для публикации"""
    await callback.answer("⏳ Модель Qwen форматирует пост...")
    
    # Берем оригинальный текст сообщения, где была нажата кнопка
    original_text = callback.message.text
    
    # Красиво оформляем его через ИИ
    ready_post = await format_text_for_channel(original_text)
    
    try:
        # Бот отправляет готовый пост в ваш канал
        await callback.bot.send_message(chat_id=CHANNEL_ID, text=ready_post, parse_mode="Markdown")
        await callback.message.edit_text(f"{original_text}\n\n✅ **Пост успешно опубликован в канал!**")
    except Exception as e:
        await callback.message.reply(f"❌ Ошибка публикации: {e}\nПроверьте, добавлен ли бот в админы канала.")


def register_plugin(dp, *args, **kwargs):
    dp.include_router(router)
