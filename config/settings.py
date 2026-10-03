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

# --- TON yuborish (BuyTon/, BuyStars/) va Fragment.com integratsiyasi ---
# DIQQAT: bular asl zip'da ichiga haqiqiy qiymatlar bilan to'ldirilgan edi —
# GitHub'ga ochiq ketmasligi uchun endi environment variable'ga ko'chirildi.
# Agar bu qiymatlar boshqa joyda (masalan eski zip) oshkor bo'lgan bo'lsa,
# ehtiyot shart uchun tonconsole.com/Fragment'da yangilab qo'yish tavsiya etiladi.
API_TON = os.environ.get('API_TON', '')            # https://tonconsole.com/ dan olingan api key
MNEMONIC = os.environ.get('MNEMONIC', '')           # 24 so'zlik hamyon maxfiy iborasi, probel bilan ajratilgan
MNEMONIC_LIST = MNEMONIC.split() if MNEMONIC else []

FRAGMENT_HASH = os.environ.get('FRAGMENT_HASH', '')
FRAGMENT_PUBLICKEY = os.environ.get('FRAGMENT_PUBLICKEY', '')
FRAGMENT_WALLETS = os.environ.get('FRAGMENT_WALLETS', '')
FRAGMENT_ADDRES = os.environ.get('FRAGMENT_ADDRES', '')

STEL_SSID = os.environ.get('STEL_SSID', '')
STEL_DT = os.environ.get('STEL_DT', '-300')
STEL_TON_TOKEN = os.environ.get('STEL_TON_TOKEN', '')
STEL_TOKEN = os.environ.get('STEL_TOKEN', '')

FRAGMENT_COOKIES = {
    'stel_ssid': STEL_SSID,
    'stel_dt': STEL_DT,
    'stel_ton_token': STEL_TON_TOKEN,
    'stel_token': STEL_TOKEN,
}
