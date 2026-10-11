"""
config/config.php ning Python porti.

Maxfiy qiymatlar (token, kalitlar, mnemonic, cookie) KODDA SAQLANMAYDI —
ular Render > Environment bo'limidan o'qiladi. Ochiq (maxfiy bo'lmagan) qiymatlar shu yerda.

Render'da kerakli o'zgaruvchilar:
BOT_TOKEN, MNEMONIC, TONAPI_KEY, API_TON,
STEL_SSID, STEL_DT, STEL_TON_TOKEN, STEL_TOKEN
(ixtiyoriy: BASE_URL, FRAGMENT_HASH, FRAGMENT_PUBLICKEY, FRAGMENT_WALLETS, FRAGMENT_ADDRES,
 TOLOV_API_URL, TOLOV_API_KEY — oxirgi ikkitasi config/payment_settings.py da o'qiladi)
"""
import os
import re
import logging

logger = logging.getLogger("sorapay.settings")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(name: str, default: str = '') -> str:
    """Muhit o'zgaruvchisini o'qiydi; bo'sh joylarni va tasodifiy qo'shtirnoqlarni olib tashlaydi."""
    return os.environ.get(name, default).strip().strip('"').strip("'")


# --- Telegram bot ---
BOT_TOKEN = _env('BOT_TOKEN')
API_URL = f'https://api.telegram.org/bot{BOT_TOKEN}/'

# --- ChannelDB sozlamalari (MySQL o'rniga) ---
DB_CHANNEL_ID = -1003755790777
DB_DATA_DIR = os.path.join(BASE_DIR, 'storage', 'db')

ADMIN_ID = 8578660273
LOG_CHANNEL_ID = -1003701137136
TONAPI_KEY = _env('TONAPI_KEY')   # tonapi.io kaliti

# Render bergan haqiqiy manzil. Boshqacha bo'lsa, BASE_URL o'zgaruvchisi bilan almashtiring.
BASE_URL = _env('BASE_URL', 'https://sorapaybot.onrender.com').rstrip('/')

DEBUG = _env('DEBUG', '0').lower() in ('1', 'true', 'yes')   # productionda o'chiq

STEP_DIR = os.path.join(BASE_DIR, 'step')
os.makedirs(STEP_DIR, exist_ok=True)
os.makedirs(DB_DATA_DIR, exist_ok=True)

# --- TON yuborish (BuyTon/, BuyStars/) va Fragment.com integratsiyasi ---
API_TON = _env('API_TON')

# Hamyon maxfiy iborasi: probel, vergul yoki yangi qator bilan ajratilgan 12 yoki 24 so'z.
MNEMONIC = _env('MNEMONIC')
MNEMONIC_LIST = [w for w in re.split(r'[\s,;]+', MNEMONIC.lower()) if w]

# Fragment — ochiq qiymatlar (fragment.com ga hamyon ulanganda olinadi).
# ⚠️ Quyidagi uch qiymat — namuna (asl koddan qolgan) va O'Z HAMYONINGIZNIKI EMAS.
# O'z hamyoningiz bilan fragment.com ga kirib, brauzer (F12 > Network > api?hash=...) dan olingan
# qiymatlar bilan Render Environment'da almashtiring: FRAGMENT_PUBLICKEY, FRAGMENT_WALLETS, FRAGMENT_ADDRES.
FRAGMENT_HASH = _env('FRAGMENT_HASH', '03290a4624161419')
FRAGMENT_PUBLICKEY = _env('FRAGMENT_PUBLICKEY', 'bd9767479817f5587029a3c131fadedfd4bcad456ec66729a9bd078034fb234d')
FRAGMENT_WALLETS = _env('FRAGMENT_WALLETS', 'te6cckECFgEAAwQAAgE0ARUBFP8A9KQT9LzyyAsCAgEgAxACAUgEBwLm0AHQ0wMdIz0M=')
FRAGMENT_ADDRES = _env('FRAGMENT_ADDRES', '0:c16230bea882a7dfc38c25734de1965d4651198718c130e32dabe0011352c')

# Fragment sessiya cookie'lari — MAXFIY
STEL_SSID = _env('STEL_SSID')
STEL_DT = _env('STEL_DT', '-300')
STEL_TON_TOKEN = _env('STEL_TON_TOKEN')
STEL_TOKEN = _env('STEL_TOKEN')

# Bo'sh qiymatli cookie'lar yuborilmaydi
FRAGMENT_COOKIES = {k: v for k, v in {
    'stel_ssid': STEL_SSID,
    'stel_dt': STEL_DT,
    'stel_ton_token': STEL_TON_TOKEN,
    'stel_token': STEL_TOKEN,
}.items() if v}


# --- Ishga tushganda tekshiruv (qiymatlarning o'zini logga yozmaydi, faqat "bor/yo'q") ---
def _startup_check():
    missing = [n for n, v in (('BOT_TOKEN', BOT_TOKEN), ('MNEMONIC', MNEMONIC),
                              ('TONAPI_KEY', TONAPI_KEY), ('API_TON', API_TON),
                              ('STEL_SSID', STEL_SSID), ('STEL_TOKEN', STEL_TOKEN)) if not v]
    if missing:
        logger.error("Render Environment'da yetishmayapti: %s", ", ".join(missing))
    if MNEMONIC and len(MNEMONIC_LIST) not in (12, 24):
        logger.error("MNEMONIC %d ta so'zdan iborat — 12 yoki 24 bo'lishi kerak", len(MNEMONIC_LIST))

    # Fragment qiymatlari: raw manzil '0:' + 64 ta hex belgi bo'ladi; walletStateInit odatda uzun (~300+ belgi).
    if not re.fullmatch(r'-?\d+:[0-9a-fA-F]{64}', FRAGMENT_ADDRES):
        logger.error("FRAGMENT_ADDRES noto'g'ri formatda (kutilgan: '0:' + 64 hex) — Stars/Premium xaridi ishlamaydi. "
                     "O'z hamyoningiz qiymatini Render Environment'ga kiriting.")
    if len(FRAGMENT_WALLETS) < 150:
        logger.error("FRAGMENT_WALLETS juda qisqa (%d belgi) — namuna qiymatga o'xshaydi. "
                     "O'z hamyoningiz qiymatini Render Environment'ga kiriting.", len(FRAGMENT_WALLETS))


_startup_check()