"""
config/channel_pdo.php ning Python porti.

admin_api.py va web_api.py fayllarida haqiqiy PDO o'rniga ishlatiladi.
GROUP BY va LEFT JOIN kabi murakkab so'rovlar uchun maxsus handler bor
(chunki bu loyihada bunday so'rov atigi bir nechta joyda ishlatilgan).
"""
import re

from .channel_db import ChannelStore
from .channel_sql import CDBConnection, CDBResult, cdb_exec_sql


class ChannelPDOStatement:
    def __init__(self, sql: str):
        self.sql = sql
        self.rows: list = []
        self.pos = 0

    def execute(self, params: list = None) -> bool:
        sql = self.sql
        params = params or []
        if params:
            idx = {'i': 0}

            def _sub(m):
                i = idx['i']
                val = params[i] if i < len(params) else None
                idx['i'] += 1
                if val is None:
                    return 'NULL'
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    return str(val)
                return "'" + str(val).replace('\\', '\\\\').replace("'", "\\'") + "'"

            sql = re.sub(r'\?', _sub, sql)

        self.rows = cdb_pdo_run(sql)
        self.pos = 0
        return True

    def fetch(self):
        if self.pos >= len(self.rows):
            return False
        row = self.rows[self.pos]
        self.pos += 1
        return row

    def fetchAll(self) -> list:
        remaining = self.rows[self.pos:]
        self.pos = len(self.rows)
        return remaining

    def fetchColumn(self):
        row = self.fetch()
        if row is False:
            return False
        values = list(row.values())
        return values[0] if values else False

    def rowCount(self) -> int:
        return len(self.rows)


class ChannelPDO:
    last_insert_id = 0

    def __init__(self, *args, **kwargs):
        # dsn/user/pass/options e'tiborsiz qoldiriladi — ChannelStore
        # config.settings orqali allaqachon init qilingan bo'lishi kerak.
        pass

    def setAttribute(self, *args, **kwargs) -> bool:
        return True

    def prepare(self, sql: str) -> ChannelPDOStatement:
        return ChannelPDOStatement(sql)

    def beginTransaction(self) -> bool:
        return True  # yozishlar darhol saqlanadi, alohida tranzaksiya kerak emas

    def commit(self) -> bool:
        return True

    def rollBack(self) -> bool:
        # ESLATMA: ChannelStore yozishlari darhol sodir bo'lgani uchun
        # haqiqiy "rollback" mavjud emas. Agar bu muhim bo'lsa (masalan
        # completeOrder ichida), chaqiruvchi tomonda qo'lda qaytarish kerak.
        return True

    def lastInsertId(self) -> str:
        return str(ChannelPDO.last_insert_id or 0)


def cdb_pdo_run(sql: str) -> list:
    """ChannelPDOStatement.execute() ichidan chaqiriladigan markaziy bajaruvchi."""
    sql = sql.strip()
    upper = sql.upper()

    if upper.startswith('SELECT') and re.search(r'\bJOIN\b', sql, flags=re.IGNORECASE):
        return cdb_pdo_select_join(sql)
    if upper.startswith('SELECT') and re.search(r'\bGROUP\s+BY\b', sql, flags=re.IGNORECASE):
        return cdb_pdo_select_group_by(sql)

    # Oddiy SELECT/INSERT/UPDATE/DELETE — mavjud mysqli-shim dvigatelini qayta ishlatamiz.
    fake_conn = CDBConnection()
    result = cdb_exec_sql(fake_conn, sql)
    ChannelPDO.last_insert_id = fake_conn.insert_id

    if isinstance(result, CDBResult):
        return result.rows
    return []


def cdb_pdo_select_join(sql: str) -> list:
    """faqat "transactions t LEFT JOIN orders o ON t.order_id = o.id" ko'rinishi uchun."""
    transactions = ChannelStore.table('transactions')
    orders = ChannelStore.table('orders')
    orders_by_id = {o.get('id'): o for o in orders}

    joined = []
    for t in transactions:
        o = orders_by_id.get(t.get('order_id'), {})
        joined.append({
            'id': t.get('id'),
            'order_id': o.get('order_id'),
            'user_id': o.get('user_id'),
            'username': o.get('username'),
            'turi': o.get('turi'),
            'amount': o.get('amount'),
            'status': o.get('status'),
            'payme_id': t.get('payme_id'),
            'state': t.get('state'),
            'create_time': t.get('create_time'),
            'perform_time': t.get('perform_time'),
            'transaction_id': t.get('transaction_id'),
            'created_at': o.get('created_at'),
        })

    joined.sort(key=lambda r: str(r.get('created_at') or ''), reverse=True)

    m = re.search(r'LIMIT\s+(\d+)', sql, flags=re.IGNORECASE)
    if m:
        joined = joined[:int(m.group(1))]
    return joined


def cdb_pdo_select_group_by(sql: str) -> list:
    """faqat "orders GROUP BY user_id, username" (getUsers) ko'rinishi uchun."""
    gm = re.search(r'GROUP\s+BY\s+(.*?)(?:\s+ORDER\s+BY|\s+LIMIT|$)', sql, flags=re.IGNORECASE | re.DOTALL)
    if not gm:
        return []
    group_cols = [c.strip(' `') for c in gm.group(1).split(',')]

    rows = ChannelStore.table('orders')
    groups: dict = {}
    for row in rows:
        key = '|'.join(str(row.get(c, '')) for c in group_cols)
        groups.setdefault(key, []).append(row)

    result = []
    for group_rows in groups.values():
        entry = {c: group_rows[0].get(c) for c in group_cols}
        entry['total_orders'] = len(group_rows)
        entry['paid_orders'] = sum(1 for r in group_rows if r.get('status') == 'paid')
        entry['pending_orders'] = sum(1 for r in group_rows if r.get('status') == 'pending')
        entry['total_spent'] = sum(float(r.get('amount') or 0) for r in group_rows if r.get('status') == 'paid')
        result.append(entry)

    result.sort(key=lambda e: e['total_spent'], reverse=True)

    m = re.search(r'LIMIT\s+(\d+)', sql, flags=re.IGNORECASE)
    if m:
        result = result[:int(m.group(1))]
    return result
