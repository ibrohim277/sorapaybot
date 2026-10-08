"""
Xarid oqimlari: Stars / Premium / Gift / TON.

To'lov modeli: foydalanuvchi balansi (users.balance, so'mda).
Xarid tasdiqlanganda balansdan yechiladi -> Fragment/TON orqali yuboriladi ->
xato bo'lsa pul avtomatik qaytariladi.

handlers.py va main.py dan chaqiriladi:
    purchase.handle_callback(bot, cq, connect, chat_id, message_id) -> bool
    purchase.handle_text(bot, msg, connect) -> bool
"""
import asyncio
import json
import logging
import os
import re
import time

import requests

from config import settings
from config.channel_sql import (
    cdb_query, cdb_prepare, cdb_stmt_bind_param, cdb_stmt_execute,
    cdb_stmt_get_result, cdb_stmt_close, cdb_fetch_assoc,
)
from config.username_info import chekusername, chekPremiumUsername
from telegram_bot import tg_from

logger = logging.getLogger("sorapay.purchase")

# ---- narx sozlamalari (asl PHP koddagi qiymatlar) ----
PREMIUM_TON = {3: 6.70, 6: 8.92, 12: 16.16}
STARS_50_TON = 0.4279
MARKUP_UZS = 1500
MIN_TON_UZS = 21000 + MARKUP_UZS
STARS_PACKS = [50, 100, 250, 500, 1000]
STARS_MIN, STARS_MAX = 50, 100000
TON_MIN, TON_MAX = 1.0, 500.0

BACK = [{'text': "⬅️ Orqaga", 'callback_data': 'menu'}]
USERNAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]{4,31}$')
TON_ADDR_RE = re.compile(r'^(EQ|UQ|kQ|0Q)[A-Za-z0-9_\-]{46}$')

_price_cache = {'t': 0, 'v': MIN_TON_UZS}


# ------------------------------------------------------------------ yordamchilar

def _flow_path(uid):
    return os.path.join(settings.STEP_DIR, f"{uid}.flow")


def _get_flow(uid):
    try:
        with open(_flow_path(uid), 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _set_flow(uid, flow):
    os.makedirs(settings.STEP_DIR, exist_ok=True)
    with open(_flow_path(uid), 'w', encoding='utf-8') as f:
        json.dump(flow, f)


def _clear_flow(uid):
    try:
        os.remove(_flow_path(uid))
    except OSError:
        pass


def _answer(bot, cq, text=None, alert=False):
    params = {'callback_query_id': cq.id}
    if text:
        params.update({'text': text, 'show_alert': alert})
    bot.answerCallbackQuery(params)


def _esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _kb(rows):
    return json.dumps({'inline_keyboard': rows})


def _show(bot, chat_id, message_id, text, rows):
    """Xabarni tahrirlaydi; bo'lmasa yangi xabar yuboradi."""
    if message_id:
        res = bot.editMessageText({
            'chat_id': chat_id, 'message_id': message_id, 'text': text,
            'parse_mode': 'HTML', 'reply_markup': _kb(rows),
        })
        if res is not None and getattr(res, 'ok', False):
            return
    bot.sendMessage({'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': _kb(rows)})


def _get_user(connect, user_id):
    stmt = cdb_prepare(connect, "SELECT * FROM users WHERE user_id = ?")
    cdb_stmt_bind_param(stmt, "s", str(user_id))
    cdb_stmt_execute(stmt)
    row = cdb_fetch_assoc(cdb_stmt_get_result(stmt))
    cdb_stmt_close(stmt)
    return row


def _balance(connect, user_id) -> int:
    u = _get_user(connect, user_id)
    try:
        return int(float(u.get('balance') or 0)) if u else 0
    except (TypeError, ValueError):
        return 0


def _change_balance(connect, user_id, delta: int):
    sign = '+' if delta >= 0 else '-'
    cdb_query(connect, f"UPDATE users SET balance = balance {sign} {abs(int(delta))} WHERE user_id = '{user_id}'")


def _fmt(n) -> str:
    return f"{int(n):,}".replace(',', ' ')


def ton_uzs() -> int:
    """1 TON narxi so'mda (+ ustama). 5 daqiqa keshlanadi."""
    if time.time() - _price_cache['t'] < 300:
        return _price_cache['v']
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={'ids': 'the-open-network', 'vs_currencies': 'uzs'}, timeout=8)
        price = float(r.json()['the-open-network']['uzs'])
        _price_cache.update(t=time.time(), v=int(max(price + MARKUP_UZS, MIN_TON_UZS)))
    except Exception:
        logger.warning("TON narxini olib bo'lmadi, oxirgi/minimal narx ishlatiladi")
        _price_cache['t'] = time.time() - 240  # 1 daqiqadan keyin qayta uriniladi
    return _price_cache['v']


def price_stars(qty: int) -> int:
    return int(qty * (STARS_50_TON / 50) * ton_uzs())


def price_premium(months: int) -> int:
    return int(PREMIUM_TON[months] * ton_uzs())


def price_ton(amount: float) -> int:
    return int(amount * ton_uzs())


def _wallet_ready() -> bool:
    return bool(settings.MNEMONIC_LIST)


def _log(bot, text):
    try:
        bot.sendMessage({'chat_id': settings.LOG_CHANNEL_ID, 'text': text, 'parse_mode': 'HTML'})
    except Exception:
        pass


# ------------------------------------------------------------------ boshlash

def _start_stars(bot, chat_id, message_id):
    rows, row = [], []
    for q in STARS_PACKS:
        row.append({'text': f"⭐ {q} — {_fmt(price_stars(q))} so'm", 'callback_data': f"st_q_{q}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{'text': "✏️ Boshqa miqdor", 'callback_data': 'st_q_custom'}])
    rows.append(BACK)
    _show(bot, chat_id, message_id,
          f"⭐ <b>Telegram Stars</b>\n\nMiqdorni tanlang (minimal {STARS_MIN} ta):", rows)


def _start_premium(bot, chat_id, message_id):
    rows = [[{'text': f"💎 {m} oy — {_fmt(price_premium(m))} so'm", 'callback_data': f"pr_m_{m}"}]
            for m in (3, 6, 12)]
    rows.append(BACK)
    _show(bot, chat_id, message_id, "💎 <b>Telegram Premium</b>\n\nMuddatni tanlang:", rows)


def _start_ton(bot, uid, chat_id, message_id):
    _set_flow(uid, {'kind': 'ton', 'state': 'amount'})
    _show(bot, chat_id, message_id,
          f"💰 <b>TON olish</b>\n\n1 TON ≈ {_fmt(ton_uzs())} so'm\n"
          f"Necha TON kerak? ({TON_MIN:g} dan {TON_MAX:g} gacha) Son yuboring, masalan: <code>2.5</code>",
          [BACK])


def _start_gift(bot, chat_id, message_id):
    res = bot.getAvailableGifts({})
    gifts = []
    try:
        gifts = sorted(res.result.gifts, key=lambda g: g.star_count)[:8]
    except Exception:
        pass
    if not gifts:
        return _show(bot, chat_id, message_id,
                     "🎁 Hozircha sovg'alar ro'yxatini olib bo'lmadi. Keyinroq urinib ko'ring.", [BACK])
    rows = []
    for g in gifts:
        label = f"{getattr(g, 'emoji', '') or getattr(getattr(g, 'sticker', None), 'emoji', '🎁')} " \
                f"{g.star_count}⭐ — {_fmt(price_stars(g.star_count))} so'm"
        rows.append([{'text': label, 'callback_data': f"gf_{g.id}_{g.star_count}"}])
    rows.append(BACK)
    _show(bot, chat_id, message_id,
          "🎁 <b>Telegram Gift</b>\n\nSovg'ani tanlang (sovg'a sizning akkauntingizga yuboriladi):", rows)


# ------------------------------------------------------------------ tasdiqlash ekrani

def _confirm_screen(bot, uid, chat_id, message_id, flow, connect):
    kind = flow['kind']
    price = flow['price']
    if kind == 'stars':
        what = f"⭐ {flow['qty']} Stars\n👤 Qabul qiluvchi: @{_esc(flow['username'])} ({_esc(flow.get('name', ''))})"
    elif kind == 'premium':
        what = f"💎 Premium — {flow['months']} oy\n👤 Qabul qiluvchi: @{_esc(flow['username'])} ({_esc(flow.get('name', ''))})"
    elif kind == 'ton':
        what = f"💰 {flow['amount']:g} TON\n📬 Hamyon: <code>{_esc(flow['address'])}</code>"
    else:
        what = f"🎁 Gift ({flow['stars']}⭐)\n👤 Sizning akkauntingizga"
    flow['state'] = 'confirm'
    _set_flow(uid, flow)
    bal = _balance(connect, uid)
    text = (f"🧾 <b>Buyurtmani tasdiqlang</b>\n\n{what}\n\n"
            f"💵 Narxi: <b>{_fmt(price)} so'm</b>\n💳 Balansingiz: {_fmt(bal)} so'm")
    _show(bot, chat_id, message_id, text,
          [[{'text': "✅ Tasdiqlash", 'callback_data': f"ok_{kind}"}], BACK])


# ------------------------------------------------------------------ bajarish

def _deliver(kind, flow) -> bool:
    if kind in ('stars', 'premium'):
        from BuyStars.main import buy
        amount = flow['qty'] if kind == 'stars' else flow['months']
        return asyncio.run(buy(kind, '@' + flow['username'], amount))
    if kind == 'ton':
        from BuyTon.main import TonSender
        return asyncio.run(TonSender().send(flow['address'], flow['amount']))
    return False


def _execute(bot, cq, connect, uid, chat_id, message_id, kind):
    flow = _get_flow(uid)
    if not flow or flow.get('kind') != kind or flow.get('state') != 'confirm':
        return _answer(bot, cq, "Buyurtma eskirgan. Qaytadan boshlang.", True)
    _clear_flow(uid)  # ikki marta bosishdan himoya

    price = int(flow['price'])
    if _balance(connect, uid) < price:
        _answer(bot, cq, "Balansingizda mablag' yetarli emas!", True)
        admin = f"tg://user?id={settings.ADMIN_ID}"
        return _show(bot, chat_id, message_id,
                     f"❌ Balans yetarli emas.\nKerak: {_fmt(price)} so'm, sizda: {_fmt(_balance(connect, uid))} so'm.\n\n"
                     f"Balansni to'ldirish uchun <a href=\"{admin}\">admin</a> bilan bog'laning.", [BACK])

    if kind != 'gift' and not _wallet_ready():
        _answer(bot, cq, "Xizmat vaqtincha ishlamayapti.", True)
        logger.error("MNEMONIC bo'sh — config/settings.py ni to'ldiring!")
        return _show(bot, chat_id, message_id,
                     "⚠️ Xizmat vaqtincha ishlamayapti. Pulingiz yechilmadi. Keyinroq urinib ko'ring.", [BACK])

    _answer(bot, cq, "⏳ Bajarilmoqda...")
    _change_balance(connect, uid, -price)
    _show(bot, chat_id, message_id, "⏳ <b>Buyurtma bajarilmoqda...</b> Iltimos kuting.", [])

    ok = False
    try:
        if kind == 'gift':
            res = bot.sendGift({'user_id': uid, 'gift_id': flow['gift_id']})
            ok = bool(res is not None and getattr(res, 'ok', False))
        else:
            ok = bool(_deliver(kind, flow))
    except Exception:
        logger.exception("Xaridda xato (kind=%s, user=%s)", kind, uid)

    if ok:
        _show(bot, chat_id, message_id,
              f"✅ <b>Xarid muvaffaqiyatli!</b>\n\n{_summary(flow)}\n💵 To'landi: {_fmt(price)} so'm", [BACK])
        _log(bot, f"✅ {kind} | user {uid} | {_summary(flow)} | {_fmt(price)} so'm")
    else:
        _change_balance(connect, uid, price)  # qaytarish
        _show(bot, chat_id, message_id,
              "❌ Xarid amalga oshmadi. Pulingiz balansingizga qaytarildi. Keyinroq qayta urinib ko'ring.", [BACK])
        _log(bot, f"❌ {kind} xato | user {uid} | {_summary(flow)} | pul qaytarildi")


def _summary(flow) -> str:
    k = flow['kind']
    if k == 'stars':
        return f"{flow['qty']} Stars → @{flow['username']}"
    if k == 'premium':
        return f"Premium {flow['months']} oy → @{flow['username']}"
    if k == 'ton':
        return f"{flow['amount']:g} TON → {flow['address']}"
    return f"Gift {flow['stars']}⭐"


# ------------------------------------------------------------------ callback router

def handle_callback(bot, cq, connect, chat_id, message_id) -> bool:
    data = cq.data or ''
    uid = tg_from(cq).id

    if data == 'buy_stars':
        _clear_flow(uid); _answer(bot, cq); _start_stars(bot, chat_id, message_id)
    elif data == 'buy_premium':
        _clear_flow(uid); _answer(bot, cq); _start_premium(bot, chat_id, message_id)
    elif data == 'buy_ton':
        _answer(bot, cq); _start_ton(bot, uid, chat_id, message_id)
    elif data == 'buy_gift':
        _clear_flow(uid); _answer(bot, cq); _start_gift(bot, chat_id, message_id)

    elif data == 'st_q_custom':
        _set_flow(uid, {'kind': 'stars', 'state': 'qty'})
        _answer(bot, cq)
        _show(bot, chat_id, message_id,
              f"✏️ Necha Stars kerak? {STARS_MIN} dan {STARS_MAX} gacha butun son yuboring:", [BACK])
    elif data.startswith('st_q_'):
        qty = int(data.split('_')[2])
        _set_flow(uid, {'kind': 'stars', 'state': 'username', 'qty': qty, 'price': price_stars(qty)})
        _answer(bot, cq)
        _show(bot, chat_id, message_id,
              f"⭐ {qty} Stars — {_fmt(price_stars(qty))} so'm\n\nStars qabul qiluvchi <b>@username</b> ni yuboring:", [BACK])
    elif data.startswith('pr_m_'):
        months = int(data.split('_')[2])
        if months not in PREMIUM_TON:
            return _answer(bot, cq) or True
        _set_flow(uid, {'kind': 'premium', 'state': 'username', 'months': months, 'price': price_premium(months)})
        _answer(bot, cq)
        _show(bot, chat_id, message_id,
              f"💎 Premium {months} oy — {_fmt(price_premium(months))} so'm\n\nQabul qiluvchi <b>@username</b> ni yuboring:", [BACK])
    elif data.startswith('gf_'):
        parts = data.split('_')
        gift_id, stars = parts[1], int(parts[2])
        flow = {'kind': 'gift', 'gift_id': gift_id, 'stars': stars, 'price': price_stars(stars)}
        _answer(bot, cq)
        _confirm_screen(bot, uid, chat_id, message_id, flow, connect)
    elif data in ('ok_stars', 'ok_premium', 'ok_ton', 'ok_gift'):
        _execute(bot, cq, connect, uid, chat_id, message_id, data[3:])
    else:
        return False
    return True


# ------------------------------------------------------------------ matnli xabarlar

def handle_text(bot, msg, connect) -> bool:
    """Foydalanuvchi yozgan matnni joriy oqimga qarab qayta ishlaydi. Qayta ishlansa True."""
    uid = tg_from(msg).id
    chat_id = msg.chat.id
    text = (getattr(msg, 'text', '') or '').strip()

    # --- admin: /addbalance <user_id> <so'm> ---
    if text.startswith('/addbalance') and uid == settings.ADMIN_ID:
        parts = text.split()
        try:
            target, amount = parts[1], int(parts[2])
            if not _get_user(connect, target):
                raise ValueError
            _change_balance(connect, target, amount)
            bot.sendMessage({'chat_id': chat_id, 'text': f"✅ {target} balansi {amount:+} so'mga o'zgardi. Hozir: {_balance(connect, target)}"})
            bot.sendMessage({'chat_id': target, 'text': f"💳 Balansingiz {_fmt(amount)} so'mga to'ldirildi."})
        except (IndexError, ValueError):
            bot.sendMessage({'chat_id': chat_id, 'text': "Foydalanish: /addbalance <user_id> <summa>\nFoydalanuvchi bazada bo'lishi kerak."})
        return True

    flow = _get_flow(uid)
    if not flow or text.startswith('/'):
        return False
    state, kind = flow.get('state'), flow.get('kind')

    def say(t):
        bot.sendMessage({'chat_id': chat_id, 'text': t, 'parse_mode': 'HTML', 'reply_markup': _kb([BACK])})

    if kind == 'stars' and state == 'qty':
        if not text.isdigit() or not (STARS_MIN <= int(text) <= STARS_MAX):
            say(f"❌ {STARS_MIN} dan {STARS_MAX} gacha butun son yuboring.")
            return True
        qty = int(text)
        flow.update(state='username', qty=qty, price=price_stars(qty))
        _set_flow(uid, flow)
        say(f"⭐ {qty} Stars — {_fmt(flow['price'])} so'm\n\nQabul qiluvchi <b>@username</b> ni yuboring:")
        return True

    if kind in ('stars', 'premium') and state == 'username':
        uname = text.lstrip('@')
        if not USERNAME_RE.match(uname):
            say("❌ Username noto'g'ri. Masalan: <code>@username</code>")
            return True
        info = chekusername(uname) if kind == 'stars' else chekPremiumUsername(uname, flow['months'])
        if info.get('error'):
            say("⚠️ Tekshirib bo'lmadi, birozdan so'ng qayta urinib ko'ring.")
            return True
        if kind == 'premium' and info.get('has_premium'):
            say("❌ Bu akkauntda allaqachon Telegram Premium bor.")
            return True
        if not info.get('exists'):
            say("❌ Bunday foydalanuvchi topilmadi. Username'ni tekshirib qayta yuboring.")
            return True
        flow.update(username=uname, name=info.get('name', uname))
        _confirm_screen(bot, uid, chat_id, 0, flow, connect)
        return True

    if kind == 'ton' and state == 'amount':
        try:
            amount = round(float(text.replace(',', '.')), 4)
        except ValueError:
            say("❌ Son yuboring, masalan: <code>2.5</code>")
            return True
        if not (TON_MIN <= amount <= TON_MAX):
            say(f"❌ {TON_MIN:g} dan {TON_MAX:g} TON gacha bo'lishi kerak.")
            return True
        flow.update(state='address', amount=amount, price=price_ton(amount))
        _set_flow(uid, flow)
        say(f"💰 {amount:g} TON — {_fmt(flow['price'])} so'm\n\nTON hamyon manzilingizni yuboring:")
        return True

    if kind == 'ton' and state == 'address':
        if not TON_ADDR_RE.match(text):
            say("❌ Hamyon manzili noto'g'ri. (EQ... yoki UQ... bilan boshlanadi, 48 belgi)")
            return True
        flow['address'] = text
        _confirm_screen(bot, uid, chat_id, 0, flow, connect)
        return True

    return False
