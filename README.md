# SoraPayBot (Python porti)

Telegram Stars / Premium / Gift / TON sotib olish boti.
Asl loyiha PHP'da yozilgan edi (`channel_db.php` + `index.php` + `admin/*`);
bu — o'sha loyihaning Python/Flask'ga o'tkazilgan versiyasi.

## ⚠️ Hozirgi holat (muhim!)

Bu loyiha **hali to'liq tugallanmagan**. Quyidagilar yozildi va **real test
qilindi** (Flask test client orqali, soxta Telegram update'lar bilan):

- ✅ `config/channel_db.py` + `config/channel_sql.py` + `config/channel_pdo.py`
  — ChannelDB dvigateli (Telegram kanalni "baza" sifatida ishlatish). Asl
  PHP versiyasida topilgan barcha bug'lar (LIMIT ishlamasligi, `WHERE 1=1`
  doim yolg'on chiqishi, `INSERT ... SET` tushunilmasligi) shu yerda
  **tuzatilgan holda** portlangan.
- ✅ `telegram_bot.py` — Telegram Bot API bilan ishlash uchun umumiy wrapper.
- ✅ `main.py` — webhook kirish nuqtasi, obunani majburiy tekshirish
  (`majburiy()` / `check()` / `Tugma_Edit()`), oddiy va referal orqali
  ro'yxatdan o'tish (captcha bilan).

**Hali yozilmagan:** Stars/Premium/Gift/TON xarid oqimlari, captcha
tekshirish handleri, referal/profil/statistika bo'limlari, admin panel
(`admin/admin.php`, `admin/api.php`), TON to'lov webhook'i
(`Ton_webhook.php`), mini-app API (`web/api/*`).

Botni productionda **to'liq** ishlatishdan oldin, shu qolgan qismlar ham
yozilishi kerak — hozircha botga `/start` yozish, obuna tekshiruvi va
ro'yxatdan o'tish ishlaydi, lekin "Stars olish" kabi tugmalar hali javob
bermaydi.

## Loyiha tuzilishi

```
config/
  settings.py       — barcha sozlamalar (environment variable'lardan o'qiydi)
  channel_db.py      — ChannelDB: Telegram kanalga asoslangan saqlash qatlami
  channel_sql.py      — mini SQL-parser (SELECT/INSERT/UPDATE/DELETE)
  channel_pdo.py      — admin panel uchun PDO-ga o'xshash qatlam
  username_info.py    — Fragment.com orqali username tekshirish
telegram_bot.py        — Telegram Bot API umumiy wrapper
main.py                 — Flask webhook (asosiy bot handleri)
requirements.txt, Procfile, render.yaml, runtime.txt — deploy fayllari
```

## Lokalda ishga tushirish

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env faylini to'ldiring: BOT_TOKEN, BASE_URL va h.k.

python3 main.py
# yoki production uslubida:
gunicorn main:app --bind 0.0.0.0:8080
```

Keyin ngrok yoki shunga o'xshash tunnel orqali webhookni sozlang, yoki
to'g'ridan-to'g'ri Render'ga deploy qiling (pastga qarang).

## Render.com'ga deploy qilish

### 1-usul — Blueprint (`render.yaml`) orqali, eng oson

1. Render Dashboard → **New** → **Blueprint**.
2. Shu GitHub repo'ni tanlang (`muslihiddinlive/sorapay`).
3. Render `render.yaml`ni o'qib, xizmatni avtomatik sozlaydi.
4. **Environment** bo'limida quyidagilarni qo'ling (`sync: false` bo'lgani
   uchun bular qo'lda kiritiladi):
   - `BOT_TOKEN` — BotFather'dan olingan token
   - `BASE_URL` — Render sizga bergan URL, masalan `https://sorapay.onrender.com`
     (birinchi deploy'dan keyin paydo bo'ladi, keyin shuni kiritib qayta deploy qiling)
   - `DB_CHANNEL_ID`, `ADMIN_ID`, `LOG_CHANNEL_ID`, `TONAPI_KEY`
5. **Deploy** tugmasini bosing.

### 2-usul — qo'lda Web Service

1. Render Dashboard → **New** → **Web Service** → shu repo'ni tanlang.
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `gunicorn main:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60`
4. Yuqoridagi environment variable'larni qo'lda kiriting.
5. Deploy qiling.

### Webhookni o'rnatish

Bot kodi har bir so'rovda o'zi `setWebhook` chaqiradi (`BASE_URL` orqali),
shuning uchun `BASE_URL`ni to'g'ri kiritib qayta deploy qilsangiz, webhook
avtomatik o'rnatiladi. Tekshirish uchun:

```
https://api.telegram.org/bot<TOKEN>/getWebhookInfo
```

### ⚠️ Free tarif haqida muhim eslatma

- Render **Free** tarifida fayl tizimi **doimiy emas** — har deploy/restart'da
  tozalanadi. Bu katta muammo emas, chunki `ChannelDB` lokal fayl topilmasa
  Telegram kanalidagi zaxiradan **o'zi tiklanadi** (`channel_db.py` dagi
  `_load_table`/`_load_index` shuning uchun yozilgan). Faqat `step/` papkasidagi
  vaqtinchalik holat (masalan hali yechilmagan captcha xabari) restart paytida
  yo'qolishi mumkin — foydalanuvchi shunchaki qayta `/start` bossa yetarli.
- Free tarif 15 daqiqa harakatsizlikdan keyin "uxlab qoladi" — birinchi so'rov
  sekinroq (cold start) keladi. Agar bu muammo bo'lsa, Starter tarifga o'ting
  yoki tashqi "ping" xizmati bilan uni uyg'oq tutib turing.

## Environment Variable'lar ro'yxati

| Nomi | Tavsif |
|---|---|
| `BOT_TOKEN` | BotFather'dan olingan bot tokeni |
| `BASE_URL` | Botning public URL manzili (webhook + ichki fayl so'rovlari uchun) |
| `DB_CHANNEL_ID` | ChannelDB uchun private kanal ID (`-100...`) |
| `ADMIN_ID` | Admin Telegram user ID |
| `LOG_CHANNEL_ID` | Log kanal ID |
| `TONAPI_KEY` | tonapi.io API kaliti |
| `DEBUG` | `1`/`0` |
