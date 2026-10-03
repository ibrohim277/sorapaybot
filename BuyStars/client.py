"""
BuyStars/client.py ning Python porti — Fragment.com orqali Stars/Premium
sotib olish uchun so'rov zanjiri (recipient qidirish -> req_id olish ->
to'lov havolasini olish).
"""
import logging
import httpx

from config import settings


def get_cookies() -> dict:
    return dict(settings.FRAGMENT_COOKIES)


class FragmentClient:
    URL = f"https://fragment.com/api?hash={settings.FRAGMENT_HASH}"

    async def fetch_recipient(self, query: str, amount, action: str):
        if action == "stars":
            data = {"query": query, "method": "searchStarsRecipient"}
        else:
            data = {"query": query, "months": amount, "method": "searchPremiumGiftRecipient"}

        async with httpx.AsyncClient() as client:
            response = await client.post(self.URL, cookies=get_cookies(), data=data)
            logging.info(response.json())
            return response.json().get("found", {}).get("recipient")

    async def fetch_req_id(self, recipient: str, amount, action: str):
        if action == "stars":
            data = {"recipient": recipient, "quantity": amount, "method": "initBuyStarsRequest"}
        else:
            data = {"recipient": recipient, "months": amount, "method": "initGiftPremiumRequest"}

        async with httpx.AsyncClient() as client:
            response = await client.post(self.URL, cookies=get_cookies(), data=data)
            logging.info(response.json())
            return response.json().get("req_id")

    async def fetch_buy_link(self, recipient: str, req_id, amount, action: str):
        if action == "stars":
            method = "getBuyStarsLink"
            referer = f"https://fragment.com/stars/buy?recipient={recipient}&quantity={amount}"
        else:
            method = "getGiftPremiumLink"
            referer = f"https://fragment.com/premium/gift?recipient={recipient}&months={amount}"

        data = {
            "address": settings.FRAGMENT_ADDRES,
            "chain": "-239",
            "walletStateInit": settings.FRAGMENT_WALLETS,
            "publicKey": settings.FRAGMENT_PUBLICKEY,
            "features": ["SendTransaction", {"name": "SendTransaction", "maxMessages": 255}],
            "maxProtocolVersion": 2,
            "platform": "iphone",
            "appName": "Tonkeeper",
            "appVersion": "5.0.14",
            "transaction": "1",
            "id": req_id,
            "show_sender": "0",
            "method": method,
        }
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": "https://fragment.com",
            "referer": referer,
            "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            "x-requested-with": "XMLHttpRequest",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(self.URL, headers=headers, cookies=get_cookies(), data=data)
            json_data = response.json()
            logging.info(json_data)
            if json_data.get("ok") and "transaction" in json_data:
                transaction = json_data["transaction"]
                return (
                    transaction["messages"][0]["address"],
                    transaction["messages"][0]["amount"],
                    transaction["messages"][0]["payload"],
                )
        return None, None, None
