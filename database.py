import sqlite3
from config import DB_PATH

cached_active_account = None

def init_db():
    db = sqlite3.connect(DB_PATH, timeout=15)
    try:
        cursor = db.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('CREATE TABLE IF NOT EXISTS accounts (name TEXT PRIMARY KEY, phone TEXT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS active_session (user_id INTEGER PRIMARY KEY, account_name TEXT)')
        db.commit()
    finally:
        db.close()

def get_active_account() -> str:
    global cached_active_account
    if cached_active_account:
        return cached_active_account
        
    db = sqlite3.connect(DB_PATH, timeout=15)
    try:
        cursor = db.cursor()
        cursor.execute("SELECT account_name FROM active_session WHERE user_id = 8030850501")
        row = cursor.fetchone()
        if row:
            cached_active_account = row[0]
    finally:
        db.close()
    return cached_active_account

def set_active_account(account_name: str):
    global cached_active_account
    cached_active_account = account_name
    
    db = sqlite3.connect(DB_PATH, timeout=15)
    try:
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO active_session (user_id, account_name) 
            VALUES (8030850501, ?) 
            ON CONFLICT(user_id) DO UPDATE SET account_name = excluded.account_name
        ''', (account_name,))
        db.commit()
    finally:
        db.close()

def save_new_account(name: str, phone: str):
    db = sqlite3.connect(DB_PATH, timeout=15)
    try:
        cursor = db.cursor()
        cursor.execute("INSERT OR REPLACE INTO accounts VALUES (?, ?)", (name, phone))
        db.commit()
    finally:
        db.close()
