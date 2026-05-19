import os
from telethon import TelegramClient, connection
from config import API_ID, API_HASH
import database

telethon_client = None

def scan_sessions_from_disk():
    return [f.replace("userbot_", "").replace(".session", "") for f in os.listdir(".") if f.startswith("userbot_") and f.endswith(".session")]

def init_telethon_client(account_name: str) -> TelegramClient:
    global telethon_client
    database.set_active_account(account_name)
    safe_name = "".join([c for c in account_name if c.isalpha() or c.isdigit() or c=='_']).lower()
    

    # Правильный формат передачи MTProto прокси для Telethon
    telethon_client = TelegramClient(
        f"userbot_{safe_name}", API_ID, API_HASH,
        connection_retries=None, auto_reconnect=True,
    )

    return telethon_client

def get_current_client() -> TelegramClient:
    global telethon_client
    if telethon_client is None:
        active_name = database.get_active_account()
        if active_name:
            init_telethon_client(active_name)
    return telethon_client
