import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, URLInputFile, InputMediaPhoto

class ImageParserStates(StatesGroup):
    wait_query = State()

plugin_router = Router()

# Универсальные заголовки браузера для обхода простейших защит сайтов
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8"
}

@plugin_router.message(Command("img"))
async def cmd_img_start(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
        
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        await parse_and_send_images(message, args[1].strip(), message.bot)
    else:
        await message.answer("🖼 Введите поисковый запрос для сбора картинок (например: *горы минимализм*):", parse_mode="Markdown")
        await state.set_state(ImageParserStates.wait_query)

@plugin_router.message(ImageParserStates.wait_query)
async def process_img_query(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
    await state.clear()
    await parse_and_send_images(message, message.text.strip(), message.bot)

# 1. Хэндлер для команды /parse_url
@plugin_router.message(Command("parse_url"))
async def cmd_parse_url(message: Message, bot: Bot, admin_id: int):
    if message.from_user.id != admin_id:
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("🔗 Пожалуйста, укажите ссылку. Пример:\n`/parse_url https://example.com`固定", parse_mode="Markdown")
        
    target_url = args[1].strip()
    status = await message.answer("⏳ Подключаюсь к сайту и собираю изображения...")
    
    try:
        # Делаем запрос к указанному сайту
        response = requests.get(target_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        media_group = []
        
        # Находим все теги картинок на этой конкретной странице
        for img in soup.find_all("img"):
            img_url = img.get("src") or img.get("data-src") or img.get("srcset")
            
            if not img_url:
                continue
                
            # Если ссылка относительная (например, /images/pic.jpg), делаем её абсолютной
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                # Берем базовый домен сайта (например, https://example.com)
                base_domain = "/".join(target_url.split("/")[:3])
                img_url = base_domain + img_url
            elif not img_url.startswith("http"):
                continue

            # Базовая фильтрация: убираем мелкие иконки, аватарки и мусор (.svg, .gif)
            if any(ext in img_url.lower() for ext in [".svg", ".gif", "avatar", "icon", "logo"]):
                continue
                
            # Защита от дубликатов
                    # Защита от дубликатов (строка 84 на вашем экране)
            if img_url not in [m.media.url for m in media_group if isinstance(m.media, URLInputFile)]:
                caption = f"🖼 Собрано со страницы:\n{target_url}" if len(media_group) == 0 else ""
                
                # СЮДА добавляем строку со спойлером!
                media_group.append(InputMediaPhoto(media=URLInputFile(img_url), caption=caption, has_spoiler=True))
                
            # Telegram разрешает отправлять максимум 10 медиафайлов
            if len(media_group) >= 10:
                break

                
        if not media_group:
            return await status.edit_text("❌ На этой странице не найдено подходящих картинок или сайт защищен от парсинга.")
            
        await status.edit_text(f"🚀 Найдено {len(media_group)} изображений! Отправляю альбом...")
        await bot.send_media_group(chat_id=message.chat.id, media=media_group)
        await status.delete()
        
    except Exception as e:
        await status.edit_text(f"💥 Не удалось спарсить страницу. Ошибка: {str(e)}")

async def parse_and_send_images(message: Message, query: str, bot: Bot):
    status = await message.answer(f"🔍 Парсер собирает лучшие фото по запросу: `{query}`...", parse_mode="Markdown")
    
    # Кодируем кириллицу для безопасной вставки в URL
    encoded_query = quote(query)
    
    # Источник 1: Прямой поиск по открытой базе высококачественных фото Unsplash
    url = f"https://unsplash.com{encoded_query}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        media_group = []
        
        # Парсим теги картинок на Unsplash (ищем оригинальные srcset или src)
        for img in soup.find_all("img"):
            img_url = img.get("src")
            # Отсеиваем аватарки и мелкие иконки интерфейса
            if img_url and "://unsplash.com" in img_url and "profile-" not in img_url:
                # Оптимизируем ссылку, чтобы забрать фото в хорошем разрешении (w=1080)
                clean_url = img_url.split("?")[0] + "?w=1080&fit=max&q=80"
                
                if clean_url not in [m.media.url for m in media_group if isinstance(m.media, URLInputFile)]:
                    caption = f"🖼 Результат по запросу: {query}" if len(media_group) == 0 else ""
                    media_group.append(InputMediaPhoto(media=URLInputFile(clean_url), caption=caption))
                    
                if len(media_group) >= 5: # Ограничиваем пачку до 5 штук
                    break

        # Если Unsplash ничего не выдал, включаем Резервный Источник 2 (WallpapersCraft или аналогичный)
        if not media_group:
            await status.edit_text("🔄 На основном сайте пусто, подключаю резервный источник...")
            backup_url = f"https://wallpaperscraft.ru{encoded_query}"
            response = requests.get(backup_url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for link in soup.find_all("a", class_="wallpapers__link"):
                img_page = "https://wallpaperscraft.ru" + link.get("href")
                # Быстрый переход к превью высокого качества
                img_id = img_page.split("_")[-1]
                direct_img = f"https://wallpaperscraft.ru{img_page.split('/')[-1]}_1920x1080.jpg"
                
                caption = f"🖼 Найдено в резерве: {query}" if len(media_group) == 0 else ""
                media_group.append(InputMediaPhoto(media=URLInputFile(direct_img), caption=caption))
                if len(media_group) >= 5:
                    break

        if not media_group:
            return await status.edit_text("❌ К сожалению, не удалось найти или распарсить картинки по этому запросу.")

        await status.edit_text("🚀 Сборка альбома завершена! Отправляю...")
        await bot.send_media_group(chat_id=message.chat.id, media=media_group)
        await status.delete()

    except Exception as e:
        await status.edit_text(f"💥 Ошибка парсера: {str(e)}")

def register_plugin(main_plugins_router: Router, bot: Bot, admin_id: int):
    main_plugins_router.include_router(plugin_router)
