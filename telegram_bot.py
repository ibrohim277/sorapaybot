"""
config/function.php dagi `Begzod` klassining Python porti.
Har qanday Telegram Bot API metodini dinamik chaqiradi: bot.sendMessage({...})
xuddi PHP'dagi $bot->sendMessage([...]) kabi ishlaydi.
Natija PHP'dagi json_decode($response) (obyekt) uslubida — SimpleNamespace bilan,
shunda `update.message.chat.id` kabi nuqta bilan murojaat qilish mumkin.
"""
import json
import requests
from types import SimpleNamespace

from config.settings import API_URL


def tg_from(obj):
    """obj.from ga mos keladi — 'from' Python'da zahira so'z bo'lgani uchun shu orqali olinadi."""
    return getattr(obj, 'from', None)


def _to_namespace(obj):
    """dict/list larni PHP'dagi stdClass uslubiga o'xshab SimpleNamespace'ga aylantiradi."""
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _to_namespace(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_to_namespace(v) for v in obj]
    return obj


class Begzod:
    def __init__(self, raw_body: bytes = None):
        """raw_body — Flask so'rovining request.get_data() natijasi
        (PHP'dagi file_get_contents('php://input') ga mos)."""
        self._update = None
        if raw_body:
            try:
                decoded = json.loads(raw_body)
                self._update = _to_namespace(decoded)
            except (json.JSONDecodeError, TypeError):
                self._update = None

    def update(self):
        return self._update

    def __getattr__(self, method_name):
        """Har qanday $bot->someMethod([...]) chaqiruvini Telegram API'ga forward qiladi."""
        def _call(params=None):
            return self._request(method_name, params or {})
        return _call

    def _request(self, method: str, params: dict):
        url = API_URL + method
        try:
            resp = requests.post(url, json=params, headers={'Content-Type': 'application/json'}, timeout=15)
        except requests.RequestException:
            return None
        try:
            data = resp.json()
        except ValueError:
            return None
        return _to_namespace(data)
