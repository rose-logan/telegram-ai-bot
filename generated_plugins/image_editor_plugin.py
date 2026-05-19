import os
from io import BytesIO
import requests
from PIL import Image, ImageFilter
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile, ReplyKeyboardRemove

# Импортируем вашу функцию ИИ
from ai_handler import ask_local_ai

class EditorStates(StatesGroup):
    wait_image = State()

plugin_router = Router()

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Создаем обычную Reply-клавиатуру для нижнего меню
def get_reply_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="🔲 ЧБ Фильтр"), KeyboardButton(text="💧 Размытие")],
        [KeyboardButton(text="🔄 Повернуть 90°"), KeyboardButton(text="↔️ Отзеркалить")],
        [KeyboardButton(text="🤖 ИИ-Анализ (Ollama)")],
        [KeyboardButton(text="❌ Выйти из редактора")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=False)

# Хэндлер команды начала работы
@plugin_router.message(Command("edit_img"))
async def cmd_edit_img(message: Message, state: FSMContext, admin_id: int):
    if message.from_user.id != admin_id:
        return
    await message.answer(
        "🖼 Отправьте мне картинку, и внизу откроется меню инструментов:",
        reply_markup=get_reply_keyboard()
    )
    await state.set_state(EditorStates.wait_image)

# Обработка полученного изображения и команд модификации
@plugin_router.message(EditorStates.wait_image)
async def process_image_logic(message: Message, state: FSMContext, bot: Bot):
    # Если пользователь нажал кнопку выхода
    if message.text == "❌ Выйти из редактора":
        await state.clear()
        return await message.answer("🚪 Вы зашли из режима редактирования.", reply_markup=ReplyKeyboardRemove())

    # Если прислали текст (нажатие на кнопку фильтра), а картинки еще нет на сервере
    file_name = f"{message.from_user.id}_current.jpg"
    file_path = os.path.join(DOWNLOAD_DIR, file_name)

    if message.text in ["🔲 ЧБ Фильтр", "💧 Размытие", "🔄 Повернуть 90°", "↔️ Отзеркалить", "🤖 ИИ-Анализ (Ollama)"]:
        if not os.path.exists(file_path):
            return await message.answer("📂 Сначала отправьте мне саму картинку, а потом нажимайте на фильтры!")
            
        status = await message.answer("⏳ Обрабатываю...")
        action = message.text

        try:
            if action == "🤖 ИИ-Анализ (Ollama)":
                with Image.open(file_path) as img:
                    width, height = img.size
                    mode = img.mode
                prompt = (
                    f"Параметры картинки: разрешение {width}x{height}, модель {mode}. "
                    f"Напиши короткий художественный пост на русском языке для соцсетей под это фото. Добавь 3 хэштега."
                )
                ai_text = ask_local_ai(prompt)
                await status.delete()
                return await message.answer(f"🤖 **Анализ от Ollama:**\n\n{ai_text}", parse_mode="Markdown")

            # Модификации через Pillow
            with Image.open(file_path) as img:
                if action == "🔲 ЧБ Фильтр":
                    edited_img = img.convert("L")
                    caption = "🔲 Черно-белый фильтр наложен!"
                elif action == "💧 Размытие":
                    edited_img = img.filter(ImageFilter.GaussianBlur(radius=5))
                    caption = "💧 Размытие применено!"
                elif action == "🔄 Повернуть 90°":
                    edited_img = img.rotate(270, expand=True)
                    caption = "🔄 Изображение повернуто!"
                elif action == "↔️ Отзеркалить":
                    edited_img = img.transpose(Image.FLIP_LEFT_RIGHT)
                    caption = "↔️ Картинка отзеркалена!"

                # Сохраняем измененную картинку как текущую базу, чтобы можно было применять фильтры по цепочке!
                edited_img.save(file_path, "JPEG")
                
                bio = BytesIO()
                bio.name = file_name
                edited_img.save(bio, "JPEG")
                bio.seek(0)

                await status.delete()
                await bot.send_photo(
                    chat_id=message.chat.id,
                    photo=BufferedInputFile(bio.read(), filename=bio.name),
                    caption=caption
                )
        except Exception as e:
            await status.edit_text(f"💥 Ошибка модификации: {str(e)}")
        return

    # Если прислали само фото/документ
    if message.photo or (message.document and message.document.mime_type.startswith("image/")):
        status = await message.answer("📥 Сохраняю изображение для обработки...")
        try:
            file_id = message.photo[-1].file_id if message.photo else message.document.file_id
            file = await bot.get_file(file_id)
            await bot.download_file(file.file_path, file_path)
            
            with Image.open(file_path) as img:
                width, height = img.size
                img_format = img.format
                
            await status.edit_text(
                f"📊 **Картинка готова к работе!**\nРазрешение: {width}x{height}\nФормат: {img_format}\n\n"
                f"Теперь нажимайте на кнопки внизу, чтобы применить фильтры."
            )
        except Exception as e:
            await status.edit_text(f"💥 Ошибка при загрузке: {str(e)}")
    else:
        await message.answer("❌ Пожалуйста, отправьте картинку или выберите инструмент в меню ниже.")

def register_plugin(main_plugins_router: Router, bot: Bot, admin_id: int):
    main_plugins_router.include_router(plugin_router)
