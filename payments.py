"""
tolov.go to'lov tizimi mijozi (sozlamalar: config/payment_settings.py).

⚠️ tolov.go ning rasmiy hujjati topilmadi, shuning uchun so'rov/javob formati umumiy REST namunasiga
asoslangan va config/payment_settings.py orqali moslanadi. Haqiqiy servisda SINALMAGAN.

Xavfsizlik qoidasi: webhook/tugma "to'landi" desa ham, bot BARIBIR gateway'ning holat API'sidan
qayta so'rab tasdiqlaydi (soxta webhook bilan bepul xarid qilib bo'lmasin).
"""
import hmac
import hashlib
import logging

import requests

from config import settings
from config import payment_settings as PS

logger = logging.getLogger("sorapay.payments")


class PaymentError(Exception):
    pass


def enabled() -> bool:
    return bool(str(PS.TOLOV_API_URL).strip() and str(PS.TOLOV_API_KEY).strip())


# ---------------------------------------------------------------- webhook xavfsizligi
def webhook_secret() -> str:
    if str(PS.TOLOV_WEBHOOK_SECRET).strip():
        return str(PS.TOLOV_WEBHOOK_SECRET).strip()
    return hashlib.sha256((settings.BOT_TOKEN + ':tolov-webhook').encode()).hexdigest()[:24]


def webhook_url() -> str:
    return f"{settings.BASE_URL.rstrip('/')}/tolov/webhook?secret={webhook_secret()}"


def check_secret(given: str) -> bool:
    return hmac.compare_digest(str(given or ''), webhook_secret())


# ---------------------------------------------------------------- HTTP
def _http(method: str, url: str, **kw):
    return requests.request(method, url, timeout=15, **kw)


def _headers() -> dict:
    return {PS.TOLOV_AUTH_HEADER: f"{PS.TOLOV_AUTH_PREFIX}{PS.TOLOV_API_KEY}",
            'Accept': 'application/json'}


def _base() -> str:
    return str(PS.TOLOV_API_URL).rstrip('/')


def _dig(data, keys):
    """Javobning yuqori darajasidan, so'ng 'data'/'result'/... ichidan birinchi mos qiymatni topadi."""
    if not isinstance(data, dict):
        return None
    scopes = [data] + [data[k] for k in ('data', 'result', 'payload', 'invoice') if isinstance(data.get(k), dict)]
    for scope in scopes:
        for k in keys:
            v = scope.get(k)
            if v not in (None, ''):
                return v
    return None


def _json(resp, what: str) -> dict:
    if resp.status_code >= 400:
        raise PaymentError(f"{what}: HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        raise PaymentError(f"{what}: javob JSON emas")
    if not isinstance(data, dict):
        raise PaymentError(f"{what}: kutilmagan javob")
    return data


# ---------------------------------------------------------------- ochiq API
def create_invoice(order_id, amount_uzs: int, description: str) -> dict:
    """{'pay_url': ..., 'invoice_id': ...} qaytaradi yoki PaymentError ko'taradi."""
    values = {
        'amount': int(round(int(amount_uzs) * PS.TOLOV_AMOUNT_MULTIPLIER)),
        'order_id': str(order_id),
        'description': description,
        'callback_url': webhook_url(),
        'return_url': settings.BASE_URL,
    }
    body = {api_name: values[our] for our, api_name in PS.TOLOV_CREATE_FIELDS.items() if our in values}
    try:
        resp = _http('POST', _base() + PS.TOLOV_CREATE_PATH, json=body, headers=_headers())
    except requests.RequestException as e:
        raise PaymentError(f"tarmoq xatosi: {type(e).__name__}")
    data = _json(resp, "hisob yaratish")
    pay_url = _dig(data, PS.TOLOV_PAY_URL_KEYS)
    invoice_id = _dig(data, PS.TOLOV_INVOICE_ID_KEYS)
    if not pay_url or not str(pay_url).startswith(('http://', 'https://')):
        logger.error("[tolov] to'lov havolasi topilmadi. Javob kalitlari: %s", list(data.keys()))
        raise PaymentError("javobda to'lov havolasi topilmadi (config/payment_settings.py dagi TOLOV_PAY_URL_KEYS ni tekshiring)")
    if not invoice_id:
        logger.error("[tolov] hisob raqami topilmadi. Javob kalitlari: %s", list(data.keys()))
        raise PaymentError("javobda hisob raqami topilmadi (TOLOV_INVOICE_ID_KEYS ni tekshiring)")
    return {'pay_url': str(pay_url), 'invoice_id': str(invoice_id)}


def is_paid(invoice_id) -> bool:
    """Gateway'dan holatni so'rab, to'langanmi-yo'qmi aniqlaydi (xato bo'lsa PaymentError)."""
    url = _base() + PS.TOLOV_STATUS_PATH.replace('{id}', str(invoice_id))
    try:
        resp = _http(PS.TOLOV_STATUS_METHOD.upper(), url, headers=_headers())
    except requests.RequestException as e:
        raise PaymentError(f"tarmoq xatosi: {type(e).__name__}")
    data = _json(resp, "holatni tekshirish")
    if _dig(data, ('paid',)) is True:
        return True
    status = _dig(data, PS.TOLOV_STATUS_KEYS)
    return str(status).strip().lower() in {v.lower() for v in PS.TOLOV_PAID_VALUES}


def extract_ids(payload: dict):
    """Webhook tanasidan (bizning_buyurtma_id, gateway_hisob_id) ni topadi."""
    order = _dig(payload, PS.TOLOV_WEBHOOK_ORDER_KEYS)
    invoice = _dig(payload, PS.TOLOV_WEBHOOK_INVOICE_KEYS)
    return (str(order) if order is not None else None, str(invoice) if invoice is not None else None)
