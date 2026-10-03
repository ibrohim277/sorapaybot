"""
config/config.php ning Python porti.
Barcha sozlamalar shu yerda hardcoded (repo private bo'lgani uchun).

BOT_TOKEN va MNEMONIC asl kodda ham bo'sh edi — bular hech qayerda
berilmagan, shu yerga o'zingiz to'ldirishingiz kerak.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BOT_TOKEN = ''   # <-- BotFather'dan olingan tokenni shu yerga yozing
API_URL = f'https://api.telegram.org/bot{BOT_TOKEN}/'

# --- ChannelDB sozlamalari (MySQL o'rniga) ---
DB_CHANNEL_ID = -1004403059476
DB_DATA_DIR = os.path.join(BASE_DIR, 'storage', 'db')

ADMIN_ID = 2142292702
LOG_CHANNEL_ID = -1003991077401
TONAPI_KEY = ''   # tonapi.io kalitingiz (hali kodda ishlatilmayapti)
BASE_URL = 'https://sorapay.onrender.com'   # Render servis nomi "sorapay" bo'lgani uchun odatda shu manzil bo'ladi.
                                             # Agar Render boshqa manzil bersa (masalan "sorapay" band bo'lib chiqsa),
                                             # shu yerni Render haqiqiy bergan URL bilan almashtirib qayta push qiling.

DEBUG = True

STEP_DIR = os.path.join(BASE_DIR, 'step')
os.makedirs(STEP_DIR, exist_ok=True)
os.makedirs(DB_DATA_DIR, exist_ok=True)

# --- TON yuborish (BuyTon/, BuyStars/) va Fragment.com integratsiyasi ---
API_TON = "AH6VGUQHYLVXFGQAAAAE6E5OK5T4H7TF3DSHJCHSJ4XNUTEIXPXQAYSSPI4ZLUERNDXWDVI"
MNEMONIC = ''   # <-- hamyon 24 so'zlik maxfiy iborasi, probel bilan ajratib yozing (asl kodda ham bo'sh edi)
MNEMONIC_LIST = MNEMONIC.split() if MNEMONIC else []

FRAGMENT_HASH = '03290a4624161419'
FRAGMENT_PUBLICKEY = 'bd9767479817f5587029a3c131fadedfd4bcad456ec66729a9bd078034fb234d'
FRAGMENT_WALLETS = 'te6cckECFgEAAwQAAgE0ARUBFP8A9KQT9LzyyAsCAgEgAxACAUgEBwLm0AHQ0wMdIz0M='
FRAGMENT_ADDRES = '0:c16230bea882a7dfc38c25734de1965d4651198718c130e32dabe0011352c'

STEL_SSID = '547c9d2018b8804a79_422117814560415'
STEL_DT = '-300'
STEL_TON_TOKEN = '_gKZvwRyzR9bgBSETHYXG4qyooQQNnpj3S3CJSnsjdKKMK6CaM5wdeSRKbrIJPH7Fe5Laka3mMuNvWza6KCKCnBimcYvHRn-rAljca-XJkc5iyCj1edZISZ4Vx3Tk1vD9o_7hzipq8bQLrYhHPnWxsuS0W2VLt7E-0sSeYbJn-dz'
STEL_TOKEN = 'ab85018e4ebeb5c9c24f50aac392dc25ab8561464ab850c59b5cd294560a40dd5b7724a'

FRAGMENT_COOKIES = {
    'stel_ssid': STEL_SSID,
    'stel_dt': STEL_DT,
    'stel_ton_token': STEL_TON_TOKEN,
    'stel_token': STEL_TOKEN,
}
