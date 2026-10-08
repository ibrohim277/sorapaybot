"""
Bot sog'lig'ini tekshirish: `/diag` (admin) buyrug'i va server ishga tushganda logga yozish.

Maqsad — "nima uchun ishlamayapti?" savoliga log qidirmasdan, bitta xabarda javob berish.
Hech qachon maxfiy qiymatlarni (token, mnemonic, cookie) chiqarmaydi — faqat "bor/yo'q".
"""
import logging
import threading

from config import settings
from config import pricing as P
from telegram_bot import Begzod

logger = logging.getLogger("sorapay.diag")


def _h(s) -> str:
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _desc(res) -> str:
    return str(getattr(res, 'description', None) or 'javob kelmadi (tarmoq?)')


def _run_checks(bot: Begzod, connect=None, full: bool = True):
    """[(ok: bool, matn)] ro'yxatini qaytaradi. full=False — faqat yengil (tezkor) tekshiruvlar."""
    out = []

    def add(ok, text):
        out.append((bool(ok), text))

    # --- 1. Token ---
    me = bot.getMe()
    bot_id = None
    if getattr(me, 'ok', False):
        bot_id = getattr(me.result, 'id', None)
        add(True, f"Token to'g'ri: @{getattr(me.result, 'username', '?')}")
    else:
        add(False, f"BOT_TOKEN ishlamayapti: {_desc(me)}")

    # --- 2. Webhook ---
    wh = bot.getWebhookInfo()
    expected = settings.BASE_URL.rstrip('/') + '/index.php'
    if getattr(wh, 'ok', False):
        wr = getattr(wh, 'result', None)
        url = getattr(wr, 'url', '') or ''
        last_err = getattr(wr, 'last_error_message', None)
        pending = getattr(wr, 'pending_update_count', 0)
        if url != expected:
            add(False, f"Webhook manzili mos emas: Telegram'da «{_h(url or 'yo`q')}», kodda BASE_URL bo'yicha «{_h(expected)}». "
                       "settings.BASE_URL ni Render bergan haqiqiy manzilga almashtiring!")
        else:
            add(True, f"Webhook to'g'ri ({pending} ta kutilayotgan update)")
        if last_err:
            add(False, f"Telegram oxirgi webhook xatosi: {_h(last_err)}")

    # --- 3. DB kanal va log kanal ---
    for label, cid in (("DB kanal", settings.DB_CHANNEL_ID), ("Log kanal", settings.LOG_CHANNEL_ID)):
        chat = bot.getChat({'chat_id': cid})
        if not getattr(chat, 'ok', False):
            add(False, f"{label} ({cid}) topilmadi: {_h(_desc(chat))}. Botni shu kanalga ADMIN qilib qo'shing "
                       "yoki ID ni to'g'rilang." + (" Aks holda ma'lumotlar server qayta ishga tushganda YO'QOLADI!" if label == "DB kanal" else ""))
            continue
        status = None
        if bot_id:
            m = bot.getChatMember({'chat_id': cid, 'user_id': bot_id})
            status = getattr(getattr(m, 'result', None), 'status', None)
        if status in ('administrator', 'creator'):
            add(True, f"{label} ulangan: «{_h(getattr(getattr(chat, 'result', None), 'title', cid))}» (bot admin)")
        else:
            add(False, f"{label} topildi, lekin bot admin emas (holat: {status}). Botni ADMIN qiling.")

    # --- 4. Sozlamalar ---
    words = len(settings.MNEMONIC_LIST)
    add(words in (12, 24), "MNEMONIC kiritilgan" + (f" ({words} so'z)" if words else "")
        if words in (12, 24) else "MNEMONIC bo'sh yoki noto'g'ri — Stars/Premium/TON bajarib bo'lmaydi (config/settings.py)")
    add(bool(settings.API_TON), "API_TON bor" if settings.API_TON else "API_TON bo'sh")
    if connect is not None:
        try:
            from orders import _card
            card, owner = _card(connect)
            add(bool(card), f"To'lov kartasi: {_h(card)}" if card else "To'lov kartasi kiritilmagan — mijozlar to'lay olmaydi. Botda: /karta 8600123412341234 Ism Familiya")
        except Exception as e:
            add(False, f"Karta tekshirilmadi: {_h(e)}")

    if not full:
        return out

    # --- 5. Narx kursi ---
    try:
        rate = P.get_ton_uzs(None)
        live = P._CACHE['v'] is not None
        add(live, f"TON kursi: {P.fmt(rate)} so'm" if live else
            f"TON kursi avtomatik olinmadi — minimal narx ishlatilmoqda ({P.fmt(rate)}). Tavsiya: /kurs 31500")
    except Exception as e:
        add(False, f"Kurs xatosi: {_h(e)}")

    # --- 6. Hamyon ---
    if words in (12, 24):
        try:
            from orders import _wallet_balance_ton
            bal = _wallet_balance_ton()
            add(bal >= 1, f"Hamyon balansi: {bal:.2f} TON" + ("" if bal >= 1 else " — juda kam, to'ldiring"))
        except Exception as e:
            add(False, f"Hamyonga ulanib bo'lmadi: {_h(type(e).__name__)}: {_h(e)}")

    # --- 7. Fragment (Stars/Premium uchun) ---
    try:
        from config.username_info import chekusername
        r = chekusername('durov')
        if r.get('exists'):
            add(True, "Fragment ishlayapti (cookie/hash yaroqli)")
        else:
            add(False, f"Fragment javobi noto'g'ri: {_h(r.get('error') or r.get('message'))}. "
                       "FRAGMENT_HASH va STEL_* cookie'lari eskirgan bo'lishi mumkin — Stars/Premium shu sababli ishlamaydi.")
    except Exception as e:
        add(False, f"Fragment tekshirilmadi: {_h(e)}")

    # --- 8. Gift (botning Stars balansi) ---
    g = bot.getAvailableGifts()
    if getattr(g, 'ok', False):
        n = len(getattr(getattr(g, 'result', None), 'gifts', []) or [])
        sb = bot.getMyStarBalance()
        amount = getattr(getattr(sb, 'result', None), 'amount', None)
        add(bool(amount), f"Gift: {n} ta sovg'a mavjud, botning Stars balansi: {amount if amount is not None else '?'}"
            + ("" if amount else " — Gift sotish uchun Stars balansini to'ldiring"))
    else:
        add(False, f"Gift ro'yxatini olib bo'lmadi: {_h(_desc(g))}")

    return out


def run_checks(bot: Begzod, connect=None, full: bool = True):
    """_run_checks ning xavfsiz o'rami: kutilmagan xato bo'lsa ham hisobot qaytaradi."""
    try:
        return _run_checks(bot, connect, full)
    except Exception as e:
        logger.exception("Tashxis vositasida xato")
        return [(False, f"Tashxis vositasi yiqildi: {_h(type(e).__name__)}: {_h(e)}")]


def format_report(checks) -> str:
    bad = sum(1 for ok, _ in checks if not ok)
    head = "🩺 <b>Tashxis natijasi</b> — " + ("hammasi joyida ✅" if not bad else f"{bad} ta muammo ❌")
    return head + "\n\n" + "\n".join(("✅ " if ok else "❌ ") + t for ok, t in checks)


def log_startup(connect) -> None:
    """Server ishga tushganda fon oqimida yengil tekshiruv o'tkazib, natijani logga yozadi."""
    def _run():
        try:
            for ok, text in run_checks(Begzod(), connect, full=False):
                (logger.info if ok else logger.error)("[STARTUP] %s %s", "OK " if ok else "XATO", text)
        except Exception:
            logger.exception("[STARTUP] tashxis bajarilmadi")
    threading.Thread(target=_run, name="startup-diag", daemon=True).start()
