"""
index.php ning Python porti — asosiy bot webhook handleri.
Flask orqali ishlaydi: POST /index.php (yoki /) ga Telegram webhook yuboradi.
"""
import os
import re
import threading
import collections
import json
import logging
from datetime import datetime
from urllib.parse import urlencode

from flask import Flask, request

from config import settings
from config.channel_sql import (
    cdb_connect, cdb_query, cdb_prepare, cdb_stmt_bind_param, cdb_stmt_execute,
    cdb_stmt_get_result, cdb_stmt_close, cdb_fetch_assoc, cdb_fetch_all, cdb_num_rows,
    cdb_real_escape_string, cdb_affected_rows,
)
from telegram_bot import Begzod, tg_from
from handlers import handle_callback
import orders
import diagnostics
from config.username_info import chekusername, chekPremiumUsername

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sorapay.main")

app = Flask(__name__)

connect = cdb_connect(settings.BOT_TOKEN, settings.DB_CHANNEL_ID, settings.DB_DATA_DIR)

MAIN_MENU = [
    [
        {'text': "Stars olish", 'callback_data': 'buy_stars', 'icon_custom_emoji_id': "5363844691580177304"},
        {'text': "Premium olish", 'callback_data': 'buy_premium', 'icon_custom_emoji_id': "5388584703932522832"},
    ],
    [
        {'text': "Gift olish", 'callback_data': 'buy_gift', 'icon_custom_emoji_id': "5293983582472135373"},
        {'text': "Ton olish", 'callback_data': 'buy_ton', 'icon_custom_emoji_id': "5406976471153545018"},
    ],
    [{'text': "Statistikam", 'callback_data': 'statistika', 'icon_custom_emoji_id': "5936143551854285132"}],
    [
        {'text': "Referal", 'callback_data': 'ref', 'icon_custom_emoji_id': "5409257566939134596"},
        {'text': "Profilim", 'callback_data': 'profil', 'icon_custom_emoji_id': "5409014699423446355"},
    ],
]


def main_menu_text(first_name: str) -> str:
    return (
        f"<tg-emoji emoji-id='5994750571041525522'>👋</tg-emoji> <i><b><u>Assalom aleykum {first_name} "
        "SoraPay botga xush kelibsiz!</u></b></i>\n\n"
        "<tg-emoji emoji-id='5793933761594789855'>💬</tg-emoji> <i>Bot orqali quyidagilarni xarid qilish "
        "mumkin. «Tez va Xavfsiz»</i>\n"
        "<blockquote expandable><tg-emoji emoji-id='5956148757899776734'>⭐️</tg-emoji>Telegram Stars - "
        "yulduzcha\n"
        "<tg-emoji emoji-id='5956561749070057536'>⭐️</tg-emoji>Telegram Premium\n"
        "<tg-emoji emoji-id='5875180111744995604'>🎁</tg-emoji>Telegram Gift sovg'alar\n"
        "<tg-emoji emoji-id='6028530359975548369'>💎</tg-emoji> TON coin</blockquote>\n\n"
        "<b>Boshlash uchun xizmatni tanlang:</b> <tg-emoji emoji-id='5470112026548257635'>⬇️</tg-emoji>"
    )


def step_path(*parts) -> str:
    return os.path.join(settings.STEP_DIR, *parts)


def read_step(filename: str):
    path = step_path(filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return None


def write_step(filename: str, content) -> None:
    with open(step_path(filename), 'w', encoding='utf-8') as f:
        f.write(str(content))


def remove_step(filename: str) -> None:
    path = step_path(filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def clear_purchase_steps(user_id) -> None:
    """Har bir xarid oqimi (yoki asosiy menyuga qaytishdan) oldin step fayllarini tozalaydi."""
    for suffix in (
        '.step', '_quantity.txt', '_month.txt', '_custom_emoji.txt', '_emoji.txt',
        '_gift_id.txt', '_uzs_price.txt', '_uzs_summasi.txt', '_quantity_ton.txt',
        '.amount', '.username', '.txt', '.order',
    ):
        remove_step(f"{user_id}{suffix}")


def send_main_menu(bot: Begzod, user_id, first_name: str) -> None:
    bot.sendMessage({
        'chat_id': user_id,
        'text': main_menu_text(first_name),
        'parse_mode': 'HTML',
        'reply_markup': json.dumps({'inline_keyboard': MAIN_MENU}),
    })
    clear_purchase_steps(user_id)


# ===================================================================
# majburiy obuna (majburiy kanallar/botlar) tekshiruvi
# ===================================================================

def zayafka_qabul(user_id, chat_id, status: str) -> None:
    stmt = cdb_prepare(connect, "INSERT INTO joinRequest (user_id, chat_id, status) VALUES (?, ?, ?) ON DUPLICATE KEY UPDATE status = ?")
    cdb_stmt_bind_param(stmt, "isss", user_id, chat_id, status, status)
    cdb_stmt_execute(stmt)
    cdb_stmt_close(stmt)


def tugma_edit(user_id, bot: Begzod, first_name: str = '') -> None:
    channels = cdb_fetch_all(cdb_query(connect, "SELECT * FROM zayafka"))
    public_channels = cdb_fetch_all(cdb_query(connect, "SELECT * FROM kanal"))
    bots = cdb_fetch_all(cdb_query(connect, "SELECT bot_tokenn, bot_link FROM bots"))
    majsiz = cdb_fetch_all(cdb_query(connect, "SELECT * FROM majburiysiz"))

    keyboard = []
    all_subscribed = True

    for channel in channels:
        stmt = cdb_prepare(connect, "SELECT status FROM joinRequest WHERE user_id = ? AND chat_id = ?")
        cdb_stmt_bind_param(stmt, "is", user_id, channel['chat_id'])
        cdb_stmt_execute(stmt)
        res = cdb_stmt_get_result(stmt)
        status = cdb_fetch_assoc(res)['status'] if cdb_num_rows(res) > 0 else 'not_member'
        cdb_stmt_close(stmt)
        if status not in ('member', 'pending'):
            all_subscribed = False
            keyboard.append([{'text': "Obuna bo'lish", 'url': channel['invite_link'], 'icon_custom_emoji_id': "5409380965644514142"}])

    for channel in public_channels:
        member = bot.getChatMember({'chat_id': channel['chat_id'], 'user_id': user_id})
        is_member = getattr(getattr(member, 'result', None), 'status', None)
        if is_member not in ("member", "administrator", "creator"):
            all_subscribed = False
            keyboard.append([{'text': "Obuna bo'lish", 'url': channel['kanal_url'], 'icon_custom_emoji_id': "5409380965644514142"}])

    for channell in majsiz:
        keyboard.append([{'text': "Obuna bo'lish", 'url': channell['link'], 'icon_custom_emoji_id': "5778168620278354602"}])

    for other_bot in bots:
        import requests as _requests
        url = f"https://api.telegram.org/bot{other_bot['bot_tokenn']}/sendchataction?chat_id={user_id}&action=typing"
        try:
            resp = _requests.get(url, timeout=5)
            data = resp.json() if resp.ok else {'ok': False}
        except Exception:
            data = {'ok': False}
        if not data.get('ok'):
            all_subscribed = False
            keyboard.append([{'text': "Obuna bo'lish", 'url': other_bot['bot_link'], 'icon_custom_emoji_id': "5409380965644514142"}])

    keyboard.append([{'text': "Tasdiqlash", 'callback_data': 'check_obuna', 'icon_custom_emoji_id': "5408909562919007848"}])

    message_id = read_step(f"{user_id}.txt")
    if message_id:
        bot.editMessageReplyMarkup({
            'chat_id': user_id,
            'message_id': message_id,
            'reply_markup': json.dumps({'inline_keyboard': keyboard}),
        })

    if all_subscribed:
        if message_id:
            bot.deleteMessage({'chat_id': user_id, 'message_id': message_id})
        send_main_menu(bot, user_id, first_name)


def check_obuna_status(user_id, bot: Begzod, is_confirm_action: bool = False, first_name: str = '') -> bool:
    """PHP'dagi check() funksiyasi — 'check_obuna' callback tugmasi bosilganda ishlaydi."""
    channels = cdb_fetch_all(cdb_query(connect, "SELECT * FROM zayafka"))
    public_channels = cdb_fetch_all(cdb_query(connect, "SELECT * FROM kanal"))
    bots = cdb_fetch_all(cdb_query(connect, "SELECT bot_tokenn, bot_link FROM bots"))

    all_subscribed = True
    for channel in channels:
        stmt = cdb_prepare(connect, "SELECT status FROM joinRequest WHERE user_id = ? AND chat_id = ?")
        cdb_stmt_bind_param(stmt, "is", user_id, channel['chat_id'])
        cdb_stmt_execute(stmt)
        res = cdb_stmt_get_result(stmt)
        status = cdb_fetch_assoc(res)['status'] if cdb_num_rows(res) > 0 else 'not_member'
        cdb_stmt_close(stmt)
        if status not in ('member', 'pending'):
            all_subscribed = False
            break

    if all_subscribed:
        for channel in public_channels:
            member = bot.getChatMember({'chat_id': channel['chat_id'], 'user_id': user_id})
            is_member = getattr(getattr(member, 'result', None), 'status', None)
            if is_member not in ("member", "administrator", "creator"):
                all_subscribed = False
                break

    for other_bot in bots:
        import requests as _requests
        url = f"https://api.telegram.org/bot{other_bot['bot_tokenn']}/sendchataction?chat_id={user_id}&action=typing"
        try:
            resp = _requests.get(url, timeout=5)
            data = resp.json() if resp.ok else {'ok': False}
        except Exception:
            data = {'ok': False}
        if not data.get('ok'):
            all_subscribed = False
            break

    if all_subscribed and is_confirm_action:
        mid = read_step(f"{user_id}.txt")
        if mid:
            bot.deleteMessage({'chat_id': user_id, 'message_id': mid})
        send_main_menu(bot, user_id, first_name)
        return all_subscribed

    if not all_subscribed:
        update = bot.update()
        if getattr(update, 'callback_query', None):
            bot.answerCallbackQuery({
                'callback_query_id': update.callback_query.id,
                'text': "Siz hali barcha kanallarga yoki botlarga obuna bo'lmagansiz!",
                'show_alert': True,
            })
        tugma_edit(user_id, bot, first_name)

    return all_subscribed


def majburiy(user_id, bot: Begzod, edit_buttons: bool = False, first_name: str = '') -> None:
    """PHP'dagi majburiy() funksiyasi — /start bosilganda chaqiriladi."""
    channels = cdb_fetch_all(cdb_query(connect, "SELECT * FROM zayafka"))
    public_channels = cdb_fetch_all(cdb_query(connect, "SELECT * FROM kanal"))
    bots = cdb_fetch_all(cdb_query(connect, "SELECT bot_tokenn, bot_link FROM bots"))
    majsiz = cdb_fetch_all(cdb_query(connect, "SELECT * FROM majburiysiz"))

    keyboard = []
    all_subscribed = True

    for channel in channels:
        stmt = cdb_prepare(connect, "SELECT status FROM joinRequest WHERE user_id = ? AND chat_id = ?")
        cdb_stmt_bind_param(stmt, "is", user_id, channel['chat_id'])
        cdb_stmt_execute(stmt)
        res = cdb_stmt_get_result(stmt)
        status = cdb_fetch_assoc(res)['status'] if cdb_num_rows(res) > 0 else 'not_member'
        cdb_stmt_close(stmt)
        if status not in ('member', 'pending'):
            all_subscribed = False
            keyboard.append([{'text': "Obuna bo'lish", 'url': channel['invite_link'], 'icon_custom_emoji_id': "5409380965644514142"}])

    for channel in public_channels:
        member = bot.getChatMember({'chat_id': channel['chat_id'], 'user_id': user_id})
        is_member = getattr(getattr(member, 'result', None), 'status', None) or 'left'
        if is_member not in ("member", "administrator", "creator"):
            all_subscribed = False
            keyboard.append([{'text': "Obuna bo'lish", 'url': channel['kanal_url'], 'icon_custom_emoji_id': "5409380965644514142"}])

    for channell in majsiz:
        keyboard.append([{'text': "Obuna bo'lish", 'url': channell['link'], 'icon_custom_emoji_id': "5778168620278354602"}])

    for other_bot in bots:
        import requests as _requests
        url = f"https://api.telegram.org/bot{other_bot['bot_tokenn']}/sendchataction?chat_id={user_id}&action=typing"
        try:
            resp = _requests.get(url, timeout=5)
            data = resp.json() if resp.ok else {'ok': False}
        except Exception:
            data = {'ok': False}
        if not data.get('ok'):
            all_subscribed = False
            keyboard.append([{'text': "Obuna bo'lish", 'url': other_bot['bot_link'], 'icon_custom_emoji_id': "5409380965644514142"}])

    if not all_subscribed:
        keyboard.append([{'text': "Tasdiqlash", 'callback_data': 'check_obuna', 'icon_custom_emoji_id': "5408909562919007848"}])

        if edit_buttons:
            mid = read_step(f"{user_id}.txt")
            if mid:
                bot.editMessageReplyMarkup({
                    'chat_id': user_id,
                    'message_id': mid,
                    'reply_markup': json.dumps({'inline_keyboard': keyboard}),
                })
        else:
            old_msg = read_step(f"{user_id}.txt")
            if old_msg:
                bot.deleteMessage({'chat_id': user_id, 'message_id': old_msg})
            res = bot.sendMessage({
                'chat_id': user_id,
                'text': "Botni ishlatish uchun quyidagi kanallarimizga va botlarga obuna bo'lishingiz kerak:",
                'reply_markup': json.dumps({'inline_keyboard': keyboard}),
            })
            write_step(f"{user_id}.txt", res.result.message_id)
    else:
        old_msg = read_step(f"{user_id}.txt")
        if old_msg:
            bot.deleteMessage({'chat_id': user_id, 'message_id': old_msg})
        send_main_menu(bot, user_id, first_name)


def generate_num(length: int = 10) -> str:
    import random
    import string
    chars = string.digits + string.ascii_letters
    return ''.join(random.choice(chars) for _ in range(length))


# ===================================================================
# Narx / balans yuklash (har bir so'rovda; PHP original bilan bir xil)
# ===================================================================

def fetch_pricing():
    """PHP kodining 535-605 qatorlaridagi narx/balans hisob-kitoblarining porti.
    Qaytaradi: dict (final_price, narx, narx_premium_3/6/12, olish_mumkin, Mystars, MyProfilStars, ...)."""
    import requests as _requests

    payme_merchant_id = ""
    ton_wallet_address = "ABE1LD2v"

    premium_3 = 6.70
    premium_6 = 8.92
    premium_12 = 16.16
    stars_50 = 0.4279

    buy_price = 21000
    minimal_price = buy_price + 1500

    try:
        resp = _requests.get(settings.BASE_URL + "/BuyTon/price_ton_uzs.txt", timeout=10, verify=False)
        if resp.status_code == 200:
            ton_price = float(resp.text.strip())
            final_price = max(ton_price + 1500, minimal_price)
        else:
            final_price = minimal_price
    except Exception:
        final_price = minimal_price

    try:
        resp = _requests.get(settings.BASE_URL + "/BuyStars/balance.txt", timeout=10)
        balance = float(resp.text.strip()) if resp.status_code == 200 else 0.0
    except Exception:
        balance = 0.0

    per_unit = stars_50 / 50
    olish_mumkin = int(balance // per_unit) if per_unit else 0
    narx = int(stars_50 * final_price)
    narx_premium_3 = int(premium_3 * final_price)
    narx_premium_6 = int(premium_6 * final_price)
    narx_premium_12 = int(premium_12 * final_price)

    available = []
    if balance >= premium_3:
        available.append(3)
    if balance >= premium_6:
        available.append(6)
    if balance >= premium_12:
        available.append(12)

    try:
        resp = _requests.get(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getMyStarBalance", timeout=10)
        mystars = resp.json().get('result', {}).get('amount', 0)
    except Exception:
        mystars = 0

    try:
        resp = _requests.get(settings.BASE_URL + "/Gift_card/stars_balance.json", timeout=10)
        da = resp.json() if resp.status_code == 200 else {}
        my_profil_stars = int(da.get('balance', 0))
    except Exception:
        my_profil_stars = 0

    return {
        'payme_merchant_id': payme_merchant_id,
        'ton_wallet_address': ton_wallet_address,
        'final_price': final_price,
        'balance': balance,
        'olish_mumkin': olish_mumkin,
        'narx': narx,
        'narx_premium_3': narx_premium_3,
        'narx_premium_6': narx_premium_6,
        'narx_premium_12': narx_premium_12,
        'available': available,
        'mystars': mystars,
        'my_profil_stars': my_profil_stars,
    }


# ===================================================================
# Ro'yxatdan o'tish (registratsiya)
# ===================================================================

def register_with_referral(bot: Begzod, from_id, first_name: str, username: str, ref_id_from_text: str) -> bool:
    """/start <ref_id> — referal orqali kirgan yangi foydalanuvchi.
    True qaytarsa — so'rov shu yerda to'xtashi kerak (PHP'dagi exit() ga mos)."""
    ref_check = cdb_fetch_assoc(cdb_query(connect, f"SELECT * FROM users WHERE user_ref_id='{ref_id_from_text}'"))
    if not ref_check:
        return True  # exit()

    user_ref_id = ref_check['user_ref_id']
    self_row = cdb_fetch_assoc(cdb_query(connect, f"SELECT user_ref_id FROM users WHERE user_id='{from_id}'"))
    self_ref = self_row['user_ref_id'] if self_row else None

    if self_ref == user_ref_id:
        bot.sendMessage({
            'chat_id': from_id,
            'text': "<tg-emoji emoji-id='5881702736843511327'>⚠️</tg-emoji> <b>Referal bilan o'zingizni taklif qila olmaysiz. Qayta /start bosing</b>",
            'parse_mode': 'HTML',
        })
        return True

    check = cdb_query(connect, f"SELECT * FROM users WHERE user_id='{from_id}'")
    if cdb_num_rows(check) == 0:
        import random
        a = random.randint(1, 9)
        b = random.randint(1, 9)
        captcha = a + b
        fake1 = captcha + random.randint(1, 3)
        fake2 = max(1, captcha - random.randint(1, 3))
        options = [captcha, fake1, fake2]
        random.shuffle(options)

        pas = generate_num(10)
        now_ts = int(datetime.now().timestamp())
        sana = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cdb_query(connect, f"""INSERT INTO users SET
user_id='{from_id}',
first_name='{cdb_real_escape_string(connect, first_name)}',
username='{cdb_real_escape_string(connect, username)}',
ref_id='{user_ref_id}',
user_ref_id='{pas}',
captcha='{captcha}',
captcha_required='1',
captcha_passed='0',
captcha_try='0',
captcha_time='{now_ts}',
balance='0',
ref='0',
sana='{sana}'
""")

        keyboard = {'inline_keyboard': [[
            {'text': str(options[0]), 'callback_data': f"captcha_{options[0]}"},
            {'text': str(options[1]), 'callback_data': f"captcha_{options[1]}"},
            {'text': str(options[2]), 'callback_data': f"captcha_{options[2]}"},
        ]]}

        bot.sendMessage({
            'chat_id': from_id,
            'text': f"<tg-emoji emoji-id='5258113901106580375'>⌛️</tg-emoji> <b>Iltimos captchani yeching!</b>\n\n{a} + {b} = ?",
            'parse_mode': 'HTML',
            'reply_markup': json.dumps(keyboard),
        })
        return True
    else:
        bot.sendMessage({
            'chat_id': from_id,
            'text': "<tg-emoji emoji-id='5881702736843511327'>⚠️</tg-emoji> <b>Siz allaqachon botdasiz!</b>",
            'parse_mode': 'HTML',
        })
        return True


def silent_register_if_new(from_id, first_name: str, username: str) -> None:
    """Referalsiz birinchi marta yozgan foydalanuvchini captchasiz ro'yxatga oladi (PHP 513-529)."""
    a = cdb_fetch_assoc(cdb_query(connect, f"SELECT * FROM users WHERE user_id = '{from_id}'"))
    if not a:
        pas = generate_num(10)
        sana = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cdb_query(connect, f"""INSERT INTO users SET
user_id='{from_id}',
first_name='{cdb_real_escape_string(connect, first_name)}',
username='{cdb_real_escape_string(connect, username)}',
user_ref_id='{pas}',
captcha_required='0',
captcha_passed='1',
balance='0',
ref='0',
sana='{sana}'
""")


# ===================================================================
# WEBHOOK — asosiy kirish nuqtasi (index.php ning tanasi)
# ===================================================================

_SEEN_UPDATES = collections.deque(maxlen=2000)
_SEEN_LOCK = threading.Lock()


def _is_duplicate_update(update) -> bool:
    """Telegram sekin javobda update'ni qayta yuboradi — pul bilan ishlaganda ikki marta bajarmaslik uchun."""
    uid = getattr(update, 'update_id', None)
    if uid is None:
        return False
    with _SEEN_LOCK:
        if uid in _SEEN_UPDATES:
            return True
        _SEEN_UPDATES.append(uid)
        return False


@app.route('/', methods=['GET', 'HEAD'])
def health():
    """Render health-check uchun (405 xatosini oldini oladi)."""
    return 'SoraPayBot ishlayapti', 200


@app.route('/index.php', methods=['POST'])
@app.route('/', methods=['POST'])
def webhook():
    raw = request.get_data()
    bot = Begzod(raw)
    update = bot.update()
    if update is None or _is_duplicate_update(update):
        return 'ok'

    # Webhookni har safar qayta o'rnatish (PHP original bilan bir xil xatti-harakat)
    bot.setWebhook({
        'url': settings.BASE_URL + '/index.php',
        'allowed_updates': json.dumps(['message', 'callback_query', 'chat_join_request', 'chat_member', 'channel_post']),
    })

    msg = getattr(update, 'message', None)
    cq = getattr(update, 'callback_query', None)

    from_id = chat_id = first_name = username = text = message_id = chat_type = data_val = None

    if msg is not None:
        chat_type = msg.chat.type
        chat_id = msg.chat.id
        msg_from = tg_from(msg)
        from_id = msg_from.id
        text = getattr(msg, 'text', '') or ''
        first_name = getattr(msg_from, 'first_name', '') or ''
        username = getattr(msg_from, 'username', None) or f'user_{from_id}'
        message_id = msg.message_id

    if cq is not None:
        cq_from = tg_from(cq)
        from_id = cq_from.id
        first_name = getattr(cq_from, 'first_name', '')
        data_val = cq.data
        chat_id = cq.message.chat.id if getattr(cq, 'message', None) else from_id
        chat_type = cq.message.chat.type if getattr(cq, 'message', None) else None
        message_id = cq.message.message_id if getattr(cq, 'message', None) else 0

    # --- chat_member (kanalga a'zo bo'lish / chiqish) ---
    chat_member = getattr(update, 'chat_member', None)
    if chat_member is not None:
        chat_id_member = chat_member.chat.id
        member_user_id = tg_from(chat_member).id
        new_status = chat_member.new_chat_member.status

        if new_status in ('member', 'administrator', 'creator'):
            if os.path.exists(step_path(f"{member_user_id}.txt")):
                tugma_edit(member_user_id, bot)
        elif new_status in ('left', 'kicked', 'banned'):
            stmt = cdb_prepare(connect, "DELETE FROM joinRequest WHERE user_id = ? AND chat_id = ?")
            cdb_stmt_bind_param(stmt, "is", member_user_id, chat_id_member)
            cdb_stmt_execute(stmt)
            cdb_stmt_close(stmt)

            stmt2 = cdb_prepare(connect, "SELECT * FROM kanal WHERE chat_id = ?")
            cdb_stmt_bind_param(stmt2, "s", chat_id_member)
            cdb_stmt_execute(stmt2)
            is_our_channel = cdb_num_rows(cdb_stmt_get_result(stmt2)) > 0
            cdb_stmt_close(stmt2)

            stmt3 = cdb_prepare(connect, "SELECT * FROM zayafka WHERE chat_id = ?")
            cdb_stmt_bind_param(stmt3, "s", chat_id_member)
            cdb_stmt_execute(stmt3)
            is_zayafka = cdb_num_rows(cdb_stmt_get_result(stmt3)) > 0
            cdb_stmt_close(stmt3)

            if is_our_channel or is_zayafka:
                old_msg = read_step(f"{member_user_id}.txt")
                if old_msg:
                    bot.deleteMessage({'chat_id': member_user_id, 'message_id': old_msg})
                    remove_step(f"{member_user_id}.txt")
                majburiy(member_user_id, bot, False)

    # --- check_obuna callback ---
    if data_val == 'check_obuna':
        if check_obuna_status(from_id, bot, True, first_name or ''):
            bot.answerCallbackQuery({'callback_query_id': cq.id})

    # --- chat_join_request (majburiy kanalga so'rov yuborib qo'shilish) ---
    chat_join_request = getattr(update, 'chat_join_request', None)
    if chat_join_request is not None:
        jr_chat_id = chat_join_request.chat.id
        jr_user_id = tg_from(chat_join_request).id
        zayafka_qabul(jr_user_id, jr_chat_id, 'pending')
        tugma_edit(jr_user_id, bot)

    if not os.path.exists(settings.STEP_DIR):
        os.makedirs(settings.STEP_DIR, exist_ok=True)

    # --- /start ---
    if text in ("/start", "/start true"):
        majburiy(from_id, bot, False, first_name or '')

    # --- /start <ref_id> ---
    if text and "/start " in text:
        ref_id_from_text = text.split(" ")[1] if len(text.split(" ")) > 1 else ''
        if register_with_referral(bot, from_id, first_name or '', username or '', ref_id_from_text):
            return 'ok'

    # --- referalsiz birinchi tashrif — jim ro'yxatga olish ---
    if chat_type == 'private':
        silent_register_if_new(from_id, first_name or '', username or '')

    # --- inline tugmalar (menyu, captcha, profil, referal, statistika, xaridlar) ---
    if cq is not None and data_val != 'check_obuna':
        handle_callback(bot, cq, connect, send_main_menu, majburiy)
        return 'ok'

    # --- matnli xabarlar va chek rasmlari (xarid oqimlari: Stars/Premium/Gift/TON) ---
    if msg is not None and chat_type == 'private' and not (text or '').startswith('/start'):
        try:
            orders.handle_message(bot, msg, connect, send_main_menu)
        except Exception:
            logger.exception("Xabarni qayta ishlashda xato (user=%s)", from_id)

    return 'ok'


# Server ishga tushganda fon oqimida yengil tashxis (natija logda: [STARTUP] ...)
diagnostics.log_startup(connect)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))