# SoraPayBot (Python porti)

Telegram Stars / Premium / Gift / TON sotib olish boti.
Asl loyiha PHP'da yozilgan edi; bu — Python/Flask'ga o'tkazilgan versiyasi.

## ⚠️ Hozirgi holat (muhim!)

Bu loyiha **hali to'liq tugallanmagan**. Quyidagilar yozildi va **real test
qilindi** (Flask test client orqali, soxta Telegram update'lar bilan):

- ✅ `config/channel_db.py` + `channel_sql.py` + `channel_pdo.py` — ChannelDB
  dvigateli (Telegram kanalni "baza" sifatida ishlatish). Asl PHP versiyasida
  topilgan barcha bug'lar (LIMIT ishlamasligi, `WHERE 1=1` doim yolg'on
  chiqishi, `INSERT ... SET` tushunilmasligi) shu yerda tuzatilgan.
- ✅ `telegram_bot.py` — Telegram Bot API umumiy wrapper.
- ✅ `main.py` — webhook, majburiy obuna tekshiruvi, oddiy va referal+captcha
  orqali ro'yxatdan o'tish.
- ✅ `BuyTon/`, `BuyStars/` — TON yuborish va Fragment.com orqali Stars/Premium
  sotib olish skriptlari (asl kod ham Python edi, ko'chirildi).

**Hali yozilmagan:** bot ichidagi Stars/Premium/Gift/TON xarid **suhbat
oqimi** (tugmalar bosilganda), captcha tekshirish handleri, referal/profil/
statistika bo'limlari, admin panel, TON to'lov webhook'i, mini-app API.

## ⚠️ Sozlamalar haqida — MUHIM

`config/settings.py` ichidagi barcha qiymatlar **to'g'ridan-to'g'ri kodga
yozilgan** (hardcoded), chunki bu repo **private**. Environment variable
kiritish shart emas.

**Lekin quyidagi 2 ta qiymat asl kodingizda ham bo'sh edi — bular hali ham
bo'sh, botni ishga tushirishdan oldin `config/settings.py` faylini ochib
qo'lingiz bilan to'ldiring:**

```python
BOT_TOKEN = ''   # BotFather'dan olasiz
MNEMONIC = ''    # hamyoningizning 24 so'zlik maxfiy iborasi
```

`TONAPI_KEY` ham bo'sh, lekin hozircha kodda ishlatilmayapti (TON webhook
qismi hali yozilmagan), shuning uchun shoshilinch emas.

Qolgan hammasi (`ADMIN_ID`, `LOG_CHANNEL_ID`, `DB_CHANNEL_ID`, `API_TON`,
`FRAGMENT_*`, `STEL_*`) — asl kodingizdagi haqiqiy qiymatlar bilan allaqachon
to'ldirilgan.

> Eslatma: repo private bo'lsa ham, bu qiymatlar (ayniqsa `API_TON` va
> `STEL_*` sessiya token'lari) amaldagi kalitlar — tokenga ega bo'lgan har
> qanday hamkor yoki xizmat (masalan GitHub xodimlari, CI/CD integratsiyasi)
> nazariy jihatdan ularni ko'rishi mumkinligini yodda tuting.

## Loyiha tuzilishi

```
config/
  settings.py        — barcha sozlamalar (hardcoded)
  channel_db.py       — ChannelDB: Telegram kanalga asoslangan saqlash qatlami
  channel_sql.py       — mini SQL-parser (SELECT/INSERT/UPDATE/DELETE)
  channel_pdo.py       — admin panel uchun PDO-ga o'xshash qatlam
  username_info.py     — Fragment.com orqali username tekshirish
telegram_bot.py         — Telegram Bot API umumiy wrapper
main.py                  — Flask webhook (asosiy bot handleri)
BuyTon/main.py           — TON yuborish (tonutils)
BuyStars/                — Fragment.com orqali Stars/Premium sotib olish
requirements.txt, Procfile, render.yaml, runtime.txt — deploy fayllari
```

## Lokalda ishga tushirish

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# config/settings.py ichida BOT_TOKEN va MNEMONIC'ni to'ldiring

python3 main.py
# yoki production uslubida:
gunicorn main:app --bind 0.0.0.0:8080
```

## Render.com'ga deploy qilish

### Blueprint (`render.yaml`) orqali — eng oson

1. Render Dashboard → **New** → **Blueprint**.
2. Shu GitHub repo'ni tanlang (`muslihiddinlive/sorapay`).
3. Render `render.yaml`ni o'qib, xizmatni avtomatik sozlaydi — environment
   variable kiritish **shart emas** (hammasi kodda).
4. **Deploy**ni bosing.
5. Deploy tugagach, Render sizga URL beradi (masalan
   `https://sorapay.onrender.com` yoki boshqa, agar nom band bo'lsa). Agar bu
   `config/settings.py`dagi `BASE_URL` bilan **bir xil bo'lmasa**, shu faylda
   `BASE_URL`ni to'g'ri qiymatga almashtirib, qayta push qiling.

### Qo'lda Web Service

1. Render Dashboard → **New** → **Web Service** → shu repo'ni tanlang.
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `gunicorn main:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60`
4. Deploy qiling (environment variable kerak emas).

### Webhookni o'rnatish

Bot kodi har bir so'rovda o'zi `setWebhook` chaqiradi (`BASE_URL` orqali),
shuning uchun `BASE_URL` to'g'ri bo'lsa, webhook avtomatik o'rnatiladi.
Tekshirish: `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`

### ⚠️ Free tarif haqida

- Fayl tizimi doimiy emas (har restart'da tozalanadi) — muammo emas, chunki
  `ChannelDB` Telegram kanalidagi zaxiradan o'zi tiklanadi. Faqat `step/`
  papkasidagi vaqtinchalik holat (masalan hali yechilmagan captcha)
  yo'qolishi mumkin — foydalanuvchi qayta `/start` bossa yetarli.
- 15 daqiqa harakatsizlikdan keyin "uxlab qoladi" (cold start sekinroq bo'ladi).
# sorapaybot
