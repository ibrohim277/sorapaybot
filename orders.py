"""
Xarid oqimlari: Stars / Premium / Gift / TON.

OQIM (har bir xizmat uchun bir xil):
  1) Foydalanuvchi miqdor/turini tanlaydi
  2) Qabul qiluvchini kiritadi (@username / TON hamyon / Telegram ID)
  3) Narxni ko'radi va tasdiqlaydi  -> buyurtma yaratiladi (awaiting_payment)
  4) Kartaga to'lov qiladi va CHEK rasmini yuboradi -> awaiting_admin
  5) Admin chekni ko'radi va ✅ bosadi -> processing -> FONDA avtomatik bajariladi
        stars/premium : Fragment.com orqali (BuyStars)
        ton           : hamyondan yuborish (BuyTon)
        gift          : Bot API sendGift (botning Stars balansidan)
  6) Natija foydalanuvchiga va adminga xabar qilinadi (done / failed)

Buyurtma holatlari:
  awaiting_payment -> awaiting_admin -> processing -> done
                                     \\-> rejected        processing -> failed -> (retry) processing
  awaiting_payment -> cancelled
"""
import os
import re
import json
import asyncio
import logging
import threading
from datetime import datetime
from decimal import Decimal, InvalidOperation

from config import settings
from config import pricing as P
from config.channel_sql import (
    cdb_prepare, cdb_stmt_bind_param, cdb_stmt_execute, cdb_stmt_get_result,
    cdb_stmt_close, cdb_fetch_assoc, cdb_fetch_all, cdb_num_rows, cdb_insert_id,
)
from config.username_info import chekusername, chekPremiumUsername
from telegram_bot import Begzod, tg_from

logger = logging.getLogger("sorapay.orders")

# Bitta jarayon (gunicorn --workers 1) ichida buyurtma holatini himoya qiladi.
DB_LOCK = threading.RLock()

CALLBACK_PREFIXES = ('buy_', 'stars_', 'prem_', 'ton_', 'gift_', 'ord_', 'adm_')
USERNAME_RE = re.compile(r'^@?([A-Za-z][A-Za-z0-9_]{4,31})$')
TON_ADDR_RE = re.compile(r'^(UQ|EQ|kQ|0Q)[A-Za-z0-9_\-]{46}$')
MAX_OPEN_ORDERS = 3   # bitta foydalanuvchining admin tasdig'ini kutayotgan buyurtmalari


# =============================================================== kichik yordamchilar

def _h(s) -> str:
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _is_admin(user_id) -> bool:
    return str(user_id) == str(settings.ADMIN_ID)


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _safe_note(s, n=300) -> str:
    """Bazaga yoziladigan matnni xavfsiz qiladi."""
    s = re.sub(r"[\r\n\t]+", " ", str(s))
    s = re.sub(r"""['"`\\;]""", " ", s)
    return s[:n]


def _ok(res) -> bool:
    return bool(getattr(res, 'ok', False))


def _kb(rows):
    return json.dumps({'inline_keyboard': rows})


def _grid(buttons, per_row=2):
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


CANCEL_ROW = [{'text': "❌ Bekor qilish", 'callback_data': 'ord_cancel'}]
BACK_ROW = [{'text': "⬅️ Orqaga", 'callback_data': 'menu'}]


# =============================================================== step / qoralama (draft)

def _p(uid, suffix) -> str:
    return os.path.join(settings.STEP_DIR, f"{uid}{suffix}")


def _step_get(uid):
    try:
        with open(_p(uid, '.step'), encoding='utf-8') as f:
            return f.read().strip() or None
    except OSError:
        return None


def _step_set(uid, value) -> None:
    with open(_p(uid, '.step'), 'w', encoding='utf-8') as f:
        f.write(str(value))


def _draft_get(uid) -> dict:
    try:
        with open(_p(uid, '.order'), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _draft_set(uid, d: dict) -> None:
    with open(_p(uid, '.order'), 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False)


def _flow_clear(uid) -> None:
    for suffix in ('.step', '.order'):
        try:
            os.remove(_p(uid, suffix))
        except OSError:
            pass


# =============================================================== telegram yordamchilari

class Ctx:
    def __init__(self, bot, connect, send_main_menu, user, chat_id, message_id=0, cq=None):
        self.bot = bot
        self.connect = connect
        self.send_main_menu = send_main_menu
        self.user = user
        self.uid = user.id
        self.first_name = getattr(user, 'first_name', '') or ''
        self.username = getattr(user, 'username', None)
        self.chat_id = chat_id
        self.message_id = message_id
        self.cq = cq


def _send(bot, chat_id, text, rows=None):
    params = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
    if rows is not None:
        params['reply_markup'] = _kb(rows)
    return bot.sendMessage(params)


def _screen(ctx: Ctx, text, rows=None):
    """Callbackdan kelgan bo'lsa — xabarni tahrirlaydi, bo'lmasa yangi xabar yuboradi."""
    if ctx.message_id:
        params = {'chat_id': ctx.chat_id, 'message_id': ctx.message_id, 'text': text,
                  'parse_mode': 'HTML', 'disable_web_page_preview': True}
        if rows is not None:
            params['reply_markup'] = _kb(rows)
        res = ctx.bot.editMessageText(params)
        if _ok(res) or 'not modified' in str(getattr(res, 'description', '')):
            return res
    return _send(ctx.bot, ctx.chat_id, text, rows)


def _ans(ctx: Ctx, text=None, alert=False):
    if ctx.cq is None:
        return
    p = {'callback_query_id': ctx.cq.id}
    if text:
        p.update({'text': text, 'show_alert': alert})
    ctx.bot.answerCallbackQuery(p)


# =============================================================== baza yordamchilari

def _q_one(connect, sql, *vals):
    stmt = cdb_prepare(connect, sql)
    if vals:
        cdb_stmt_bind_param(stmt, "s" * len(vals), *[str(v) for v in vals])
    cdb_stmt_execute(stmt)
    res = cdb_stmt_get_result(stmt)
    rows = cdb_fetch_all(res)
    cdb_stmt_close(stmt)
    return rows


def _exec(connect, sql, *vals):
    stmt = cdb_prepare(connect, sql)
    if vals:
        cdb_stmt_bind_param(stmt, "s" * len(vals), *[str(v) for v in vals])
    cdb_stmt_execute(stmt)
    cdb_stmt_close(stmt)


def _cfg_get(connect, key, default=None):
    rows = _q_one(connect, "SELECT * FROM sozlamalar WHERE k = ?", key)
    return rows[0].get('v') if rows else default


def _cfg_set(connect, key, value) -> None:
    with DB_LOCK:
        if _q_one(connect, "SELECT * FROM sozlamalar WHERE k = ?", key):
            _exec(connect, "UPDATE sozlamalar SET v = ? WHERE k = ?", value, key)
        else:
            _exec(connect, "INSERT INTO sozlamalar SET k = ?, v = ?", key, value)


def _order_get(connect, oid):
    rows = _q_one(connect, "SELECT * FROM orders WHERE id = ?", oid)
    return rows[0] if rows else None


def _order_set(connect, oid, **fields) -> None:
    cols = list(fields.keys())
    sets = ", ".join(f"{c} = ?" for c in cols)
    _exec(connect, f"UPDATE orders SET {sets} WHERE id = ?", *[fields[c] for c in cols], oid)


def _order_create(connect, **fields) -> int:
    cols = list(fields.keys())
    sets = ", ".join(f"{c} = ?" for c in cols)
    stmt = cdb_prepare(connect, f"INSERT INTO orders SET {sets}")
    cdb_stmt_bind_param(stmt, "s" * len(cols), *[str(fields[c]) for c in cols])
    cdb_stmt_execute(stmt)
    cdb_stmt_close(stmt)
    return int(cdb_insert_id(connect))


def _claim(connect, oid, expected, new_status, **extra):
    """Holatni ATOMIK o'zgartiradi (qo'sh-bosish / qayta yuborilgan update'dan himoya).
    Muvaffaqiyatli bo'lsa — yangilangan buyurtmani, aks holda None qaytaradi."""
    with DB_LOCK:
        o = _order_get(connect, oid)
        if not o or str(o.get('status')) not in expected:
            return None
        _order_set(connect, oid, status=new_status, updated=_now(), **extra)
        o = dict(o)
        o['status'] = new_status
        return o


def _rate(connect) -> float:
    return P.get_ton_uzs(_cfg_get(connect, 'ton_kurs'))


def _card(connect):
    number = _cfg_get(connect, 'karta') or P.CARD_NUMBER
    owner = _cfg_get(connect, 'karta_egasi') or P.CARD_OWNER
    return (str(number or '').strip(), str(owner or '').strip())


# =============================================================== TON / hamyon (lazy import)

def _wallet_balance_ton() -> float:
    from tonutils.client import TonapiClient
    from tonutils.wallet import WalletV4R2

    async def _b():
        client = TonapiClient(api_key=settings.API_TON, is_testnet=False)
        wallet, _, _, _ = WalletV4R2.from_mnemonic(client, settings.MNEMONIC_LIST)
        nano = await client.get_account_balance(wallet.address.to_str(is_bounceable=False))
        return nano / 1_000_000_000

    return asyncio.run(_b())


def _run_buy(action, query, amount) -> bool:
    from BuyStars.main import buy
    return asyncio.run(buy(action, query, int(amount)))


def _run_ton_send(address, amount) -> bool:
    from BuyTon.main import TonSender
    return asyncio.run(TonSender().send(address, float(amount)))


# =============================================================== tavsif / narx

KIND_TITLE = {'stars': "Stars", 'premium': "Premium", 'ton': "TON", 'gift': "Gift"}


def _describe(d: dict) -> str:
    k = d.get('kind')
    if k == 'stars':
        what = f"⭐️ <b>{P.fmt(d['qty'])} Telegram Stars</b>"
        who = f"👤 Qabul qiluvchi: <b>{_h(d.get('target', '?'))}</b>"
    elif k == 'premium':
        what = f"💎 <b>Telegram Premium — {d['qty']} oy</b>"
        who = f"👤 Qabul qiluvchi: <b>{_h(d.get('target', '?'))}</b>"
    elif k == 'ton':
        what = f"💎 <b>{_h(d['qty'])} TON</b>"
        who = f"👛 Hamyon: <code>{_h(d.get('target', '?'))}</code>"
    else:
        what = f"🎁 <b>Gift {_h(d.get('gift_emoji', ''))} ({d.get('gift_stars')}⭐️)</b>"
        who = f"👤 Qabul qiluvchi ID: <code>{_h(d.get('target', '?'))}</code>"
    return f"{what}\n{who}"


def _price(d: dict, rate: float) -> int:
    k = d['kind']
    if k == 'stars':
        return P.stars_price(int(d['qty']), rate)
    if k == 'premium':
        return P.premium_price(int(d['qty']), rate)
    if k == 'ton':
        return P.ton_price(Decimal(str(d['qty'])), rate)
    return P.stars_price(int(d['gift_stars']), rate)


# =============================================================== 1-bosqich: xizmat tanlash

def start_stars(ctx: Ctx):
    _flow_clear(ctx.uid)
    rate = _rate(ctx.connect)
    btns = [{'text': f"⭐️ {n} · {P.fmt(P.stars_price(n, rate))} so'm", 'callback_data': f'stars_q_{n}'}
            for n in P.STARS_PACKS]
    rows = _grid(btns) + [[{'text': "✏️ Boshqa miqdor", 'callback_data': 'stars_q_custom'}], BACK_ROW]
    _ans(ctx)
    _screen(ctx, "⭐️ <b>Telegram Stars</b>\n\nKerakli miqdorni tanlang yoki o'zingiz kiriting "
                 f"(min {P.STARS_MIN}, max {P.fmt(P.STARS_MAX)}):", rows)


def start_premium(ctx: Ctx):
    _flow_clear(ctx.uid)
    rate = _rate(ctx.connect)
    btns = [{'text': f"💎 {m} oy · {P.fmt(P.premium_price(m, rate))} so'm", 'callback_data': f'prem_m_{m}'}
            for m in sorted(P.PREMIUM_TON)]
    _ans(ctx)
    _screen(ctx, "💎 <b>Telegram Premium</b>\n\nMuddatni tanlang:", _grid(btns, 1) + [BACK_ROW])


def start_ton(ctx: Ctx):
    _flow_clear(ctx.uid)
    rate = _rate(ctx.connect)
    btns = [{'text': f"💎 {n} TON · {P.fmt(P.ton_price(n, rate))} so'm", 'callback_data': f'ton_q_{n}'}
            for n in P.TON_PACKS]
    rows = _grid(btns) + [[{'text': "✏️ Boshqa miqdor", 'callback_data': 'ton_q_custom'}], BACK_ROW]
    _ans(ctx)
    _screen(ctx, f"💎 <b>TON coin</b>\n\nMiqdorni tanlang yoki o'zingiz kiriting (min {P.TON_MIN}, max {P.TON_MAX}):", rows)


def _load_gifts(bot):
    res = bot.getAvailableGifts()
    gifts = getattr(getattr(res, 'result', None), 'gifts', None) or []
    out = []
    for g in gifts:
        remaining = getattr(g, 'remaining_count', None)
        if remaining is not None and int(remaining) <= 0:
            continue
        sticker = getattr(g, 'sticker', None)
        out.append({'id': str(g.id), 'stars': int(g.star_count),
                    'emoji': getattr(sticker, 'emoji', '🎁') or '🎁'})
    out.sort(key=lambda x: x['stars'])
    return out


def start_gift(ctx: Ctx):
    _flow_clear(ctx.uid)
    gifts = _load_gifts(ctx.bot)[:16]
    if not gifts:
        return _ans(ctx, "Hozircha sovg'alar mavjud emas. Keyinroq urinib ko'ring.", True)
    rate = _rate(ctx.connect)
    btns = [{'text': f"{g['emoji']} {g['stars']}⭐️ · {P.fmt(P.stars_price(g['stars'], rate))}",
             'callback_data': f"gift_g_{g['id']}"} for g in gifts]
    _ans(ctx)
    _screen(ctx, "🎁 <b>Telegram Gift</b>\n\nSovg'ani tanlang (narx so'mda):", _grid(btns) + [BACK_ROW])


# =============================================================== 2-bosqich: miqdor/qabul qiluvchi

def _ask_recipient(ctx: Ctx, d: dict):
    k = d['kind']
    rows = []
    if k in ('stars', 'premium'):
        step = 'stars_user' if k == 'stars' else 'prem_user'
        text = (f"{_describe_head(d)}\n\n👤 Kimga yuboramiz? Telegram <b>@username</b> kiriting "
                "(masalan: <code>@durov</code>)")
        if ctx.username:
            rows.append([{'text': "👤 O'zimga", 'callback_data': 'ord_me'}])
    elif k == 'ton':
        step = 'ton_addr'
        text = (f"{_describe_head(d)}\n\n👛 TON hamyon manzilingizni yuboring "
                "(<code>UQ...</code> yoki <code>EQ...</code> ko'rinishida).\n"
                "⚠️ Manzilni diqqat bilan tekshiring — noto'g'ri manzilga yuborilgan TON qaytmaydi!")
    else:
        step = 'gift_user'
        text = (f"{_describe_head(d)}\n\n👤 Sovg'a oluvchining <b>Telegram ID</b> raqamini yuboring "
                "yoki o'zingizga yuboring.")
        rows.append([{'text': "🎁 O'zimga", 'callback_data': 'ord_me'}])
    rows.append(CANCEL_ROW)
    _draft_set(ctx.uid, d)
    _step_set(ctx.uid, step)
    _screen(ctx, text, rows)


def _describe_head(d: dict) -> str:
    return _describe({**d, 'target': d.get('target', '—')}).split('\n')[0]


def _show_confirm(ctx: Ctx, d: dict):
    rate = _rate(ctx.connect)
    price = _price(d, rate)
    _draft_set(ctx.uid, d)
    _step_set(ctx.uid, 'confirm')
    text = (f"🧾 <b>Buyurtmani tasdiqlang</b>\n\n{_describe(d)}\n\n"
            f"💰 To'lov summasi: <b>{P.fmt(price)} so'm</b>")
    _screen(ctx, text, [[{'text': "✅ Tasdiqlash", 'callback_data': 'ord_confirm'}], CANCEL_ROW])


def _validate_username(ctx: Ctx, d: dict, raw: str):
    """(True, '@name') yoki (False, xato matni)."""
    m = USERNAME_RE.match(raw.strip())
    if not m:
        return False, "❌ Username noto'g'ri. Masalan: <code>@durov</code>"
    name = m.group(1)
    if d['kind'] == 'premium':
        r = chekPremiumUsername(name, int(d['qty']))
        if r.get('error'):
            return False, "⚠️ Tekshirib bo'lmadi, birozdan so'ng qayta urinib ko'ring."
        if r.get('has_premium'):
            return False, "⚠️ Bu akkauntda allaqachon Telegram Premium bor."
        if not r.get('exists'):
            return False, "❌ Bunday foydalanuvchi topilmadi yoki unga Premium sovg'a qilib bo'lmaydi."
    else:
        r = chekusername(name)
        if r.get('error'):
            return False, "⚠️ Tekshirib bo'lmadi, birozdan so'ng qayta urinib ko'ring."
        if not r.get('exists'):
            return False, "❌ Bunday foydalanuvchi topilmadi. Username'ni tekshirib qayta yuboring."
    return True, '@' + name


# =============================================================== 3-bosqich: buyurtma yaratish

def _stock_check(ctx: Ctx, d: dict):
    """Yumshoq tekshiruv: xizmatni bajarishga resurs bormi. (ok, sabab)."""
    try:
        if d['kind'] == 'gift':
            res = ctx.bot.getMyStarBalance()
            bal = int(getattr(getattr(res, 'result', None), 'amount', 0) or 0)
            if _ok(res) and bal < int(d['gift_stars']):
                return False, "Hozircha bu sovg'a mavjud emas (zaxira tugagan). Keyinroq urinib ko'ring."
            return True, ''
        if not settings.MNEMONIC_LIST:
            return True, ''   # sozlanmagan bo'lsa — admin qo'lda hal qiladi
        need = P.required_ton(d['kind'], d['qty']) + P.WALLET_RESERVE_TON
        bal = _wallet_balance_ton()
        if bal < need:
            return False, "Hozircha bu miqdorni berib bo'lmaydi (zaxira yetarli emas). Kichikroq miqdorni tanlang yoki keyinroq urining."
    except Exception as e:
        logger.warning("Zaxira tekshiruvi bajarilmadi: %s", e)
    return True, ''


def confirm_order(ctx: Ctx):
    d = _draft_get(ctx.uid)
    if not d.get('kind') or not d.get('target') or _step_get(ctx.uid) != 'confirm':
        return _ans(ctx, "Seans tugagan. Iltimos, menyudan qaytadan boshlang.", True)

    card, owner = _card(ctx.connect)
    if not card and not _is_admin(ctx.uid):
        _ans(ctx, "To'lov rekvizitlari hali sozlanmagan. Admin bilan bog'laning.", True)
        _send(ctx.bot, settings.ADMIN_ID,
              "⚠️ Foydalanuvchi buyurtma bermoqchi, lekin to'lov kartasi kiritilmagan.\n"
              "Quyidagicha kiriting:\n<code>/karta 8600123412341234 Ism Familiya</code>")
        return

    open_cnt = len([o for o in _q_one(ctx.connect, "SELECT * FROM orders WHERE user_id = ? AND status = ?",
                                      ctx.uid, 'awaiting_admin')])
    if open_cnt >= MAX_OPEN_ORDERS:
        return _ans(ctx, "Sizda admin tekshiruvini kutayotgan buyurtmalar ko'p. Iltimos, kuting.", True)

    ok, why = _stock_check(ctx, d)
    if not ok:
        return _ans(ctx, why, True)

    with DB_LOCK:
        if _step_get(ctx.uid) != 'confirm':     # qo'sh bosishdan himoya
            return _ans(ctx)
        rate = _rate(ctx.connect)
        price = _price(d, rate)
        oid = _order_create(
            ctx.connect,
            user_id=ctx.uid, first_name=_safe_note(ctx.first_name, 60), username=_safe_note(ctx.username or '', 40),
            kind=d['kind'], qty=d.get('qty', ''), target=_safe_note(d['target'], 80),
            gift_id=d.get('gift_id', ''), gift_emoji=d.get('gift_emoji', ''),
            price_uzs=price, status='awaiting_payment', receipt_type='', receipt_file_id='',
            note='', created=_now(), updated=_now(),
        )
        _draft_set(ctx.uid, {'order_id': oid})
        _step_set(ctx.uid, 'receipt')

    _ans(ctx)

    if _is_admin(ctx.uid):
        # Admin o'z botidan o'zi xarid qiladi — to'lov/chek so'ralmaydi, to'g'ridan-to'g'ri bajariladi.
        _flow_clear(ctx.uid)
        if _claim(ctx.connect, oid, {'awaiting_payment'}, 'processing'):
            _CONNECT_REF['c'] = ctx.connect
            _screen(ctx, f"⏳ <b>Buyurtma #{oid}</b> (admin) — to'lovsiz, hamyondan bajarilmoqda...\n\n{_describe(d)}", [BACK_ROW])
            _spawn_fulfillment(oid)
        return

    text = (f"🧾 <b>Buyurtma #{oid}</b>\n\n{_describe(d)}\n\n"
            f"💰 To'lov summasi: <b>{P.fmt(price)} so'm</b>\n\n"
            f"💳 Karta: <code>{_h(card)}</code>\n"
            + (f"👤 Qabul qiluvchi: <b>{_h(owner)}</b>\n" if owner else "") +
            "\n❗️ Aynan shu summani o'tkazing, so'ng <b>to'lov chekini (skrinshot) rasm qilib shu yerga yuboring</b>. "
            "Admin tekshirgach, buyurtmangiz avtomatik bajariladi.")
    _screen(ctx, text, [[{'text': "❌ Buyurtmani bekor qilish", 'callback_data': f'ord_xcl_{oid}'}]])


# =============================================================== 4-bosqich: chek

def _admin_order_text(o: dict) -> str:
    d = {'kind': o['kind'], 'qty': o['qty'], 'target': o['target'],
         'gift_emoji': o.get('gift_emoji'), 'gift_stars': o['qty']}
    who = f"@{_h(o.get('username'))}" if o.get('username') else "—"
    return (f"🧾 <b>Buyurtma #{o['id']}</b>\n"
            f"👤 Mijoz: {_h(o.get('first_name', ''))} ({who}) · ID <code>{o['user_id']}</code>\n\n"
            f"{_describe(d)}\n\n"
            f"💰 Summa: <b>{P.fmt(o['price_uzs'])} so'm</b>")


def _admin_buttons(oid):
    return [[{'text': "✅ Tasdiqlash", 'callback_data': f'adm_ok_{oid}'},
             {'text': "❌ Rad etish", 'callback_data': f'adm_no_{oid}'}]]


def handle_receipt(ctx: Ctx, msg):
    d = _draft_get(ctx.uid)
    oid = d.get('order_id')
    if not oid:
        return _send(ctx.bot, ctx.chat_id, "Buyurtma topilmadi. Menyudan qaytadan boshlang: /start")

    photos = getattr(msg, 'photo', None)
    doc = getattr(msg, 'document', None)
    if photos:
        rtype, file_id = 'photo', photos[-1].file_id
    elif doc:
        rtype, file_id = 'document', doc.file_id
    else:
        return _send(ctx.bot, ctx.chat_id, "📎 Iltimos, to'lov <b>chekini rasm (skrinshot) qilib</b> yuboring.")

    o = _claim(ctx.connect, oid, {'awaiting_payment'}, 'awaiting_admin',
               receipt_type=rtype, receipt_file_id=file_id)
    if not o:
        return _send(ctx.bot, ctx.chat_id, "Bu buyurtma uchun chek allaqachon yuborilgan yoki buyurtma yopilgan.")

    full = _order_get(ctx.connect, oid)
    method = 'sendPhoto' if rtype == 'photo' else 'sendDocument'
    key = 'photo' if rtype == 'photo' else 'document'
    res = getattr(ctx.bot, method)({
        'chat_id': settings.ADMIN_ID, key: file_id, 'caption': _admin_order_text(full),
        'parse_mode': 'HTML', 'reply_markup': _kb(_admin_buttons(oid)),
    })
    if not _ok(res):
        logger.error("Adminga chek yuborib bo'lmadi: %s", getattr(res, 'description', res))
        _claim(ctx.connect, oid, {'awaiting_admin'}, 'awaiting_payment')   # qayta yuborishga ruxsat
        return _send(ctx.bot, ctx.chat_id, "⚠️ Chekni adminga yetkazib bo'lmadi. Birozdan so'ng chekni qayta yuboring.")

    _flow_clear(ctx.uid)
    _send(ctx.bot, ctx.chat_id,
          f"✅ Chek qabul qilindi (buyurtma <b>#{oid}</b>).\nAdmin tekshirgach, buyurtmangiz bajariladi — natijani shu yerda xabar qilamiz.",
          [BACK_ROW])


# =============================================================== 5-bosqich: admin va bajarish

def _notify_user(bot, user_id, text):
    try:
        _send(bot, user_id, text, [BACK_ROW])
    except Exception:
        logger.exception("Foydalanuvchiga xabar yuborib bo'lmadi: %s", user_id)


def _clear_admin_buttons(ctx: Ctx):
    if ctx.message_id:
        ctx.bot.editMessageReplyMarkup({'chat_id': ctx.chat_id, 'message_id': ctx.message_id,
                                        'reply_markup': _kb([])})


def _spawn_fulfillment(oid):
    t = threading.Thread(target=_fulfill, args=(oid, _CONNECT_REF['c']), name=f"fulfill-{oid}", daemon=True)
    t.start()
    return t


_CONNECT_REF = {'c': None}


def admin_decide(ctx: Ctx, action: str, oid: int):
    if not _is_admin(ctx.uid):
        return _ans(ctx, "Bu tugma faqat admin uchun.", True)
    _CONNECT_REF['c'] = ctx.connect

    if action == 'no':
        o = _claim(ctx.connect, oid, {'awaiting_admin', 'failed'}, 'rejected')
        if not o:
            return _ans(ctx, "Bu buyurtma allaqachon ko'rib chiqilgan.", True)
        _ans(ctx, "Rad etildi")
        _clear_admin_buttons(ctx)
        _send(ctx.bot, ctx.chat_id, f"❌ #{oid} rad etildi.")
        _notify_user(ctx.bot, o['user_id'],
                     f"❌ Buyurtma <b>#{oid}</b> tasdiqlanmadi. Savol bo'lsa, admin bilan bog'laning.")
        return

    expected = {'awaiting_admin'} if action == 'ok' else {'failed'}
    o = _claim(ctx.connect, oid, expected, 'processing')
    if not o:
        return _ans(ctx, "Bu buyurtma allaqachon ko'rib chiqilgan.", True)
    _ans(ctx, "Bajarilmoqda...")
    _clear_admin_buttons(ctx)
    _send(ctx.bot, ctx.chat_id, f"⏳ #{oid} bajarilmoqda...")
    if action == 'ok':
        _notify_user(ctx.bot, o['user_id'], f"✅ To'lov tasdiqlandi! Buyurtma <b>#{oid}</b> bajarilmoqda...")
    _spawn_fulfillment(oid)


def _do_fulfill(o: dict, bot):
    """(ok: bool, xato matni). Istisno ko'tarsa — chaqiruvchi ushlaydi."""
    kind, qty, target = o['kind'], o['qty'], str(o['target'])

    if kind == 'gift':
        res = bot.getMyStarBalance()
        bal = int(getattr(getattr(res, 'result', None), 'amount', 0) or 0)
        if bal < int(qty):
            return False, f"Botning Stars balansi yetarli emas (bor {bal}, kerak {qty}). Balansni to'ldiring."
        res = bot.sendGift({'user_id': int(target), 'gift_id': str(o['gift_id'])})
        if not _ok(res):
            return False, f"sendGift xatosi: {getattr(res, 'description', 'noma`lum')}"
        return True, ''

    if not settings.MNEMONIC_LIST:
        return False, "config/settings.py da MNEMONIC bo'sh — hamyon sozlanmagan."
    need = P.required_ton(kind, qty) + P.WALLET_RESERVE_TON
    bal = _wallet_balance_ton()
    if bal < need:
        return False, f"Hamyonda TON yetarli emas (bor {bal:.2f}, kerak ~{need:.2f})."

    if kind in ('stars', 'premium'):
        ok = _run_buy(kind, target, qty)
        return (True, '') if ok else (False, "Fragment/TON tranzaksiyasi muvaffaqiyatsiz (loglarga qarang).")
    if kind == 'ton':
        ok = _run_ton_send(target, qty)
        return (True, '') if ok else (False, "TON yuborilmadi (loglarga qarang).")
    return False, f"Noma'lum xizmat turi: {kind}"


def _fulfill(oid, connect):
    bot = Begzod()
    o = _order_get(connect, oid)
    if not o:
        return
    try:
        ok, err = _do_fulfill(o, bot)
    except Exception as e:      # tarmoq, tonutils, Fragment va h.k.
        logger.exception("Buyurtma #%s bajarishda xato", oid)
        ok, err = False, f"{type(e).__name__}: {e}"

    with DB_LOCK:
        if ok:
            _order_set(connect, oid, status='done', updated=_now(), note='')
        else:
            _order_set(connect, oid, status='failed', updated=_now(), note=_safe_note(err))

    if ok:
        kind = o['kind']
        if kind == 'stars':
            done_text = f"⭐️ {P.fmt(o['qty'])} Stars {_h(o['target'])} ga yuborildi. Bir necha daqiqa ichida tushadi."
        elif kind == 'premium':
            done_text = f"💎 {_h(o['qty'])} oylik Premium {_h(o['target'])} ga sovg'a qilindi."
        elif kind == 'ton':
            done_text = f"💎 {_h(o['qty'])} TON hamyoningizga yuborildi. Blokcheyn tasdiqlashi uchun bir necha daqiqa kuting."
        else:
            done_text = "🎁 Sovg'a yuborildi!"
        _notify_user(bot, o['user_id'], f"✅ <b>Buyurtma #{oid} bajarildi!</b>\n\n{done_text}\n\nXaridingiz barakali bo'lsin! 🤝")
        _send(bot, settings.ADMIN_ID, f"✅ #{oid} bajarildi.")
        try:
            _send(bot, settings.LOG_CHANNEL_ID, "✅ " + _admin_order_text(_order_get(connect, oid)).replace('\n\n', '\n'))
        except Exception:
            pass
    else:
        _notify_user(bot, o['user_id'],
                     f"⚠️ Buyurtma <b>#{oid}</b> bajarilishida texnik nosozlik yuz berdi. "
                     "Admin tez orada hal qiladi — to'lovingiz yo'qolmaydi.")
        _send(bot, settings.ADMIN_ID,
              f"⚠️ <b>#{oid} bajarilmadi</b>\n<code>{_h(err)}</code>\n\n"
              "❗️ Qayta urinishdan oldin hamyon tranzaksiyalarini tekshiring (pul chiqib ketgan bo'lsa, ikki marta to'lamang).",
              [[{'text': "🔁 Qayta urinish", 'callback_data': f'adm_retry_{oid}'},
                {'text': "❌ Rad etish (qaytarish)", 'callback_data': f'adm_no_{oid}'}]])


# =============================================================== admin buyruqlari

def _admin_command(ctx: Ctx, text: str) -> bool:
    parts = text.strip().split(maxsplit=2)
    cmd = parts[0].split('@')[0].lower()

    if cmd == '/karta':
        if len(parts) < 2 or not re.fullmatch(r'\d{12,19}', parts[1].replace(' ', '')):
            _send(ctx.bot, ctx.chat_id, "Foydalanish: <code>/karta 8600123412341234 Ism Familiya</code>")
            return True
        _cfg_set(ctx.connect, 'karta', parts[1])
        _cfg_set(ctx.connect, 'karta_egasi', _safe_note(parts[2], 60) if len(parts) > 2 else '')
        _send(ctx.bot, ctx.chat_id, f"✅ Karta saqlandi: <code>{_h(parts[1])}</code>")
        return True

    if cmd == '/kurs':
        if len(parts) < 2:
            _send(ctx.bot, ctx.chat_id, "Foydalanish: <code>/kurs 31500</code> yoki <code>/kurs auto</code>")
            return True
        if parts[1].lower() == 'auto':
            _cfg_set(ctx.connect, 'ton_kurs', '')
            _send(ctx.bot, ctx.chat_id, "✅ Kurs avtomatik rejimga qaytdi.")
            return True
        try:
            val = float(parts[1])
            assert val > 0
        except (ValueError, AssertionError):
            _send(ctx.bot, ctx.chat_id, "❌ Kurs son bo'lishi kerak, masalan: <code>/kurs 31500</code>")
            return True
        _cfg_set(ctx.connect, 'ton_kurs', val)
        _send(ctx.bot, ctx.chat_id, f"✅ 1 TON = {P.fmt(val)} so'm (qo'lda belgilandi, marja qo'shilmaydi).")
        return True

    if cmd == '/narx':
        rate = _rate(ctx.connect)
        lines = [f"💱 1 TON = <b>{P.fmt(rate)}</b> so'm"]
        lines += [f"⭐️ {n} Stars = {P.fmt(P.stars_price(n, rate))}" for n in P.STARS_PACKS]
        lines += [f"💎 Premium {m} oy = {P.fmt(P.premium_price(m, rate))}" for m in sorted(P.PREMIUM_TON)]
        card, owner = _card(ctx.connect)
        lines.append(f"💳 Karta: <code>{_h(card) or 'kiritilmagan'}</code> {_h(owner)}")
        _send(ctx.bot, ctx.chat_id, "\n".join(lines))
        return True

    if cmd == '/buyurtmalar':
        rows = _q_one(ctx.connect, "SELECT * FROM orders ORDER BY id DESC LIMIT 10")
        if not rows:
            _send(ctx.bot, ctx.chat_id, "Hali buyurtmalar yo'q.")
            return True
        lines = [f"#{r['id']} · {KIND_TITLE.get(r['kind'], r['kind'])} {r['qty']} · {P.fmt(r['price_uzs'])} · "
                 f"<b>{_h(r['status'])}</b> · ID {r['user_id']}" for r in rows]
        _send(ctx.bot, ctx.chat_id, "📋 <b>Oxirgi buyurtmalar</b>\n\n" + "\n".join(lines))
        return True

    return False


# =============================================================== kirish nuqtalari

_Q_RE = {
    'stars_q': re.compile(r'stars_q_(\d+)'),
    'prem_m': re.compile(r'prem_m_(\d+)'),
    'ton_q': re.compile(r'ton_q_(\d+)'),
    'gift_g': re.compile(r'gift_g_(\d+)'),
    'adm': re.compile(r'adm_(ok|no|retry)_(\d+)'),
    'xcl': re.compile(r'ord_xcl_(\d+)'),
}


def handle_order_callback(bot, cq, connect, send_main_menu) -> bool:
    """True qaytarsa — callback shu yerda qayta ishlandi."""
    data = cq.data or ''
    if not data.startswith(CALLBACK_PREFIXES):
        return False
    msg = getattr(cq, 'message', None)
    user = tg_from(cq)
    ctx = Ctx(bot, connect, send_main_menu, user,
              msg.chat.id if msg else user.id, msg.message_id if msg else 0, cq)
    _CONNECT_REF['c'] = connect

    if data == 'buy_stars':
        start_stars(ctx)
    elif data == 'buy_premium':
        start_premium(ctx)
    elif data == 'buy_ton':
        start_ton(ctx)
    elif data == 'buy_gift':
        start_gift(ctx)

    elif data == 'stars_q_custom':
        _ans(ctx)
        _draft_set(ctx.uid, {'kind': 'stars'})
        _step_set(ctx.uid, 'stars_custom')
        _screen(ctx, f"⭐️ Nechta Stars kerak? Son yuboring (min {P.STARS_MIN}, max {P.fmt(P.STARS_MAX)}):", [CANCEL_ROW])
    elif data == 'ton_q_custom':
        _ans(ctx)
        _draft_set(ctx.uid, {'kind': 'ton'})
        _step_set(ctx.uid, 'ton_custom')
        _screen(ctx, f"💎 Necha TON kerak? Son yuboring (min {P.TON_MIN}, max {P.TON_MAX}, masalan <code>2.5</code>):", [CANCEL_ROW])

    elif _Q_RE['stars_q'].fullmatch(data):
        n = int(_Q_RE['stars_q'].fullmatch(data).group(1))
        if n not in P.STARS_PACKS:
            return _ans(ctx, "Noto'g'ri tanlov.", True) or True
        _ans(ctx)
        _ask_recipient(ctx, {'kind': 'stars', 'qty': n})
    elif _Q_RE['prem_m'].fullmatch(data):
        m = int(_Q_RE['prem_m'].fullmatch(data).group(1))
        if m not in P.PREMIUM_TON:
            return _ans(ctx, "Noto'g'ri tanlov.", True) or True
        _ans(ctx)
        _ask_recipient(ctx, {'kind': 'premium', 'qty': m})
    elif _Q_RE['ton_q'].fullmatch(data):
        n = int(_Q_RE['ton_q'].fullmatch(data).group(1))
        if n not in P.TON_PACKS:
            return _ans(ctx, "Noto'g'ri tanlov.", True) or True
        _ans(ctx)
        _ask_recipient(ctx, {'kind': 'ton', 'qty': n})
    elif _Q_RE['gift_g'].fullmatch(data):
        gid = _Q_RE['gift_g'].fullmatch(data).group(1)
        gift = next((g for g in _load_gifts(bot) if g['id'] == gid), None)   # narx serverdan qayta olinadi
        if not gift:
            return _ans(ctx, "Bu sovg'a endi mavjud emas.", True) or True
        _ans(ctx)
        _ask_recipient(ctx, {'kind': 'gift', 'qty': gift['stars'], 'gift_id': gift['id'],
                             'gift_stars': gift['stars'], 'gift_emoji': gift['emoji']})

    elif data == 'ord_me':
        d = _draft_get(ctx.uid)
        if d.get('kind') in ('stars', 'premium') and ctx.username:
            _ans(ctx)
            ok, res = _validate_username(ctx, d, ctx.username)
            if not ok:
                return _send(bot, ctx.chat_id, res) and True
            d['target'] = res
            _show_confirm(ctx, d)
        elif d.get('kind') == 'gift':
            _ans(ctx)
            d['target'] = str(ctx.uid)
            _show_confirm(ctx, d)
        else:
            _ans(ctx, "Avval xizmatni tanlang.", True)
    elif data == 'ord_confirm':
        confirm_order(ctx)
    elif data == 'ord_cancel':
        _flow_clear(ctx.uid)
        _ans(ctx, "Bekor qilindi")
        if ctx.message_id:
            bot.deleteMessage({'chat_id': ctx.chat_id, 'message_id': ctx.message_id})
        send_main_menu(bot, ctx.uid, ctx.first_name)
    elif _Q_RE['xcl'].fullmatch(data):
        oid = int(_Q_RE['xcl'].fullmatch(data).group(1))
        o = _order_get(connect, oid)
        if not o or str(o['user_id']) != str(ctx.uid):
            return _ans(ctx, "Buyurtma topilmadi.", True) or True
        if not _claim(connect, oid, {'awaiting_payment'}, 'cancelled'):
            return _ans(ctx, "Bu buyurtmani endi bekor qilib bo'lmaydi.", True) or True
        _flow_clear(ctx.uid)
        _ans(ctx, "Buyurtma bekor qilindi")
        if ctx.message_id:
            bot.deleteMessage({'chat_id': ctx.chat_id, 'message_id': ctx.message_id})
        send_main_menu(bot, ctx.uid, ctx.first_name)
    elif _Q_RE['adm'].fullmatch(data):
        m = _Q_RE['adm'].fullmatch(data)
        admin_decide(ctx, m.group(1), int(m.group(2)))
    else:
        _ans(ctx)
    return True


def handle_message(bot, msg, connect, send_main_menu) -> bool:
    """Matn / rasm xabarlari. True — xabar xarid oqimi tomonidan iste'mol qilindi."""
    user = tg_from(msg)
    ctx = Ctx(bot, connect, send_main_menu, user, msg.chat.id)
    _CONNECT_REF['c'] = connect
    text = (getattr(msg, 'text', '') or '').strip()

<<<<<<< HEAD
    cmd0 = text.split(maxsplit=1)[0].split('@')[0].lower() if text.startswith('/') else ''

    if cmd0 == '/id':   # hamma uchun: ADMIN_ID mos kelmayotganini aniqlashga yordam beradi
        _send(bot, ctx.chat_id, f"🆔 Sizning Telegram ID: <code>{ctx.uid}</code>\n"
                                + ("👑 Siz adminsiz." if _is_admin(ctx.uid) else
                                   "Siz admin emassiz. Admin bo'lish uchun <code>config/settings.py</code> dagi <code>ADMIN_ID</code> shu raqam bo'lishi kerak."))
        return True

    if cmd0 == '/diag':
        if not _is_admin(ctx.uid):
            _send(bot, ctx.chat_id, f"Bu buyruq faqat admin uchun. Sizning ID: <code>{ctx.uid}</code> — "
                                    "<code>config/settings.py</code> dagi <code>ADMIN_ID</code> bilan solishtiring.")
            return True
        import diagnostics
        _send(bot, ctx.chat_id, "🩺 Tekshiruv boshlandi, bir necha soniya kuting...")
        _send(bot, ctx.chat_id, diagnostics.format_report(diagnostics.run_checks(bot, connect, full=True)))
        return True

=======
>>>>>>> 396de28125b901daa7a9b9d4c7dad52d1eeab4c7
    if text.startswith('/') and _is_admin(ctx.uid):
        if _admin_command(ctx, text):
            return True

    step = _step_get(ctx.uid)
    if not step:
        return False

    if step == 'receipt':
        handle_receipt(ctx, msg)
        return True

    d = _draft_get(ctx.uid)

    if step == 'stars_custom':
        if not text.isdigit() or not (P.STARS_MIN <= int(text) <= P.STARS_MAX):
            _send(bot, ctx.chat_id, f"❌ {P.STARS_MIN} dan {P.fmt(P.STARS_MAX)} gacha butun son yuboring.", [CANCEL_ROW])
            return True
        _ask_recipient(ctx, {'kind': 'stars', 'qty': int(text)})
        return True

    if step == 'ton_custom':
        try:
            val = Decimal(text.replace(',', '.'))
            if not (Decimal(P.TON_MIN) <= val <= Decimal(P.TON_MAX)) or val.as_tuple().exponent < -2:
                raise InvalidOperation
        except InvalidOperation:
            _send(bot, ctx.chat_id, f"❌ {P.TON_MIN} dan {P.TON_MAX} gacha son yuboring (ko'pi bilan 2 xona kasr).", [CANCEL_ROW])
            return True
        _ask_recipient(ctx, {'kind': 'ton', 'qty': format(val.normalize(), 'f')})
        return True

    if step in ('stars_user', 'prem_user'):
        ok, res = _validate_username(ctx, d, text)
        if not ok:
            _send(bot, ctx.chat_id, res, [CANCEL_ROW])
            return True
        d['target'] = res
        _show_confirm(ctx, d)
        return True

    if step == 'ton_addr':
        if not TON_ADDR_RE.match(text):
            _send(bot, ctx.chat_id, "❌ TON manzil noto'g'ri. U <code>UQ</code> yoki <code>EQ</code> bilan boshlanib, 48 belgidan iborat bo'ladi.", [CANCEL_ROW])
            return True
        d['target'] = text
        _show_confirm(ctx, d)
        return True

    if step == 'gift_user':
        if not re.fullmatch(r'\d{5,15}', text):
            _send(bot, ctx.chat_id, "❌ Telegram ID faqat raqamlardan iborat bo'lishi kerak.", [CANCEL_ROW])
            return True
        d['target'] = text
        _show_confirm(ctx, d)
        return True

    if step == 'confirm':
        _send(bot, ctx.chat_id, "Yuqoridagi tugmalardan birini bosing: ✅ Tasdiqlash yoki ❌ Bekor qilish.")
        return True

    return False
