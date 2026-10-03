"""
BuyStars/main.py ning Python porti.

CLI: python -m BuyStars.main stars @username 50
     python -m BuyStars.main premium @username 3

Dasturiy (Flask handler ichidan):
    from BuyStars.main import buy
    ok = await buy("stars", "@username", 50)
"""
import asyncio
import sys
import logging

from BuyStars.client import FragmentClient
from BuyStars.transaction import TonTransaction

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def buy(action: str, query: str, amount) -> bool:
    client = FragmentClient()

    recipient = await client.fetch_recipient(query, amount, action)
    if not recipient:
        logging.error("Xato: qabul qiluvchi topilmadi.")
        return False

    req_id = await client.fetch_req_id(recipient, amount, action)
    if not req_id:
        logging.error("Xato: req_id olinmadi.")
        return False

    recipient, amount_nano, la = await client.fetch_buy_link(recipient, req_id, amount, action)
    if not (recipient and amount_nano and la):
        logging.error("Xato: to'lov havolasini olib bo'lmadi.")
        return False

    amount_decimal = float(amount_nano) / 1_000_000_000
    logging.info(f"Yuborish uchun summa: {amount_decimal:.4f} TON")

    transaction = TonTransaction()
    tx_hash = await transaction.send_ton_transaction(recipient, amount_decimal, la, action, amount)
    return bool(tx_hash)


async def _cli_main(action, query, amount):
    ok = await buy(action, query, amount)
    print("STATUS: SUCCESS" if ok else "STATUS: FAILED")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Xato: parametrlarni to'g'ri kiriting!")
        print("Misol (stars):   python -m BuyStars.main stars @username 50")
        print("Misol (premium): python -m BuyStars.main premium @username 3")
        sys.exit(1)

    _action = sys.argv[1]
    _query = sys.argv[2]
    _amount = int(sys.argv[3])

    if _action not in ("stars", "premium"):
        print("Xato: action faqat 'stars' yoki 'premium' bo'lishi mumkin!")
        sys.exit(1)

    asyncio.run(_cli_main(_action, _query, _amount))
