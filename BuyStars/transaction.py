"""
BuyStars/transaction.py ning Python porti.
"""
import base64
import re
import logging

from tonutils.client import TonapiClient
from tonutils.wallet import WalletV4R2

from config import settings


def fix_base64_padding(b64_string: str) -> str:
    missing_padding = len(b64_string) % 4
    if missing_padding:
        b64_string += '=' * (4 - missing_padding)
    return b64_string


class TonTransaction:
    async def send_ton_transaction(self, recipient, amount_nano, la, action, amount):
        client = TonapiClient(api_key=settings.API_TON, is_testnet=False)
        wallet, public_key, private_key, mnemonic = WalletV4R2.from_mnemonic(client, settings.MNEMONIC_LIST)
        logging.info("Hamyon muvaffaqiyatli yuklandi.")

        if not recipient:
            logging.error("Xato: qabul qiluvchi ko'rsatilmagan.")
            return
        if amount_nano <= 0:
            logging.error("Xato: summa noto'g'ri (0 dan katta bo'lishi kerak).")
            return

        decoded_bytes = base64.b64decode(fix_base64_padding(la))
        decoded_text = ''.join(chr(b) if 32 <= b < 127 else ' ' for b in decoded_bytes)
        clean_text = re.sub(r'\s+', ' ', decoded_text).strip()

        if action == "stars":
            match = re.search(rf"{amount} Telegram Stars.*", clean_text)
            final_text = match.group(0) if match else clean_text
        else:
            match = re.search(r'(Telegram.*?Ref\s*#\S+)', clean_text)
            final_text = match.group(1).replace('Ref #', 'Ref#') if match else clean_text

        logging.info(f"Tranzaksiya matni: {final_text}")

        tx_hash = await wallet.transfer(
            destination=recipient,
            amount=amount_nano,
            body=final_text,
        )
        logging.info(f"✅ Tranzaksiya yuborildi: {tx_hash}")
        return tx_hash
