import os
import socks

API_ID = 37736214
API_HASH = "a2396a3a7e331773993bd2b251a74116"
BOT_TOKEN = "8875679114:AAHdSkvefPhsGtZCRYQtYMl0huQm6zOqcX8"
ADMIN_ID = 8636650501

# PROXY_TYPE = socks.SOCKS5  
# PROXY_IP = "45.142.158.41"  
# PROXY_PORT = 1080          
# proxy_config = (PROXY_TYPE, PROXY_IP, PROXY_PORT, True, None, None)

OLLAMA_MODEL = "qwen2.5:1.5b"  
PLUGINS_DIR = "generated_plugins"
DB_PATH = "bot_data.db"

os.makedirs(PLUGINS_DIR, exist_ok=True)
os.makedirs("downloads", exist_ok=True)
