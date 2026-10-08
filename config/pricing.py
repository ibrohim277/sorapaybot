"""
Narxlar va to'lov rekvizitlari — SHU FAYLNI O'ZINGIZGA MOSLAB TAHRIRLANG.

Narx formulasi asl PHP kodidagi bilan bir xil (main.py -> fetch_pricing):
    1 TON narxi (so'm) = max(TON bozor kursi + MARGIN_UZS, MIN_TON_UZS)
    Stars narxi        = Stars soni * (TON_PER_50_STARS / 50) * 1 TON narxi
    Premium narxi      = PREMIUM_TON[oy] * 1 TON narxi
    TON narxi          = TON miqdori * 1 TON narxi

⚠️ Admin botning o'zida ham sozlay oladi (qayta deploy shart emas):
    /karta 8600123412341234 Ism Familiya     — to'lov kartasi
    /kurs 31500                               — 1 TON kursini qo'lda belgilash
    /kurs auto                                — kursni avtomatik olishga qaytish
"""
import math
import time
import logging

import requests

logger = logging.getLogger("sorapay.pricing")

# --- Asl PHP kodidan olingan qiymatlar --------------------------------------
TON_PER_50_STARS = 0.4279                         # 50 ta Stars = necha TON
PREMIUM_TON = {3: 6.70, 6: 8.92, 12: 16.16}       # Premium oylari -> TON
MARGIN_UZS = 1500                                 # TON kursiga qo'shiladigan foyda (so'm)
MIN_TON_UZS = 21000 + 1500                        # 1 TON uchun minimal narx (so'm)

# --- Miqdor chegaralari -----------------------------------------------------
STARS_PACKS = [50, 100, 250, 500, 1000]
STARS_MIN, STARS_MAX = 50, 10000
TON_PACKS = [1, 5, 10, 25]
TON_MIN, TON_MAX = 1, 100

# Fragment/TON hamyonda har doim qoldiriladigan zaxira (komissiya uchun)
WALLET_RESERVE_TON = 0.1

# --- To'lov rekvizitlari (bo'sh bo'lsa — adminning /karta buyrug'i ishlatiladi)
CARD_NUMBER = '5614 6835 1653 0409'
CARD_OWNER = 'Xamidullayeva mafirat'

# --- TON kursini avtomatik olish ---------------------------------------------
_CACHE = {'t': 0.0, 'v': None}
_CACHE_TTL = 300  # 5 daqiqa


def _fetch_ton_uzs() -> float:
    """TON bozor kursi (so'm): tonapi (TON/USD) * cbu.uz (USD/so'm)."""
    r = requests.get("https://tonapi.io/v2/rates",
                     params={"tokens": "ton", "currencies": "usd"}, timeout=8)
    usd = float(r.json()["rates"]["TON"]["prices"]["USD"])
    c = requests.get("https://cbu.uz/oz/arkhiv-kursov-valyut/json/USD/", timeout=8).json()
    return usd * float(c[0]["Rate"])


def get_ton_uzs(override=None) -> float:
    """1 TON ning sotuv narxi (so'm), marja bilan."""
    if override:
        try:
            return max(float(override), 1.0)
        except (TypeError, ValueError):
            pass
    now = time.time()
    if _CACHE['v'] is None or now - _CACHE['t'] > _CACHE_TTL:
        try:
            _CACHE['v'] = _fetch_ton_uzs()
            _CACHE['t'] = now
        except Exception as e:
            logger.warning("TON kursini olib bo'lmadi (%s) — minimal narx ishlatiladi", e)
            _CACHE['v'] = None
            _CACHE['t'] = now - _CACHE_TTL + 30  # 30 soniyadan keyin qayta urinadi
    if _CACHE['v'] is None:
        return float(MIN_TON_UZS)
    return max(_CACHE['v'] + MARGIN_UZS, float(MIN_TON_UZS))


# --- Narx hisoblash ---------------------------------------------------------
def stars_price(qty: int, rate: float) -> int:
    return int(math.ceil(qty * (TON_PER_50_STARS / 50) * rate))


def premium_price(months: int, rate: float) -> int:
    return int(math.ceil(PREMIUM_TON[months] * rate))


def ton_price(amount: float, rate: float) -> int:
    return int(math.ceil(float(amount) * rate))


def required_ton(kind: str, qty) -> float:
    """Buyurtmani bajarish uchun hamyondan chiqadigan taxminiy TON."""
    if kind == 'stars':
        return int(qty) * (TON_PER_50_STARS / 50)
    if kind == 'premium':
        return PREMIUM_TON[int(qty)]
    if kind == 'ton':
        return float(qty)
    return 0.0


def fmt(n) -> str:
    """12345 -> '12 345'"""
    return f"{int(n):,}".replace(",", " ")
