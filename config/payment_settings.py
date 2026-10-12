"""
tolov.go TO'LOV TIZIMI sozlamalari — SHU YERNI O'ZINGIZ TO'LDIRING.

Ikki qiymat bo'sh bo'lsa — to'lov tizimi O'CHIQ: bot eski usulda ishlaydi (karta + chek rasmi + admin tasdig'i).
Ikkalasi to'ldirilsa — mijozga avtomatik to'lov havolasi beriladi, to'lov kelishi bilan buyurtma
ADMIN TASDIQLAMASDAN bajariladi.

⚠️ Kalitni git'ga yozmaslik uchun Render → Environment'ga qo'yish tavsiya etiladi:
    TOLOV_API_URL, TOLOV_API_KEY  (pastdagi os.environ.get qatorlari ularni o'zi oladi)
"""
import os

# >>> tolovgo saytidan olgan API URL va KEY'ni SHU YERGA O'ZINGIZ yozing (qo'shtirnoq ichiga). <<<
# Ikkalasi ham BO'SH bo'lsa  -> karta + chek rasmi (admin tasdig'i) rejimi ishlaydi.
# Ikkalasi ham TO'LDIRILSA  -> tolovgo orqali avtomatik to'lov ishlaydi.
# (Xohlasangiz Render > Environment'ga TOLOV_API_URL / TOLOV_API_KEY qo'ysangiz ham bo'ladi — u ustun turadi.)
TOLOV_API_URL_VALUE = ''   # masalan: 'https://api.sayt.uz'  (oxirida "/" bo'lmasin)
TOLOV_API_KEY_VALUE = ''

TOLOV_API_URL = os.environ.get('TOLOV_API_URL', '').strip() or TOLOV_API_URL_VALUE
TOLOV_API_KEY = os.environ.get('TOLOV_API_KEY', '').strip() or TOLOV_API_KEY_VALUE

# Gateway to'lovni bildirganda chaqiradigan manzil maxfiy kaliti. Bo'sh bo'lsa BOT_TOKEN dan avtomatik hosil bo'ladi.
TOLOV_WEBHOOK_SECRET = os.environ.get('TOLOV_WEBHOOK_SECRET', '')

# ---------------------------------------------------------------------------
# So'rov formati. ⚠️ Bular TAXMINIY (umumiy REST namunasi) — tolov.go hujjati topilmadi.
# Hujjat boshqacha bo'lsa, KODNI EMAS, faqat shu qiymatlarni o'zgartiring.
# ---------------------------------------------------------------------------
TOLOV_AUTH_HEADER = 'Authorization'      # kalit yuboriladigan sarlavha (masalan 'X-API-KEY')
TOLOV_AUTH_PREFIX = 'Bearer '            # kalit oldidan prefiks ('' bo'lishi ham mumkin)

TOLOV_CREATE_PATH = '/invoice/create'    # hisob-faktura yaratish (POST, JSON)
TOLOV_STATUS_PATH = '/invoice/{id}'      # holatni tekshirish; {id} = gateway'dagi hisob raqami
TOLOV_STATUS_METHOD = 'GET'              # 'GET' yoki 'POST'

TOLOV_AMOUNT_MULTIPLIER = 1              # so'm uchun 1, tiyin talab qilinsa 100

# Bizning nom -> gateway so'rovidagi maydon nomi (keraksizini o'chirib tashlang)
TOLOV_CREATE_FIELDS = {
    'amount': 'amount',
    'order_id': 'order_id',
    'description': 'description',
    'callback_url': 'callback_url',
    'return_url': 'return_url',
}

# Gateway javobidan kerakli qiymatlarni topish uchun mumkin bo'lgan kalitlar (birinchisi topilgani olinadi)
TOLOV_PAY_URL_KEYS = ('pay_url', 'payment_url', 'checkout_url', 'url', 'link')
TOLOV_INVOICE_ID_KEYS = ('invoice_id', 'id', 'uuid', 'transaction_id')
TOLOV_STATUS_KEYS = ('status', 'state')
TOLOV_PAID_VALUES = ('paid', 'success', 'succeeded', 'completed', 'done', 'confirmed', 'approved')

# Webhook tanasida buyurtma/hisob raqamini topish uchun kalitlar
TOLOV_WEBHOOK_ORDER_KEYS = ('order_id', 'merchant_order_id', 'external_id')
TOLOV_WEBHOOK_INVOICE_KEYS = ('invoice_id', 'id', 'uuid', 'transaction_id')
