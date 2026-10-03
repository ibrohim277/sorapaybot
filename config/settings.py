"""
config/config.php ning Python porti.
Barcha global sozlamalar shu yerda.

DIQQAT: maxfiy qiymatlar (BOT_TOKEN, TONAPI_KEY, DB_CHANNEL_ID) endi
environment variable'lardan o'qiladi — GitHub'ga ochiq push qilish
xavfsiz bo'lishi uchun. Render.com'da "Environment" bo'limiga shu
nomlar bilan qo'shing (.env.example faylga qarang).
"""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))  # lokalda .env bo'lsa yuklaydi; Render'da .env yo'q, shunchaki o'tkazib yuboradi

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
API_URL = f'https://api.telegram.org/bot{BOT_TOKEN}/'

# --- ChannelDB sozlamalari (MySQL o'rniga) ---
DB_CHANNEL_ID = int(os.environ.get('DB_CHANNEL_ID', '-1004403059476'))
DB_DATA_DIR = os.environ.get('DB_DATA_DIR', os.path.join(BASE_DIR, 'storage', 'db'))

ADMIN_ID = int(os.environ.get('ADMIN_ID', '2142292702'))
LOG_CHANNEL_ID = int(os.environ.get('LOG_CHANNEL_ID', '-1003991077401'))
TONAPI_KEY = os.environ.get('TONAPI_KEY', '')   # tonapi.io kalitingiz
BASE_URL = os.environ.get('BASE_URL', '')       # Render'dagi public URL, masalan: https://sorapay.onrender.com

DEBUG = os.environ.get('DEBUG', '1') == '1'

STEP_DIR = os.environ.get('STEP_DIR', os.path.join(BASE_DIR, 'step'))
os.makedirs(STEP_DIR, exist_ok=True)
os.makedirs(DB_DATA_DIR, exist_ok=True)
