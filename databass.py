import os
import aiosqlite

DB_PATH = os.path.join(os.path.dirname(__file__), "data_img.db")

async def init_db():
    """Инициализация базы данных и создание таблиц при старте бота"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS download_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                command TEXT,
                input_url TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()

async def log_download(user_id: int, command: str, input_url: str):
    """Асинхронная безопасная запись лога скачивания в базу"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO download_history (user_id, command, input_url) VALUES (?, ?, ?)',
            (user_id, command, input_url)
        )
        await db.commit()
