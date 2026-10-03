"""
config/channel_db.php ning Python porti.

==========================================================================
 ChannelDB — Telegram kanalga asoslangan ma'lumotlar bazasi
==========================================================================

Ishlash prinsipi:
  - Har bir "jadval" (users, orders, kanal, ...) diskdagi bitta JSON faylda
    saqlanadi (storage/db/<jadval>.json). Bot doim shu fayldan o'qiydi va
    shu faylga yozadi — tez, MySQL kerak emas.
  - Har bir yozish (insert/update/delete) dan so'ng, o'sha jadvalning
    to'liq JSON fayli Telegram kanaliga hujjat (document) sifatida
    yuboriladi/yangilanadi — bu "zaxira nusxa" (backup).
  - Qaysi jadval qaysi kanal xabariga (message_id) tegishli ekanligi
    "_index.json" da saqlanadi.
"""
import json
import os
import logging
import requests

logger = logging.getLogger("channel_db")


class ChannelStore:
    _bot_token: str = ''
    _channel_id: str = ''
    _data_dir: str = ''
    _tables: dict = {}       # jadval_nomi -> qatorlar ro'yxati (xotirada)
    _index: dict = {}        # {'tables': {'users': {'message_id':.., 'file_id':..}, ...}, 'index_message_id': ..}
    _index_loaded: bool = False

    # ---------------------------------------------------------------------
    @classmethod
    def init(cls, bot_token: str, channel_id, data_dir: str) -> None:
        cls._bot_token = bot_token
        cls._channel_id = str(channel_id)
        cls._data_dir = data_dir.rstrip('/')
        cls._tables = {}
        cls._index = {}
        cls._index_loaded = False
        os.makedirs(cls._data_dir, exist_ok=True)

    # ---------------------------------------------------------------------
    # Telegram Bot API bilan past darajadagi aloqa
    # ---------------------------------------------------------------------
    @classmethod
    def _tg_call(cls, method: str, params: dict = None, files: dict = None):
        params = params or {}
        files_ = None
        url = f"https://api.telegram.org/bot{cls._bot_token}/{method}"
        try:
            if files:
                files_ = {field: open(path, 'rb') for field, path in files.items()}
                resp = requests.post(url, data=params, files=files_, timeout=8)
            else:
                resp = requests.post(url, json=params, timeout=8)
        except requests.RequestException as e:
            logger.error("[ChannelStore] tgCall(%s) so'rov xatosi: %s", method, e)
            return None
        finally:
            if files_:
                for f in files_.values():
                    f.close()

        try:
            data = resp.json()
        except ValueError:
            return None

        if not isinstance(data, dict) or not data.get('ok'):
            logger.error("[ChannelStore] tgCall(%s) xato: %s", method, resp.text)
            return None
        return data.get('result')

    @classmethod
    def _download_file(cls, file_path: str, save_to: str) -> bool:
        url = f"https://api.telegram.org/file/bot{cls._bot_token}/{file_path}"
        try:
            resp = requests.get(url, timeout=15)
        except requests.RequestException:
            return False
        if resp.status_code != 200:
            return False
        with open(save_to, 'wb') as f:
            f.write(resp.content)
        return True

    # ---------------------------------------------------------------------
    # Index (jadval -> kanal message_id xaritasi)
    # ---------------------------------------------------------------------
    @classmethod
    def _index_path(cls) -> str:
        return os.path.join(cls._data_dir, '_index.json')

    @classmethod
    def _load_index(cls) -> None:
        if cls._index_loaded:
            return
        cls._index_loaded = True

        path = cls._index_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    decoded = json.load(f)
                cls._index = decoded if isinstance(decoded, dict) else {'tables': {}, 'index_message_id': None}
                return
            except (json.JSONDecodeError, OSError):
                pass

        # Lokal fayl yo'q (masalan disk tozalangan) — kanaldan tiklashga harakat qilamiz.
        cls._index = {'tables': {}, 'index_message_id': None}
        chat = cls._tg_call('getChat', {'chat_id': cls._channel_id})
        pinned = (chat or {}).get('pinned_message')
        if pinned and pinned.get('document', {}).get('file_id'):
            file_ = cls._tg_call('getFile', {'file_id': pinned['document']['file_id']})
            if file_ and cls._download_file(file_['file_path'], path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        decoded = json.load(f)
                    if isinstance(decoded, dict):
                        cls._index = decoded
                        cls._index['index_message_id'] = pinned['message_id']
                except (json.JSONDecodeError, OSError):
                    pass
        cls._save_index_local()

    @classmethod
    def _save_index_local(cls) -> None:
        with open(cls._index_path(), 'w', encoding='utf-8') as f:
            json.dump(cls._index, f, ensure_ascii=False, indent=2)

    @classmethod
    def _sync_index_to_channel(cls) -> None:
        cls._save_index_local()
        path = cls._index_path()
        msg_id = cls._index.get('index_message_id')

        if msg_id:
            result = cls._tg_call('editMessageMedia', {
                'chat_id': cls._channel_id,
                'message_id': msg_id,
                'media': json.dumps({'type': 'document', 'media': 'attach://file', 'caption': '📇 _index.json'}),
            }, {'file': path})
            if result:
                return
            # edit muvaffaqiyatsiz bo'lsa (masalan xabar juda eski) — yangi xabar yuboramiz

        sent = cls._tg_call('sendDocument', {'chat_id': cls._channel_id, 'caption': '📇 _index.json'}, {'document': path})
        if sent:
            cls._index['index_message_id'] = sent['message_id']
            cls._save_index_local()
            cls._tg_call('pinChatMessage', {
                'chat_id': cls._channel_id, 'message_id': sent['message_id'], 'disable_notification': True,
            })

    # ---------------------------------------------------------------------
    # Jadval yuklash / saqlash
    # ---------------------------------------------------------------------
    @classmethod
    def _table_path(cls, name: str) -> str:
        return os.path.join(cls._data_dir, f"{name}.json")

    @classmethod
    def table(cls, name: str) -> list:
        """PHP'dagi `&table()` ga mos — qaytgan list obyektini o'zgartirish
        xotiradagi jadvalni ham o'zgartiradi (Python list'lar reference bo'ladi)."""
        if name not in cls._tables:
            cls._tables[name] = cls._load_table(name)
        return cls._tables[name]

    @classmethod
    def _load_table(cls, name: str) -> list:
        path = cls._table_path(name)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    decoded = json.load(f)
                return decoded if isinstance(decoded, list) else []
            except (json.JSONDecodeError, OSError):
                return []

        # Lokal fayl yo'q — kanaldan tiklashga harakat qilamiz.
        cls._load_index()
        meta = cls._index.get('tables', {}).get(name)
        if meta and meta.get('file_id'):
            file_ = cls._tg_call('getFile', {'file_id': meta['file_id']})
            if file_ and cls._download_file(file_['file_path'], path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        decoded = json.load(f)
                    return decoded if isinstance(decoded, list) else []
                except (json.JSONDecodeError, OSError):
                    return []
        return []

    @classmethod
    def persist(cls, name: str) -> None:
        """Jadval xotiradagi massivi o'zgargandan so'ng chaqiriladi: diskka yozadi + kanalga sinxronlaydi."""
        rows = cls._tables.get(name, [])
        path = cls._table_path(name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)

        cls._load_index()
        meta = cls._index.get('tables', {}).get(name)

        caption = f"🗂 {name}.json ({len(rows)} ta yozuv)"
        if meta and meta.get('message_id'):
            result = cls._tg_call('editMessageMedia', {
                'chat_id': cls._channel_id,
                'message_id': meta['message_id'],
                'media': json.dumps({'type': 'document', 'media': 'attach://file', 'caption': caption}),
            }, {'file': path})
            if result and result.get('document', {}).get('file_id'):
                cls._index.setdefault('tables', {}).setdefault(name, {})['file_id'] = result['document']['file_id']
                cls._sync_index_to_channel()
                return

        sent = cls._tg_call('sendDocument', {'chat_id': cls._channel_id, 'caption': caption}, {'document': path})
        if sent:
            cls._index.setdefault('tables', {})[name] = {
                'message_id': sent['message_id'],
                'file_id': sent.get('document', {}).get('file_id'),
            }
            cls._sync_index_to_channel()

    @classmethod
    def next_id(cls, name: str) -> int:
        rows = cls.table(name)
        max_id = 0
        for row in rows:
            rid = row.get('id', 0) or 0
            if rid > max_id:
                max_id = rid
        return max_id + 1
