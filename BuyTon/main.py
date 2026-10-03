"""
BuyTon/main.py ning Python porti (asl kod ham Python edi — faqat
API_TON/MNEMONIC endi config/settings.py orqali environment variable'dan
olinadi, config.py ichida hardcode qilinmaydi).

CLI sifatida ishlatish:
    python -m BuyTon.main <recipient> <amount_ton>

Dasturiy jihatdan (Flask handler ichidan) ishlatish:
    from BuyTon.main import TonSender
    await TonSender().send(recipient, amount_ton)
"""
import asyncio
import sys
import logging

from tonutils.client import TonapiClient
from tonutils.wallet import WalletV4R2

from config import settings

logging.basicConfig(level=logging.INFO, format='%(message)s')


class TonSender:
    def __init__(self):
        self.client = TonapiClient(api_key=settings.API_TON, is_testnet=False)

    async def send(self, recipient: str, amount_ton: float) -> bool:
        if not recipient:
            print("❌ Xato: recipient parametri berilmagan")
            return False

        if amount_ton <= 0:
            print("❌ Xato: amount 0 dan katta bo'lishi kerak")
            return False

        try:
            wallet, _, _, _ = WalletV4R2.from_mnemonic(self.client, settings.MNEMONIC_LIST)
            print(f"✅ Hamyon yuklandi | Sender: {wallet.address.to_str(is_bounceable=False)}")

            address_str = wallet.address.to_str(is_bounceable=False)
            balance_nano = await self.client.get_account_balance(address_str)
            balance_ton = balance_nano / 1_000_000_000

            print(f"💰 Balans: {balance_ton:.6f} TON")
            print(f"📤 Yuborilayotgan miqdor: {amount_ton:.6f} TON → {recipient}")

            if balance_ton < amount_ton + 0.05:
                print(f"❌ Yetarli mablag' yo'q! Kerak: {amount_ton + 0.05:.4f} TON")
                return False

            print("🚀 Tranzaksiya yuborilmoqda...")
            tx_hash = await wallet.transfer(
                destination=recipient,
                amount=amount_ton,
                body="@SoraPayBot bilan xaridingiz barakali bo'lsin",
            )

            print(f"✅ Tranzaksiya yuborildi: {tx_hash}")
            print(f"🔗 https://tonviewer.com/transaction/{tx_hash}")

            await asyncio.sleep(3)
            new_balance = await self.client.get_account_balance(address_str) / 1_000_000_000
            print(f"💰 Yangi balans: {new_balance:.6f} TON")

            return True

        except Exception as e:
            print(f"❌ Xato: {str(e)}")
            return False


async def _cli_main():
    if len(sys.argv) < 3:
        print("❌ Xato: recipient va amount parametrlarini berish kerak")
        print("Foydalanish: python -m BuyTon.main <recipient> <amount>")
        sys.exit(1)

    recipient = sys.argv[1].strip()
    try:
        amount = float(sys.argv[2].strip())
    except ValueError:
        print("❌ Xato: amount to'g'ri son bo'lishi kerak (masalan: 0.20)")
        sys.exit(1)

    success = await TonSender().send(recipient, amount)
    print("STATUS: SUCCESS" if success else "STATUS: FAILED")


if __name__ == "__main__":
    asyncio.run(_cli_main())
