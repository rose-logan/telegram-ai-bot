import os
import requests
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import quote
import yt_dlp
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, URLInputFile, InputMediaPhoto, InputMediaVideo

import logging
from logging.handlers import RotatingFileHandler

# Создаем изолированный логгер для этого плагина
plugin_logger = logging.getLogger("pinterest_plugin")
plugin_logger.setLevel(logging.INFO)

# Формат записи: Время [УРОВЕНЬ] Функция(Строка): Сообщение
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(funcName)s(%(lineno)d): %(message)s')

# Настраиваем запись в отдельный файл плагина (до 5 МБ)
file_handler = RotatingFileHandler('pinterest_errors.log', maxBytes=5*1024*1024, backupCount=2, encoding='utf-8')
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.ERROR)  # Писать в файл только ошибки и критические сбои

plugin_logger.addHandler(file_handler)

# Импортируем функцию ИИ из вашего обработчика
from ai_handler import ask_local_ai

class PinterestStates(StatesGroup):
    wait_link = State()
    wait_search = State()

plugin_router = Router()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
}

def extract_media_from_url(url: str):
    try:
        if "pin.it" in url:
            res = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=10)
            url = res.url
            
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        meta_video = soup.find("meta", property="og:video:secure_url") or soup.find("meta", property="og:video")
        if meta_video and meta_video.get("content"):
            return meta_video["content"], True
            
        meta_image = soup.find("meta", property="og:image")
        if meta_image and meta_image.get("content"):
            return meta_image["content"], False
            
    except Exception:
        pass
    return None, False

@plugin_router.message(Command("pin"))
async def cmd_pinterest_start(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        await download_and_send_pin(message, args[1].strip(), message.bot)
    else:
        await message.answer("📌 Отправьте мне ссылку на видео или фото из Pinterest:")
        await state.set_state(PinterestStates.wait_link)

@plugin_router.message(PinterestStates.wait_link)
async def process_pin_link(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
    await state.clear()
    await download_and_send_pin(message, message.text.strip(), message.bot)

async def download_and_send_pin(message: Message, url: str, bot: Bot):
    if not ("pinterest.com" in url or "pin.it" in url):
        return await message.answer("❌ Это не похоже на ссылку Pinterest.")
        
    status = await message.answer("⏳ Анализирую страницу Pinterest и вытягиваю медиа...")
    media_url, is_video = extract_media_from_url(url)
    
    if not media_url:
        return await status.edit_text("❌ Не удалось извлечь медиафайл.")
        
    await status.edit_text("🚀 Файл найден, отправляю...")
    input_file = URLInputFile(media_url)
    
    if is_video:
        await bot.send_video(chat_id=message.chat.id, video=input_file, caption="Вот ваше видео из Pinterest!")
    else:
        await bot.send_photo(chat_id=message.chat.id, photo=input_file, caption="Вот ваше фото из Pinterest!")
    await status.delete()

@plugin_router.message(Command("pin_search"))
async def cmd_pinterest_search(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
        
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        await perform_pinterest_search(message, args[1].strip(), message.bot)
    else:
        await message.answer("🔍 Введите поисковый запрос для Pinterest:")
        await state.set_state(PinterestStates.wait_search)

@plugin_router.message(PinterestStates.wait_search)
async def process_pin_search(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
    await state.clear()
    await perform_pinterest_search(message, message.text.strip(), message.bot)

async def perform_pinterest_search(message: Message, query: str, bot: Bot):
    status = await message.answer(f"🤖 Ollama (`qwen2.5:1.5b`) оптимизирует запрос...", parse_mode="Markdown")
    
    prompt = f"Translate to 2-3 English keywords for Pinterest search. Output ONLY keywords separated by spaces. Query: {query}"
    try:
        ai_keywords = await ask_local_ai(prompt)
        ai_keywords = ai_keywords.strip().replace('"', '').replace("'", "").replace("\n", " ")
        if not ai_keywords or len(ai_keywords) > 100:
            ai_keywords = query
    except Exception:
        ai_keywords = query
        
    await status.edit_text(f"🔍 Ищу на Pinterest по запросу: `{ai_keywords}`...", parse_mode="Markdown")
    
    encoded_keywords = quote(ai_keywords)
    search_url = f"https://pinterest.com{encoded_keywords}"
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'playlistend': 5,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(search_url, download=False)
            
        if not result or 'entries' not in result or not result['entries']:
            raise Exception("Пустой результат от Pinterest")
            
        await status.edit_text("🚀 Склеиваю медиа-группу и отправляю в чат...")
        
        media_group = []
        for index, entry in enumerate(result['entries'], start=1):
            if 'url' in entry:
                direct_url = entry['url']
                input_file = URLInputFile(direct_url)
                caption = f"Результат {index} для: {query}" if len(media_group) == 0 else ""
                
                if "://pinimg.com" in direct_url or ".mp4" in direct_url:
                    media_group.append(InputMediaVideo(media=input_file, caption=caption))
                else:
                    media_group.append(InputMediaPhoto(media=input_file, caption=caption))
                    
        if not media_group:
            raise Exception("Не удалось собрать медиа из пинов")
            
        await bot.send_media_group(chat_id=message.chat.id, media=media_group)
        await status.delete()
        
    except Exception as e:
        await status.edit_text("⚠️ Pinterest заблокировал запрос. Ищу через резервный источник...")
        try:
            # Прямой и точный адрес для поиска картинок
            ddg_url = f"https://duckduckgo.com{quote(ai_keywords)}+pinterest"
            
            res = requests.get(ddg_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            media_group = []
            for img in soup.find_all("img", class_="image-thumb"):
                img_url = img["src"]
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                
                if len(media_group) < 5:
                    caption = f"Найдено по запросу: {query}" if len(media_group) == 0 else ""
                    media_group.append(InputMediaPhoto(media=URLInputFile(img_url), caption=caption))
            
            if media_group:
                await status.edit_text("🚀 Отправляю найденные медиафайлы...")
                await bot.send_media_group(chat_id=message.chat.id, media=media_group)
                await status.delete()
            else:
                await status.edit_text("❌ По вашему запросу ничего не найдено.")
            
        except Exception as err:
            await status.edit_text(f"💥 Ошибка поиска: {str(err)}")

def register_plugin(main_plugins_router: Router, bot: Bot, admin_id: int):
    main_plugins_router.include_router(plugin_router)
