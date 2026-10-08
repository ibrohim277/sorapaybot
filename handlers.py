"""
Inline tugmalar (callback_query) handlerlari.

main.py webhook() ichidan chaqiriladi:
    handle_callback(bot, cq, connect, send_main_menu, majburiy)

Muhim qoida: HAR BIR callback_query'ga answerCallbackQuery yuboriladi —
aks holda Telegram'da tugma ustida "soat" belgisi osilib qoladi va
tugma "ishlamayapti" bo'lib ko'rinadi.
"""
import json
import logging

from telegram_bot import tg_from
<<<<<<< HEAD
import orders
=======
<<<<<<< HEAD
import orders
=======
>>>>>>> 8023c4adf49734abcd89abb10aec310e4fe50bf5
>>>>>>> 396de28125b901daa7a9b9d4c7dad52d1eeab4c7
from config.channel_sql import (
    cdb_prepare, cdb_stmt_bind_param, cdb_stmt_execute, cdb_stmt_get_result,
    cdb_stmt_close, cdb_fetch_assoc, cdb_num_rows,
)

logger = logging.getLogger("sorapay.handlers")

BACK_KB = {'inline_keyboard': [[{'text': "⬅️ Orqaga", 'callback_data': 'menu'}]]}

_bot_username_cache = {'v': None}


# ------------------------------------------------------------------ yordamchilar

def _answer(bot, cq, text=None, alert=False):
    params = {'callback_query_id': cq.id}
    if text:
        params['text'] = text
        params['show_alert'] = alert
    bot.answerCallbackQuery(params)


def _get_user(connect, user_id):
    stmt = cdb_prepare(connect, "SELECT * FROM users WHERE user_id = ?")
    cdb_stmt_bind_param(stmt, "s", str(user_id))
    cdb_stmt_execute(stmt)
    row = cdb_fetch_assoc(cdb_stmt_get_result(stmt))
    cdb_stmt_close(stmt)
    return row


def _update_user(connect, user_id, **fields):
    """Xavfsiz UPDATE: qiymatlar ekranlanadi (first_name'dagi ' belgisi buzmaydi)."""
    sets, vals = [], []
    for k, v in fields.items():
        sets.append(f"{k} = ?")
        vals.append(str(v))
    stmt = cdb_prepare(connect, f"UPDATE users SET {', '.join(sets)} WHERE user_id = ?")
    cdb_stmt_bind_param(stmt, "s" * (len(vals) + 1), *vals, str(user_id))
    cdb_stmt_execute(stmt)
    cdb_stmt_close(stmt)


def _html_escape(s) -> str:
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _edit(bot, chat_id, message_id, text, kb=BACK_KB):
    bot.editMessageText({
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML',
        'reply_markup': json.dumps(kb),
    })


def _bot_username(bot):
    if not _bot_username_cache['v']:
        res = bot.getMe()
        _bot_username_cache['v'] = getattr(getattr(res, 'result', None), 'username', None)
    return _bot_username_cache['v']


# ------------------------------------------------------------------ bo'limlar

def show_profile(bot, cq, connect, chat_id, message_id):
    u = _get_user(connect, tg_from(cq).id)
    if not u:
        return _answer(bot, cq, "Profil topilmadi. /start bosing.", True)
    text = (
        "👤 <b>Profilim</b>\n\n"
        f"🆔 ID: <code>{_html_escape(u.get('user_id'))}</code>\n"
        f"📛 Ism: {_html_escape(u.get('first_name', ''))}\n"
        f"🔗 Username: @{_html_escape(u.get('username', ''))}\n"
        f"💰 Balans: {_html_escape(u.get('balance', 0))}\n"
        f"👥 Takliflar: {_html_escape(u.get('ref', 0))}\n"
        f"📅 Ro'yxatdan o'tgan: {_html_escape(u.get('sana', '-'))}"
    )
    _answer(bot, cq)
    _edit(bot, chat_id, message_id, text)


def show_stats(bot, cq, connect, chat_id, message_id):
    u = _get_user(connect, tg_from(cq).id)
    if not u:
        return _answer(bot, cq, "Ma'lumot topilmadi. /start bosing.", True)
    text = (
        "📊 <b>Statistikam</b>\n\n"
        f"👥 Taklif qilgan do'stlar: {_html_escape(u.get('ref', 0))}\n"
        f"💰 Balans: {_html_escape(u.get('balance', 0))}\n"
        f"📅 Botda: {_html_escape(u.get('sana', '-'))} dan beri"
    )
    _answer(bot, cq)
    _edit(bot, chat_id, message_id, text)


def show_referral(bot, cq, connect, chat_id, message_id):
    u = _get_user(connect, tg_from(cq).id)
    if not u:
        return _answer(bot, cq, "Ma'lumot topilmadi. /start bosing.", True)
    uname = _bot_username(bot)
    link = f"https://t.me/{uname}?start={u.get('user_ref_id')}" if uname else "(bot username olinmadi)"
    text = (
        "👥 <b>Referal</b>\n\n"
        "Do'stlaringizni quyidagi havola orqali taklif qiling:\n"
        f"<code>{_html_escape(link)}</code>\n\n"
        f"Hozirgacha taklif qilganlar: <b>{_html_escape(u.get('ref', 0))}</b>"
    )
    _answer(bot, cq)
    _edit(bot, chat_id, message_id, text)


def handle_captcha(bot, cq, connect, chat_id, message_id, majburiy):
    chosen = cq.data.split('_', 1)[1]
    user_id = tg_from(cq).id
    u = _get_user(connect, user_id)
    if not u:
        return _answer(bot, cq, "Qayta /start bosing.", True)

    if str(u.get('captcha_passed')) == '1':
        _answer(bot, cq, "Siz allaqachon tasdiqlangansiz.")
        return

    if str(u.get('captcha')) != chosen:
        stmt = cdb_prepare(connect, "UPDATE users SET captcha_try = captcha_try + 1 WHERE user_id = ?")
        cdb_stmt_bind_param(stmt, "s", str(user_id))
        cdb_stmt_execute(stmt)
        cdb_stmt_close(stmt)
        _answer(bot, cq, "❌ Noto'g'ri javob, qayta urinib ko'ring.", True)
        return

    _update_user(connect, user_id, captcha_passed=1, captcha_required=0)

    # Taklif qilgan odamning "ref" hisoblagichini oshirish
    inviter_ref = u.get('ref_id')
    if inviter_ref:
        stmt = cdb_prepare(connect, "UPDATE users SET ref = ref + 1 WHERE user_ref_id = ?")
        cdb_stmt_bind_param(stmt, "s", str(inviter_ref))
        cdb_stmt_execute(stmt)
        cdb_stmt_close(stmt)

    _answer(bot, cq, "✅ Tasdiqlandi!")
    bot.deleteMessage({'chat_id': chat_id, 'message_id': message_id})
    majburiy(user_id, bot, False, getattr(tg_from(cq), 'first_name', '') or '')


<<<<<<< HEAD
# ------------------------------------------------------------------ router

=======
<<<<<<< HEAD
# ------------------------------------------------------------------ router

=======
def not_ready(bot, cq, name):
    logger.info("Hali yozilmagan bo'lim bosildi: %s (user=%s)", name, tg_from(cq).id)
    _answer(bot, cq, f"🛠 «{name}» bo'limi hali tayyor emas. Tez orada ishga tushadi!", True)


# ------------------------------------------------------------------ router

NOT_READY_TITLES = {
    'buy_stars': "Stars olish",
    'buy_premium': "Premium olish",
    'buy_gift': "Gift olish",
    'buy_ton': "Ton olish",
}


>>>>>>> 8023c4adf49734abcd89abb10aec310e4fe50bf5
>>>>>>> 396de28125b901daa7a9b9d4c7dad52d1eeab4c7
def handle_callback(bot, cq, connect, send_main_menu, majburiy) -> None:
    data = cq.data or ''
    msg = getattr(cq, 'message', None)
    chat_id = msg.chat.id if msg else tg_from(cq).id
    message_id = msg.message_id if msg else 0
    first_name = getattr(tg_from(cq), 'first_name', '') or ''

    if data == 'check_obuna':
        return  # main.py ichida check_obuna_status() o'zi hal qiladi

    try:
        if data == 'menu':
            _answer(bot, cq)
            if message_id:
                bot.deleteMessage({'chat_id': chat_id, 'message_id': message_id})
            send_main_menu(bot, tg_from(cq).id, first_name)
        elif data == 'profil':
            show_profile(bot, cq, connect, chat_id, message_id)
        elif data == 'statistika':
            show_stats(bot, cq, connect, chat_id, message_id)
        elif data == 'ref':
            show_referral(bot, cq, connect, chat_id, message_id)
        elif data.startswith('captcha_'):
            handle_captcha(bot, cq, connect, chat_id, message_id, majburiy)
<<<<<<< HEAD
        elif orders.handle_order_callback(bot, cq, connect, send_main_menu):
            pass   # buy_*, stars_*, prem_*, ton_*, gift_*, ord_*, adm_*
=======
<<<<<<< HEAD
        elif orders.handle_order_callback(bot, cq, connect, send_main_menu):
            pass   # buy_*, stars_*, prem_*, ton_*, gift_*, ord_*, adm_*
=======
        elif data in NOT_READY_TITLES:
            not_ready(bot, cq, NOT_READY_TITLES[data])
>>>>>>> 8023c4adf49734abcd89abb10aec310e4fe50bf5
>>>>>>> 396de28125b901daa7a9b9d4c7dad52d1eeab4c7
        else:
            logger.warning("Noma'lum callback_data: %r", data)
            _answer(bot, cq)
    except Exception:
        logger.exception("Callback handlerda xato (data=%r)", data)
<<<<<<< HEAD
=======
<<<<<<< HEAD
>>>>>>> 396de28125b901daa7a9b9d4c7dad52d1eeab4c7
        try:
            _answer(bot, cq, "Xatolik yuz berdi, birozdan so'ng qayta urinib ko'ring.", True)
        except Exception:
            pass
<<<<<<< HEAD
=======
=======
        try:    
            _answer(bot, cq, "Xatolik yuz berdi, birozdan so'ng qayta urinib ko'ring.", True)
        except Exception:
            pass
>>>>>>> 8023c4adf49734abcd89abb10aec310e4fe50bf5
>>>>>>> 396de28125b901daa7a9b9d4c7dad52d1eeab4c7
