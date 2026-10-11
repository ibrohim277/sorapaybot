"""
Username tekshiruvi (Stars / Premium uchun).

Eski kod Fragment'ga FRAGMENT_HASH + STEL_* cookie'lari bilan tayanardi. Bular boshqa odamning
sessiyasidan qolgan va tez eskiradi — shu sabab tekshiruv ishlamay qolgan. Endi:

  1) Fragment `hash` ni sahifaning o'zidan avtomatik oladi (10 daqiqa keshlanadi),
     olinmasa settings.FRAGMENT_HASH ga qaytadi;
  2) Fragment javobi tushunarsiz/xato bo'lsa (hash/cookie eskirgan, sayt javob bermadi) —
     username'ni Telegram'ning ochiq t.me sahifasi orqali tekshiradi;
  3) Faqat IKKALASI ham ishlamasa {'error': ...} qaytaradi.

Fragment/t.me javobining haqiqiy ko'rinishini bu yerda sinab bo'lmadi (internet yo'q) — shuning uchun
barcha qadamlar himoyalangan va sabablar logga yoziladi ([Fragment] ...). `/diag` ham ko'rsatadi.
"""
import re
import time
import logging
import threading

import requests

from config import settings

logger = logging.getLogger("sorapay.fragment")

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1")
HASH_RE = re.compile(r'api\?hash=([0-9a-fA-F]{8,})')
_AUTH_WORDS = ('hash', 'auth', 'login', 'access denied', 'session', 'expired', 'unauthorized')

_HASH = {'v': None, 't': 0.0}
_HASH_TTL = 600
_LOCK = threading.Lock()


def _cookies() -> dict:
    return dict(getattr(settings, 'FRAGMENT_COOKIES', {}) or {})


# ----------------------------------------------------------------------- hash
def _fetch_dynamic_hash():
    r = requests.get("https://fragment.com/stars/buy",
                     headers={'User-Agent': UA, 'Accept': 'text/html'},
                     cookies=_cookies(), timeout=15)
    m = HASH_RE.search(r.text or '')
    return m.group(1) if m else None


def get_hash(force: bool = False) -> str:
    """Fragment API hash'i: avval sahifadan (dinamik), bo'lmasa settings'dan."""
    now = time.time()
    with _LOCK:
        if not force and _HASH['v'] and now - _HASH['t'] < _HASH_TTL:
            return _HASH['v']
        try:
            h = _fetch_dynamic_hash()
        except Exception as e:
            logger.warning("[Fragment] hash'ni sahifadan olib bo'lmadi: %s", type(e).__name__)
            h = None
        if h:
            _HASH['v'], _HASH['t'] = h, now
            return h
        _HASH['v'], _HASH['t'] = None, now - _HASH_TTL + 60   # 1 daqiqadan keyin qayta uriniladi
        return getattr(settings, 'FRAGMENT_HASH', '') or ''


def get_api_url() -> str:
    return f"https://fragment.com/api?hash={get_hash()}"


def hash_source() -> str:
    return 'dinamik (sahifadan)' if _HASH['v'] else "settings.FRAGMENT_HASH (statik)"


# ------------------------------------------------------------------- Fragment
def _classify(data) -> str:
    """'found' | 'notfound' | 'bad' — Fragment javobi ishonchli talqin qilinadimi."""
    if not isinstance(data, dict):
        return 'bad'
    found = data.get('found')
    if isinstance(found, dict) and found.get('recipient'):
        return 'found'
    err = data.get('error')
    if isinstance(err, str) and any(w in err.lower() for w in _AUTH_WORDS):
        return 'bad'
    if 'found' in data or isinstance(err, str):
        return 'notfound'
    return 'bad'


def _fragment_call(post_data: dict, referer: str):
    """(data, None) yoki (None, xato_matni). data — ishonchli talqin qilingan javob."""
    hashes = [get_hash()]
    static = getattr(settings, 'FRAGMENT_HASH', '') or ''
    if static and static not in hashes:
        hashes.append(static)
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://fragment.com", "Referer": referer,
        "User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
    }
    last = "noma'lum xato"
    for h in hashes:
        try:
            resp = requests.post(f"https://fragment.com/api?hash={h}", data=post_data,
                                 headers=headers, cookies=_cookies(), timeout=15)
        except requests.RequestException as e:
            last = f"so'rov xatosi: {type(e).__name__}"
            continue
        if resp.status_code != 200:
            last = f"HTTP {resp.status_code}"
            continue
        try:
            data = resp.json()
        except ValueError:
            last = "JSON emas (hash/cookie eskirgan bo'lishi mumkin)"
            continue
        if _classify(data) == 'bad':
            last = f"tushunarsiz javob: {str(data)[:120]}"
            continue
        return data, None
    return None, last


# ------------------------------------------------------------ Telegram (zaxira)
def _tme_check(username: str) -> dict:
    """t.me ochiq sahifasi orqali tekshirish. Fragment ishlamaganda zaxira sifatida."""
    if username.lower().endswith('bot'):
        return {'exists': False, 'username': username, 'message': "Bu bot username'iga o'xshaydi."}
    try:
        r = requests.get(f"https://t.me/{username}", headers={'User-Agent': UA}, timeout=10)
    except requests.RequestException as e:
        return {'error': f"Tekshirib bo'lmadi: {type(e).__name__}"}
    if r.status_code != 200:
        return {'error': f"t.me HTTP {r.status_code}"}
    html = r.text or ''
    title = re.search(r'class="tgme_page_title"[^>]*>\s*(?:<span[^>]*>)?\s*([^<]+)', html)
    extra = re.search(r'class="tgme_page_extra"[^>]*>([^<]*)', html)
    extra_text = (extra.group(1) if extra else '').lower()
    if not title:
        return {'exists': False, 'username': username, 'source': 'telegram',
                'message': "Username topilmadi."}
    if 'subscriber' in extra_text or 'member' in extra_text:
        return {'exists': False, 'username': username, 'source': 'telegram',
                'message': "Bu kanal yoki guruh — Stars/Premium faqat foydalanuvchiga yuboriladi."}
    return {'exists': True, 'username': username, 'name': title.group(1).strip(), 'source': 'telegram'}


# ------------------------------------------------------------------ ochiq API
def chekusername(username: str) -> dict:
    """Stars uchun username mavjudligini tekshirish."""
    u = (username or '').lstrip('@').strip()
    data, err = _fragment_call({'query': u, 'method': 'searchStarsRecipient'},
                               "https://fragment.com/stars/buy")
    if data is not None:
        found = data.get('found')
        if isinstance(found, dict) and found.get('recipient'):
            return {'exists': True, 'username': u, 'recipient': found['recipient'],
                    'name': found.get('name', u), 'avatar': found.get('avatar'), 'source': 'fragment'}
        return {'exists': False, 'username': u, 'source': 'fragment',
                'message': 'Username topilmadi yoki noto\u2018g\u2018ri'}
    logger.warning("[Fragment] searchStarsRecipient ishlamadi (%s) -> Telegram orqali tekshiriladi", err)
    return _tme_check(u)


def chekPremiumUsername(username: str, months: int = 12) -> dict:
    """Premium sovg'a qilish mumkinligini tekshirish (allaqachon Premium bo'lsa — has_premium)."""
    u = (username or '').lstrip('@').strip()
    data, err = _fragment_call({'query': u, 'months': int(months), 'method': 'searchPremiumGiftRecipient'},
                               "https://fragment.com/premium/gift")
    if data is not None:
        e = data.get('error')
        if isinstance(e, str) and 'already subscribed' in e:
            return {'exists': True, 'has_premium': True, 'username': u, 'source': 'fragment',
                    'message': 'Bu akkaunt allaqachon Telegram Premium obunasiga ega.'}
        found = data.get('found')
        if isinstance(found, dict) and found.get('recipient'):
            return {'exists': True, 'has_premium': False, 'username': u, 'recipient': found['recipient'],
                    'name': found.get('name', u), 'avatar': found.get('avatar') or found.get('photo'),
                    'source': 'fragment', 'message': 'Premium sovg\u2018a qilish mumkin.'}
        return {'exists': False, 'has_premium': False, 'username': u, 'source': 'fragment',
                'message': e if isinstance(e, str) else 'Username topilmadi yoki Premium sovg\u2018a qilish imkoni yo\u2018q.'}
    logger.warning("[Fragment] searchPremiumGiftRecipient ishlamadi (%s) -> Telegram orqali tekshiriladi", err)
    r = _tme_check(u)
    if r.get('exists'):
        r['has_premium'] = False   # Premium holatini faqat Fragment biladi; buyurtma bajarilganda aniqlanadi
    return r
