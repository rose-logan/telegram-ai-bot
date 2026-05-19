import os
import re
import sys
import importlib.util
import ollama
from aiogram import types, Bot, Dispatcher
from config import OLLAMA_MODEL, PLUGINS_DIR

def register_ai_router(dp: Dispatcher, bot: Bot, admin_id: int):
    
    @dp.message(lambda message: message.text and message.text.startswith('/ai'))
    async def cmd_universal_ai(message: types.Message):
        if message.from_user.id != admin_id: return
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            return await message.answer(
                "🧠 **Универсальный ИИ-Пульт [Ollama]**\n\n"
                "**Варианты использования:**\n"
                "💬 *Просто диалог/вопрос:*\n`/ai почему небо синее?`\n\n"
                "🤖 *Создать плагин для этого бота:*\n`/ai плагин:имя_файла сделай команду /pog`\n\n"
                "💻 *Написать отдельную программу на ПК:*\n`/ai код:script.py напиши парсер сайтов`"
            )
        
        user_request = args[1].strip()
        status = await message.answer("🤖 Локальный ИИ обрабатывает запрос...")
        
        # 1. СЦЕНАРИЙ А: СОЗДАНИЕ ПЛАГИНА ДЛЯ ТЕКУЩЕГО БОТА
        if user_request.lower().startswith("плагин:"):
            try:
                sub_args = user_request.split(maxsplit=1)
                filename = sub_args[0].replace("плагин:", "").replace(".py", "").strip() + ".py"
                actual_prompt = sub_args[1]
                
                response = ollama.generate(
                    model=OLLAMA_MODEL,
                    prompt=(
                        f"Ты — высококлассный Python-разработчик. Напиши изолированный модуль для бота aiogram 3.\n"
                        f"Модуль должен СТРОГО соответствовать этой структуре:\n"
                        f"from aiogram import types, Bot, Dispatcher\n"
                        f"from aiogram.filters import Command\n\n"
                        f"def register_plugin(dp: Dispatcher, bot: Bot, admin_id: int):\n"
                        f"    @dp.message(Command('команда'))\n"
                        f"    async def handler(message: types.Message):\n"
                        f"        if message.from_user.id != admin_id: return\n"
                        f"        await message.answer('ответ')\n\n"
                        f"Задание: '{actual_prompt}'. Перепиши шаблон под задание. Используй admin_id для проверки доступа.\n"
                        f"Верни СТРОГО только готовый код Python без объяснений и без markdown-разметки (без ```python)!"
                    ),
                    options={"num_predict": 800, "temperature": 0.1, "top_p": 0.1}
                )
                code = re.sub(r'^```python\s*|^```\s*|\s*```\$', '', response['response'].strip(), flags=re.IGNORECASE).strip()
                
                file_path = os.path.join(PLUGINS_DIR, filename)
                with open(file_path, "w", encoding="utf-8") as f: f.write(code)
                
                # Динамическая активация плагина на лету
                spec = importlib.util.spec_from_file_location(filename[:-3], file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.register_plugin(dp, bot, admin_id)
                
                return await status.edit_text(f"🔥 ИИ-модуль `{filename}` успешно создан и активирован в ОЗУ на лету!")
            except Exception as e:
                return await status.edit_text(f"❌ Ошибка создания плагина: {e}")

        # 2. СЦЕНАРИЙ Б: НАПИСАТЬ СТОРОННЮЮ ПРОГРАММУ/СКРИПТ
        elif user_request.lower().startswith("код:"):
            try:
                sub_args = user_request.split(maxsplit=1)
                filename = sub_args[0].replace("код:", "").strip()
                actual_prompt = sub_args[1]
                
                response = ollama.generate(
                    model=OLLAMA_MODEL,
                    prompt=(
                        f"Напиши полноценную, рабочую программу на Python по запросу: '{actual_prompt}'. "
                        f"Код должен быть чистым, с комментариями. Верни СТРОГО только код программы, "
                        f"без вводных слов, объяснений и без markdown-кавычек ```python."
                    ),
                    options={"num_predict": 1200, "temperature": 0.2}
                )
                code = re.sub(r'^```python\s*|^```\s*|\s*```$', '', response['response'].strip(), flags=re.IGNORECASE).strip()
                
                os.makedirs("generated_apps", exist_ok=True)
                file_path = os.path.join("generated_apps", filename)
                with open(file_path, "w", encoding="utf-8") as f: f.write(code)
                
                return await status.edit_text(f"💻 Программа успешно написана и сохранена на ПК!\n📂 Путь: `generated_apps/{filename}`")
            except Exception as e:
                return await status.edit_text(f"❌ Ошибка генерации кода: {e}")

        # 3. СЦЕНАРИЙ В: РЕЖИМ УМНОГО ДИАЛОГА И ОТВЕТА НА ВОПРОСЫ
        else:
            try:
                response = ollama.generate(
                    model=OLLAMA_MODEL,
                    prompt=(
                        f"Ты — продвинутый ИИ-ассистент, встроенный в медиа-комбайн [VAKSON]. "
                        f"Ответь на запрос пользователя развернуто, грамотно и дружелюбно. "
                        f"Запрос: '{user_request}'. Пиши строго на русском языке."
                    ),
                    options={"num_predict": 600, "temperature": 0.7, "top_p": 0.9}
                )
                await status.edit_text(response['response'].strip())
            except Exception as e:
                await status.edit_text(f"❌ Ошибка ИИ-диалога: {e}")
