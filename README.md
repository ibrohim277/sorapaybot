# SoraPayBot (Python porti)

Telegram Stars / Premium / Gift / TON sotib olish boti.
Asl loyiha PHP'da yozilgan edi; bu — Python/Flask'ga o'tkazilgan versiyasi.

## Hozirgi holat

Ishlaydi (soxta Telegram update'lar bilan 55 ta tekshiruvdan o'tgan):

- ✅ Majburiy obuna, ro'yxatdan o'tish, referal + captcha
- ✅ **Stars / Premium / TON / Gift xaridi** (`orders.py`)
- ✅ Profilim, Statistikam, Referal bo'limlari (`handlers.py`)
- ✅ Admin buyruqlari: `/karta`, `/kurs`, `/narx`, `/buyurtmalar`

**Hali yozilmagan:** admin panel, Payme avtomatik to'lovi (hozir karta + chek),
TON to'lov webhook'i, mini-app API.

## Xarid qanday ishlaydi

1. Mijoz xizmat va miqdorni tanlaydi, qabul qiluvchini kiritadi (@username / TON hamyon / ID).
2. Bot narxni ko'rsatadi, mijoz tasdiqlaydi → buyurtma `#N` yaratiladi.
3. Mijoz kartaga to'laydi va **chek rasmini** botga yuboradi.
4. Chek **adminga** (`ADMIN_ID`) ✅/❌ tugmalari bilan boradi.
5. Admin ✅ bossa, buyurtma **fonda avtomatik bajariladi**:
   - Stars / Premium → Fragment.com orqali (`BuyStars/`)
   - TON → hamyondan yuborish (`BuyTon/`)
   - Gift → Bot API `sendGift` (botning o'z **Stars balansidan**)
6. Natija mijozga va adminga xabar qilinadi. Xato bo'lsa, adminda 🔁 «Qayta urinish» tugmasi chiqadi.

Admin o'zi uchun xarid qilsa, to'lov/chek so'ralmaydi — to'g'ridan-to'g'ri hamyondan bajariladi.

### Ishga tushirishdan oldin

1. `config/settings.py`: `BOT_TOKEN` va `MNEMONIC` (hamyonda yetarli TON bo'lsin).
2. Admin bir marta botga `/start` bossin (aks holda bot adminga xabar yubora olmaydi).
3. Botda admin sifatida: `/karta 8600123412341234 Ism Familiya`
4. Narxlarni tekshiring: `/narx` (formulalar va marja — `config/pricing.py`).
5. Gift sotmoqchi bo'lsangiz — botning Stars balansini to'ldiring (BotFather → Bot Settings).

Admin buyruqlari: `/karta` (to'lov kartasi), `/kurs 31500` yoki `/kurs auto` (TON kursi),
`/narx` (joriy narxlar), `/buyurtmalar` (oxirgi 10 ta buyurtma va holatlari).

> ⚠️ Gunicorn **bitta worker** (`--workers 1 --threads 8`) bilan ishlashi shart: baza jadvallari
> jarayon xotirasida keshlanadi, ikki worker bo'lsa buyurtmalar bir-birini ko'rmay qoladi.

## Muammolarni aniqlash

Bot "javob bermayapti" bo'lsa — avval botda **`/diag`** yozing (faqat admin). U bitta xabarda tekshiradi:
token, webhook manzili (`BASE_URL`), DB kanal va log kanal (bot admin bo'lishi shart), MNEMONIC, hamyon
balansi, TON kursi, Fragment (cookie/hash), to'lov kartasi, Gift uchun Stars balansi.
`/id` — o'z Telegram ID'ingizni ko'rsatadi (`ADMIN_ID` mos kelmayotganini aniqlash uchun).

Loglarda qidiring:

- `[STARTUP] XATO ...` — server ishga tushganda aniqlangan muammolar.
- `[TG] sendMessage XATO: ...` — Telegram bot so'rovini rad etgan (sababi bilan).
- `⛔ DB KANALIGA ULANIB BO'LMADI` — `chat not found`: **bot DB kanalida ADMIN emas** yoki `DB_CHANNEL_ID`
  noto'g'ri yoki `BOT_TOKEN` kanalga qo'shilmagan botniki. Tuzatilmasa, ma'lumotlar (foydalanuvchilar,
  buyurtmalar, karta) faqat lokal diskda turadi va Render qayta ishga tushganda **yo'qoladi**.

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
  pricing.py           — narxlar, marja, miqdor chegaralari, TON kursi
telegram_bot.py         — Telegram Bot API umumiy wrapper
main.py                  — Flask webhook (asosiy bot handleri)
handlers.py              — inline tugmalar router (menyu, captcha, profil, referal, statistika)
orders.py                — Stars/Premium/Gift/TON xarid oqimlari, to'lov, admin tasdig'i
diagnostics.py           — /diag tashxis buyrug'i va ishga tushish tekshiruvi
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
3. **Start Command:** `gunicorn main:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120`
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
# sorapaybot
# sorapaybot
