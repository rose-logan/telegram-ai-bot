import aiohttp
from aiogram import Router, types, F
from config import ADMIN_ID
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from telethon import events

from client_manager import get_current_client

router = Router()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:1.5b"

# ID чата, который мы отслеживаем для помощи в ответах
TARGET_CHAT_ID = None
SUGGESTED_ANSWERS = {} # Перенесли сюда

async def ask_ollama_for_answer(question: str) -> str:
    """Генерирует экспертный ответ на технический или сложный вопрос"""
    prompt = (
        f"Ты — высококлассный технический специалист и вежливый участник сообщества. "
        f"Прочитай вопрос пользователя из чата и напиши идеальный, развернутый и точный ответ на русском языке. "
        f"Не пиши никаких вводных фраз вроде 'Вот твой ответ:', отвечай сразу по сути вопроса.\n\n"
        f"Вопрос пользователя:\n{question}"
    )
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", "").strip()
    except Exception as e:
        print(f"Ошибка Ollama в чат-ассистенте: {e}")
    return ""

async def on_new_chat_message(event):
    """Слушает новые сообщения в целевом чате через юзербота"""
    if not event.message or not event.message.message:
        return
    
    # Реагируем только на сообщения, содержащие знаки вопроса или ключевые слова (помогите, как сделать, почему)
    text = event.message.message.lower()
    if '?' not in text and not any(word in text for word in ['помоги', 'как', 'почему', 'ошибка', ' help']):
        return

    # Запрашиваем ИИ-ответ
    ai_reply = await ask_ollama_for_answer(event.message.message)
    if not ai_reply:
        return

    # Получаем инфо об авторе вопроса
    try:
        sender = await event.get_sender()
        sender_name = getattr(sender, 'first_name', 'Пользователь')
    except Exception:
        sender_name = "Пользователь"

    # Формируем структуру данных для инлайн-кнопки aiogram
    # Кнопка будет содержать callback_data формата: send_ans_[reply_to_msg_id]
    # Текст ответа мы временно сохраним в кэш или передадим (в лимит 64 байт callback_data текст не влезет, 
    # поэтому сохраняем в глобальный кэш плагина)
    msg_id = event.message.id
    SUGGESTED_ANSWERS[msg_id] = ai_reply

    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Отправить этот ответ", callback_data=f"send_ans_{msg_id}")
    builder.button(text="❌ Отклонить", callback_data="delete_suggestion")

    alert_text = (
        f"💬 **В отслеживаемом чате новый вопрос!**\n"
        f"👤 **От:** {sender_name}\n"
        f"❓ **Вопрос:** _{event.message.message}_\n\n"
        f"🤖 **Предлагаемый ответ от {OLLAMA_MODEL}:**\n{ai_reply}"
    )

    from main import bot
    await bot.send_message(chat_id=ADMIN_ID, text=alert_text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# Кэш для хранения сгенерированных ответов перед отправкой
SUGGESTED_ANSWERS = {}

@router.message(Command("assistant_chat"))
async def cmd_set_assistant_chat(message: types.Message):
    """Установка чата для отслеживания вопросов. Пример: /assistant_chat -100123456789"""
    global TARGET_CHAT_ID
    args = message.text.split()
    if len(args) < 2:
        await message.reply("⚠️ Укажите ID чата или супергруппы. Пример:\n`/assistant_chat -100123456789`")
        return

    try:
        TARGET_CHAT_ID = int(args[1])
        telethon_client = get_current_client()
        
        if not telethon_client or not telethon_client.is_connected():
            await message.reply("❌ Юзербот Telethon сейчас не активен.")
            return

        # Регистрируем событие для конкретного ID чата
        telethon_client.remove_event_handler(on_new_chat_message, events.NewMessage)
        telethon_client.add_event_handler(on_new_chat_message, events.NewMessage(chats=TARGET_CHAT_ID))

        await message.reply(f"🤖 **Чат-ассистент успешно запущен на ID:** `{TARGET_CHAT_ID}`\nБот пришлет варианты ответов, если там начнут задавать вопросы.")
    except Exception as e:
        await message.reply(f"❌ Ошибка инициализации ассистента: {e}")

@router.callback_query(F.data.startswith("send_ans_"))
async def handle_send_answer(callback: types.CallbackQuery):
    """Обработчик нажатия кнопки отправки ответа через юзербота"""
    msg_id = int(callback.data.split("_")[2])
    
    if msg_id not in SUGGESTED_ANSWERS:
        await callback.answer("❌ Срок действия этого ответа истек или он был удален из кэша.", show_alert=True)
        return

    text_to_send = SUGGESTED_ANSWERS[msg_id]

    try:
        telethon_client = get_current_client()
        # Юзербот отправляет сообщение в чат как ответ (reply) на оригинальный вопрос пользователя
        await telethon_client.send_message(entity=TARGET_CHAT_ID, message=text_to_send, reply_to=msg_id)
        
        await callback.message.edit_text(f"✅ **Ответ успешно отправлен юзерботом в чат!**\n\nТекст:\n_{text_to_send}_", parse_mode="Markdown")
        del SUGGESTED_ANSWERS[msg_id]
    except Exception as e:
        await callback.answer(f"Ошибка отправки через юзербота: {e}", show_alert=True)

@router.callback_query(F.data == "delete_suggestion")
async def handle_delete_suggestion(callback: types.CallbackQuery):
    await callback.message.delete()

def register_plugin(dp, *args, **kwargs):
    dp.include_router(router)
