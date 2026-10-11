"""
Username tekshiruvi (Stars / Premium uchun).

Muammo: Fragment ba'zan MAVJUD username uchun ham «topilmadi» deydi (eskirgan/begona STEL_* cookie'lar,
hash'ning sessiyaga mos kelmasligi). Shuning uchun uning «yo'q» javobiga to'liq ishonib bo'lmaydi.

Tekshiruv tartibi:
  1) Fragment — ANONIM sessiya bilan (cookie'siz; hash va cookie sahifaning o'zidan olinadi),
  2) Fragment — settings'dagi cookie'lar + dinamik hash,  3) Fragment — settings.FRAGMENT_HASH (statik);
     birortasi «topildi» desa — tamom.
  4) Fragment «topildi» demasa (yoki ishlamasa) — Telegram'ning ochiq t.me sahifasi bilan SOLISHTIRILADI:
       t.me «foydalanuvchi bor» desa -> ishoniladi (Fragment xato qilgan), ziddiyat logga yoziladi;
       t.me ham «yo'q» desa -> «topilmadi».
Har bir urinish natijasi `last_trail()` orqali ko'rinadi va /diag da chiqadi.
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
_ANON = {'hash': None, 'cookies': None, 't': 0.0}
_LAST = {}


def last_trail(tag: str = 'stars') -> str:
    return "; ".join(_LAST.get(tag, [])) or "hali tekshirilmagan"


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


def _headers(referer: str) -> dict:
    return {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://fragment.com", "Referer": referer,
        "User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
    }


def _post(h: str, post_data: dict, referer: str, cookies):
    """(data, kind, xato) — kind: found/notfound/bad."""
    try:
        resp = requests.post(f"https://fragment.com/api?hash={h}", data=post_data,
                             headers=_headers(referer), cookies=cookies, timeout=15)
    except requests.RequestException as e:
        return None, 'bad', f"so'rov xatosi: {type(e).__name__}"
    if resp.status_code != 200:
        return None, 'bad', f"HTTP {resp.status_code}"
    try:
        data = resp.json()
    except ValueError:
        return None, 'bad', "JSON emas (hash/cookie eskirgan bo'lishi mumkin)"
    kind = _classify(data)
    return data, kind, (None if kind == 'found' else f"javob: {str(data)[:140]}")


def _anon_session():
    """Cookie'siz sessiya: hash VA cookie'lar sahifaning o'zidan olinadi (10 daqiqa keshlanadi)."""
    now = time.time()
    with _LOCK:
        if _ANON['hash'] and now - _ANON['t'] < _HASH_TTL:
            return _ANON['hash'], _ANON['cookies']
    g = requests.get("https://fragment.com/stars/buy",
                     headers={'User-Agent': UA, 'Accept': 'text/html'}, timeout=15)
    m = HASH_RE.search(getattr(g, 'text', '') or '')
    if not m:
        raise ValueError("sahifada hash topilmadi")
    jar = getattr(g, 'cookies', None)
    cookies = dict(jar) if jar is not None else {}
    with _LOCK:
        _ANON.update(hash=m.group(1), cookies=cookies, t=now)
    return m.group(1), cookies


def _fragment_call(post_data: dict, referer: str, tag: str = 'stars'):
    """(data, None) — data 'found' yoki 'notfound' bo'lishi mumkin (_classify bilan ajratiladi);
    hech biri ishonchli bo'lmasa (None, xato_matni)."""
    trail, found, notfound = [], None, None

    def consider(label, data, kind, err):
        nonlocal found, notfound
        trail.append(f"{label}: {kind}" + (f" ({err})" if err else ""))
        if kind == 'found' and found is None:
            found = data
        elif kind == 'notfound' and notfound is None:
            notfound = data

    # 1) anonim sessiya
    try:
        h, ck = _anon_session()
        consider("anonim", *_post(h, post_data, referer, ck))
    except Exception as e:
        trail.append(f"anonim: bad ({type(e).__name__}: {str(e)[:60]})")
        h = None

    # 2) settings cookie'lari + dinamik hash
    h2 = None
    if found is None:
        h2 = get_hash()
        if h2:
            consider("cookie+dinamik", *_post(h2, post_data, referer, _cookies()))

    # 3) statik hash
    static = getattr(settings, 'FRAGMENT_HASH', '') or ''
    if found is None and static and static not in (h, h2):
        consider("cookie+statik", *_post(static, post_data, referer, _cookies()))

    _LAST[tag] = trail
    if found is not None:
        return found, None
    if notfound is not None:
        return notfound, None
    return None, trail[-1] if trail else "noma'lum xato"


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
def _cross_check(u: str, data, err, what: str) -> dict:
    """Fragment «topildi» demagan holat: t.me bilan solishtirish (Fragment'ning «yo'q»iga ko'r-ko'rona ishonilmaydi)."""
    fragment_nf = data is not None
    if fragment_nf:
        logger.warning("[Fragment] %s: «topilmadi» dedi (%s) — t.me bilan solishtiriladi. Urinishlar: %s",
                       what, str(data)[:140], last_trail('stars'))
    else:
        logger.warning("[Fragment] %s: ishlamadi (%s) — t.me orqali tekshiriladi", what, err)
    t = _tme_check(u)
    if t.get('exists'):
        if fragment_nf:
            logger.warning("[Fragment] ZIDDIYAT: Fragment «topilmadi», t.me «mavjud» (@%s) -> t.me ishoniladi. "
                           "Fragment sessiyasi (STEL_*/hash) eskirgan bo'lishi mumkin.", u)
        return t
    if 'error' in t and fragment_nf:
        return {'exists': False, 'username': u, 'source': 'fragment',
                'message': 'Username topilmadi yoki noto\u2018g\u2018ri'}
    return t


def chekusername(username: str) -> dict:
    """Stars uchun username mavjudligini tekshirish."""
    u = (username or '').lstrip('@').strip()
    data, err = _fragment_call({'query': u, 'method': 'searchStarsRecipient'},
                               "https://fragment.com/stars/buy", 'stars')
    if data is not None and _classify(data) == 'found':
        found = data['found']
        return {'exists': True, 'username': u, 'recipient': found['recipient'],
                'name': found.get('name', u), 'avatar': found.get('avatar'), 'source': 'fragment'}
    return _cross_check(u, data, err, "searchStarsRecipient")


def chekPremiumUsername(username: str, months: int = 12) -> dict:
    """Premium sovg'a qilish mumkinligini tekshirish (allaqachon Premium bo'lsa — has_premium)."""
    u = (username or '').lstrip('@').strip()
    data, err = _fragment_call({'query': u, 'months': int(months), 'method': 'searchPremiumGiftRecipient'},
                               "https://fragment.com/premium/gift", 'premium')
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
    r = _cross_check(u, data, err, "searchPremiumGiftRecipient")
    if r.get('exists'):
        r['has_premium'] = False   # Premium holatini faqat Fragment biladi; buyurtma bajarilganda aniqlanadi
    return r
