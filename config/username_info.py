"""
config/username_info.php ning Python porti.
Fragment.com kalitlari endi config/settings.py (environment variable'lar)
orqali yagona manbadan olinadi — BuyStars/BuyTon bilan bir xil.
"""
import requests

from config import settings


def chekusername(username: str) -> dict:
    """Username mavjudligini tekshirish (Stars uchun)."""
    url = f"https://fragment.com/api?hash={settings.FRAGMENT_HASH}"
    post_data = {'query': username, 'method': 'searchStarsRecipient'}
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://fragment.com",
        "Referer": "https://fragment.com/stars/buy",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "X-Requested-With": "XMLHttpRequest",
    }
    cookie_header = '; '.join(f"{k}={v}" for k, v in settings.FRAGMENT_COOKIES.items())
    headers["Cookie"] = cookie_header

    try:
        resp = requests.post(url, data=post_data, headers=headers, timeout=15)
    except requests.RequestException as e:
        return {'error': f"So'rov xatosi: {e}"}

    if resp.status_code != 200:
        return {'error': f"HTTP Error: {resp.status_code}"}

    try:
        data = resp.json()
    except ValueError:
        return {'error': 'JSON parse xatosi'}

    found = data.get('found')
    if isinstance(found, dict) and found.get('recipient'):
        return {
            'exists': True,
            'username': username,
            'recipient': found['recipient'],
            'name': found.get('name', username),
            'avatar': found.get('avatar'),
        }

    return {
        'exists': False,
        'username': username,
        'message': 'Username topilmadi yoki noto\u2018g\u2018ri',
    }


def chekPremiumUsername(username: str, months: int = 12) -> dict:
    """Premium sovg'a qilish mumkinligini tekshirish
    (agar foydalanuvchida allaqachon Premium obunasi bo'lsa, xatolik qaytaradi)."""
    url = f"https://fragment.com/api?hash={settings.FRAGMENT_HASH}"
    post_data = {
        'query': username,
        'months': int(months),
        'method': 'searchPremiumGiftRecipient',
    }
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://fragment.com",
        "Referer": "https://fragment.com/premium/gift",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "X-Requested-With": "XMLHttpRequest",
    }
    cookie_header = '; '.join(f"{k}={v}" for k, v in settings.FRAGMENT_COOKIES.items())
    headers["Cookie"] = cookie_header

    try:
        resp = requests.post(url, data=post_data, headers=headers, timeout=15)
    except requests.RequestException as e:
        return {'error': f"So'rov xatosi: {e}"}

    if resp.status_code != 200:
        return {'error': f"HTTP Error: {resp.status_code}"}

    try:
        data = resp.json()
    except ValueError:
        return {'error': 'JSON parse xatosi'}

    err = data.get('error')
    if isinstance(err, str) and 'already subscribed' in err:
        return {
            'exists': True,
            'has_premium': True,
            'username': username,
            'message': 'Bu akkaunt allaqachon Telegram Premium obunasiga ega.',
        }

    found = data.get('found')
    if isinstance(found, dict) and found.get('recipient'):
        return {
            'exists': True,
            'has_premium': False,
            'username': username,
            'recipient': found['recipient'],
            'name': found.get('name', username),
            'avatar': found.get('avatar') or found.get('photo'),
            'message': 'Premium sovg\u2018a qilish mumkin.',
        }

    return {
        'exists': False,
        'has_premium': False,
        'username': username,
        'message': data.get('error', 'Username topilmadi yoki Premium sovg\u2018a qilish imkoni yo\u2018q.'),
    }
