import asyncio
import os
import sys
import re
import importlib.util
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from telethon import events
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.stories import GetPinnedStoriesRequest

# Импортируем наши собственные созданные модули
from config import BOT_TOKEN, ADMIN_ID, PLUGINS_DIR, OLLAMA_MODEL
import database
import client_manager
import ai_handler
import ai_router

# Подключаем универсальный ИИ-пульт из отдельного файла

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class AuthStates(StatesGroup):
    wait_name = State()
    wait_phone = State()
    wait_code = State()
    wait_password = State()

async def get_admin_keyboard():
    builder = InlineKeyboardBuilder()
    sessions = client_manager.scan_sessions_from_disk()
    for s_name in sessions:
        builder.button(text=f"👤 {s_name}", callback_data=f"select_acc:{s_name}")
    builder.button(text="➕ Добавить аккаунт", callback_data="add_new_account")
    builder.adjust(2)
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🤖 Бот находится на тех. обслуживании. Попробуйте позже.")

@dp.message(Command("vakson"))
async def cmd_secret_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    active_now = database.get_active_account() or "Не выбран"
    kb = await get_admin_keyboard()
    await message.answer(
        f"🗝 **Панель [VAKSON]**\n🎯 В ОЗУ активен: `{active_now}`\n\n"
        f"Команды:\n• `/channel [ссылка] [дата]` - качать канал\n"
        f"• `/stories [юзернейм]` - сторис\n"
        f"• `/search [слово]` - поиск\n"
        f"• `/monitor [ссылка]` - слежка\n"
        f"• `/ai_code [имя_файла] [запрос]` - ИИ-модуль", 
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("select_acc:"))
async def handle_select_account(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    acc_name = callback.data.split(":")[1]
    client_manager.init_telethon_client(acc_name)
    await callback.answer(f"Переключено в ОЗУ на {acc_name}")
    await callback.message.edit_text(f"🗝 **Панель [VAKSON]**\n🎯 В ОЗУ активен: `{acc_name}`", reply_markup=await get_admin_keyboard())

# --- ОБРАБОТКА ГЛАСОВЫХ И АУДИО (НОВАЯ ФИЧА) ---
@dp.message(F.voice | F.audio)
async def handle_voice_message(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    status = await message.answer("📥 Скачиваю голосовое сообщение...")
    file_id = message.voice.file_id if message.voice else message.audio.file_id
    file = await bot.get_file(file_id)
    
    # Сохраняем аудио во временную папку
    os.makedirs("temp_voice", exist_ok=True)
    file_path = os.path.join("temp_voice", f"voice_{message.message_id}.ogg")
    await bot.download_file(file.file_path, file_path)
    
    await status.edit_text("🤖 Whisper распознает речь, а Ollama форматирует текст...")
    
    # 1. Сначала СТРОГО получаем текст от ИИ-обработчика
    ai_text = ai_handler.transcribe_voice_to_text(file_path)
    
    # 2. И только потом безопасно отправляем его в чат
    if len(ai_text) > 4000:
        try:
            await status.delete()
        except:
            pass
        for x in range(0, len(ai_text), 4000):
            await message.answer(ai_text[x:x+4000])
    else:
        await status.edit_text(ai_text)

    
    # Чистим за собой диск
    try: os.remove(file_path)
    except: pass

# --- КОМАНДА СКАЧИВАНИЯ КАНАЛА ---
@dp.message(Command("channel"))
async def cmd_download_channel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    active_name = database.get_active_account()
    if not active_name: return await message.answer("❌ Выбери аккаунт")
    
    args = message.text.split(maxsplit=2)
    if len(args) < 2: return await message.answer("❌ Формат: `/channel [ссылка] [дата]`")
    
    raw_target = args[1]
    target_channel = int(raw_target) if (raw_target.startswith('-') and raw_target[1:].isdigit()) or raw_target.isdigit() else raw_target
    
    filter_date = None
    if len(args) == 3:
        try: filter_date = datetime.strptime(args[2], "%d.%m.%Y")
        except ValueError: return await message.answer("❌ Нужна дата в формате ДД.ММ.ГГГГ")

    status = await message.answer("⏳ Читаю канал...")
    try:
        client = client_manager.get_current_client()
        if not client.is_connected(): await client.connect()
        
        output_dir = os.path.join("downloads", active_name, str(raw_target).replace("https://", "").replace("t.me/", "").replace("/", "_"))
        os.makedirs(output_dir, exist_ok=True)
        
        downloaded = 0
        async for msg in client.iter_messages(target_channel, limit=15):
            if msg.media and not hasattr(msg.media, 'webpage'):
                if filter_date and msg.date.replace(tzinfo=None) < filter_date: continue
                
                file_path = await client.download_media(msg, file=os.path.join(output_dir, f"{msg.id}"))
                if file_path and os.path.exists(file_path):
                    downloaded += 1
                    ai_caption = ai_handler.ask_local_ai(msg.text)
                    input_file = types.FSInputFile(file_path)
                    await message.answer_video(video=input_file, caption=ai_caption) if file_path.endswith(('.mp4', '.mov')) else await message.answer_photo(photo=input_file, caption=ai_caption)
            if downloaded >= 5: break
        await status.edit_text(f"✅ Готово! Файлы в папе `{output_dir}`")
    except Exception as e: await status.edit_text(f"❌ Ошибка: {e}")

# --- ИИ ПЛАГИНЫ (ПЕРЕНЕСЕНО СЮДА) ---
# --- АВТОРИЗАЦИЯ, СТОРИС, ПОИСК, МОНИТОРИНГ (ОБРЕЗАНЫ ДЛЯ КРАТКОСТИ ССЫЛКАМИ НА СТАРЫЕ МОДУЛИ) ---
# [Здесь остаются функции cmd_download_stories, cmd_search_media, cmd_monitor_channel, btn_add_account из прошлого поста, они вызывают client_manager.get_current_client()]
import os
import importlib.util
from aiogram import Dispatcher, Bot, Router

plugins_router = Router()

async def load_plugins(dp: Dispatcher, bot: Bot, admin_id: int):
    global plugins_router
    
    # 1. Отключаем старый роутер со всеми хэндлерами, если он был
    if plugins_router in dp.sub_routers:
        # В aiogram 3 sub_routers — это список. Удаляем старый контейнер.
        dp.sub_routers.remove(plugins_router)
        
    # 2. Создаем чистый контейнер для новой загрузки
    plugins_router = Router()
    
    dp.include_router(plugins_router)
    @plugins_router.message.middleware()
    async def admin_id_middleware(handler, event, data):
        data["admin_id"] = admin_id
        return await handler(event, data)


    plugins_dir = os.path.join(os.path.dirname(__file__), "generated_plugins")
    if not os.path.exists(plugins_dir):
        print(f"Папка {plugins_dir} не найдена.")
        return

    # 3. Перебираем файлы в папке плагинов
    for filename in os.listdir(plugins_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = f"generated_plugins.{filename[:-3]}"
            
            # Сброс кэша импортов Python, чтобы применились изменения в коде
            if module_name in sys.modules:
                del sys.modules[module_name]
                
            try:
                # Динамический импорт модуля
                spec = importlib.util.spec_from_file_location(module_name, os.path.join(plugins_dir, filename))
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                
                # Регистрируем плагин в НАШЕМ контейнере plugins_router
                if hasattr(module, "register_plugin"):
                    module.register_plugin(plugins_router, bot, ADMIN_ID)
                    print(f"Плагин {filename} успешно загружен/обновлен!")
            except Exception as e:
                print(f"Ошибка при загрузке плагина {filename}: {e}")

# Команда для перезагрузки плагинов без остановки бота
@dp.message(Command("reload_plugins"))
async def cmd_reload_plugins(message: types.Message, bot: Bot):
    # Импортируем ADMIN_ID из вашего конфига, если его нет в main.py
    from config import ADMIN_ID 
    
    if message.from_user.id != ADMIN_ID:
        return
        
    status_msg = await message.answer("🔄 Перезагружаю плагины из папки...")
    
    try:
        # Вызываем нашу функцию загрузки заново
        await load_plugins(dp, bot, ADMIN_ID)
        await status_msg.edit_text("✅ Все плагины успешно обновлены без перезапуска процесса!")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка при перезагрузке: {e}")

async def main():
    database.init_db()
    available_sessions = client_manager.scan_sessions_from_disk()
    if available_sessions:
        client_manager.init_telethon_client(available_sessions[0])
        try: await client_manager.get_current_client().connect()
        except: pass
    await load_plugins(dp, bot, ADMIN_ID)
    print("🚀 загрузка плагинов!")
    ai_router.register_ai_router(dp, bot, ADMIN_ID)
    print("🚀 Модульный комбайн [VAKSON] успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
