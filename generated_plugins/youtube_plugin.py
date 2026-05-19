import os
import glob
import yt_dlp
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, FSInputFile, URLInputFile, InputMediaPhoto

class YouTubeStates(StatesGroup):
    wait_link = State()
    wait_search = State()

plugin_router = Router()

# Создаем папку для временных файлов, если её нет
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

YDL_OPTS_BASE = {
    'quiet': True,
    'no_warnings': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

# --- 1. СКАЧИВАНИЕ ВИДЕО НА ДИСК И ОТПРАВКА ---
@plugin_router.message(Command("yt"))
async def cmd_yt_start(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        await download_and_send_video(message, args[1].strip(), message.bot)
    else:
        await message.answer("📺 Отправьте мне ссылку на видео из YouTube или Shorts:")
        await state.set_state(YouTubeStates.wait_link)

@plugin_router.message(YouTubeStates.wait_link)
async def process_yt_link(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
    await state.clear()
    await download_and_send_video(message, message.text.strip(), message.bot)

async def download_and_send_video(message: Message, url: str, bot: Bot):
    if not ("youtube.com" in url or "youtu.be" in url):
        return await message.answer("❌ Это не похоже на ссылку YouTube.")
        
    status = await message.answer("⏳ Скачиваю видео на сервер (это может занять время)...")
    
    # Шаблон имени файла:downloads/ID_видео.mp4
    outtmpl = os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s')
    
    ydl_opts = {
        **YDL_OPTS_BASE,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', # Ищем mp4 до 720p/1080p
        'outtmpl': outtmpl,
        'merge_output_format': 'mp4',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get('id')
            title = info.get('title', 'Видео из YouTube')
            
        # Ищем скачанный файл в папке
        filepath = None
        for ext in ['mp4', 'mkv', 'webm']:
            possible_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
            if os.path.exists(possible_path):
                filepath = possible_path
                break
                
        if not filepath:
            return await status.edit_text("❌ Файл скачался, но не найден на диске.")
            
        await status.edit_text("🚀 Видео загружено на сервер! Пересылаю в Telegram...")
        
        # Отправляем как локальный файл через FSInputFile
        input_file = FSInputFile(filepath)
        await bot.send_video(chat_id=message.chat.id, video=input_file, caption=f"🎬 **{title}**", parse_mode="Markdown")
        await status.delete()
        
        # Удаляем файл с сервера после отправки
        os.remove(filepath)
        
    except Exception as e:
        await status.edit_text(f"💥 Ошибка при скачивании видео: {str(e)}")


# --- 2. ПОИСК ВИДЕО (ПРЕВЬЮ И ССЫЛКИ) ---
@plugin_router.message(Command("yt_search"))
async def cmd_yt_search(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
        
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        await perform_youtube_search(message, args[1].strip(), message.bot)
    else:
        await message.answer("🔍 Введите поисковый запрос для YouTube:", parse_mode="Markdown")
        await state.set_state(YouTubeStates.wait_search)

@plugin_router.message(YouTubeStates.wait_search)
async def process_yt_search(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
    await state.clear()
    await perform_youtube_search(message, message.text.strip(), message.bot)

async def perform_youtube_search(message: Message, query: str, bot: Bot):
    status = await message.answer(f"🔍 Ищу видео на YouTube по запросу: `{query}`...", parse_mode="Markdown")
    
    ydl_opts = {
        **YDL_OPTS_BASE,
        'extract_flat': True,
        'playlistend': 5,
    }
    
    search_query = f"ytsearch5:{query}"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(search_query, download=False)
            
        if not result or 'entries' not in result or not result['entries']:
            return await status.edit_text("❌ По вашему запросу ничего не найдено.")
            
        await status.edit_text("🚀 Результаты найдены! Склеиваю список...")
        
        media_group = []
        for index, entry in enumerate(result['entries'], start=1):
            video_id = entry.get('id')
            title = entry.get('title', 'Без названия')
            
            if video_id:
                thumb_url = f"https://youtube.com{video_id}/hqdefault.jpg"
                video_link = f"https://youtube.com{video_id}"
                
                input_file = URLInputFile(thumb_url)
                caption = f"{index}. [{title}]({video_link})"
                
                media_group.append(InputMediaPhoto(media=input_file, caption=caption, parse_mode="Markdown"))
        
        if not media_group:
            return await status.edit_text("❌ Не удалось собрать результаты поиска.")
            
        await bot.send_media_group(chat_id=message.chat.id, media=media_group)
        await status.delete()
        
    except Exception as e:
        await status.edit_text(f"💥 Ошибка поиска: {str(e)}")


def register_plugin(main_plugins_router: Router, bot: Bot, admin_id: int):
    main_plugins_router.include_router(plugin_router)
