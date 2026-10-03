"""
config/channel_sql.php ning Python porti (barcha topilgan bug-fixlar bilan).

ChannelDB uchun mysqli-ga o'xshash funksiyalar to'plami.

DIQQAT: bu haqiqiy SQL dvigateli EMAS — faqat shu loyihada ishlatilgan
so'rov shakllarini tushunadigan mini-parser (oddiy WHERE col='val' [AND ...],
ORDER BY, LIMIT, INSERT/UPDATE/DELETE, ON DUPLICATE KEY UPDATE, bir nechta
COUNT/SUM/CASE-WHEN agregatlari).
"""
import re
import logging
from datetime import datetime
from functools import cmp_to_key

from .channel_db import ChannelStore

logger = logging.getLogger("channel_sql")

# Insert paytida "ON DUPLICATE KEY UPDATE" uchun jadvalning noyob (unique) ustunlari.
CDB_UNIQUE_KEYS = {
    'joinRequest': ['user_id', 'chat_id'],
}


class CDBConnection:
    def __init__(self):
        self.insert_id = 0
        self.affected_rows = 0
        self.error = ''


class CDBResult:
    def __init__(self, rows: list):
        self.rows = list(rows)
        self.pos = 0


class CDBStatement:
    def __init__(self, connect: CDBConnection, sql: str):
        self.connect = connect
        self.sql = sql
        self.bound_refs = []
        self.types = ''
        self.result: 'CDBResult | None' = None


# --------------------------------------------------------------------------
# Ulanish / natija bilan ishlash funksiyalari (mysqli_* bilan bir xil imzoda)
# --------------------------------------------------------------------------

def cdb_connect(bot_token: str, channel_id, data_dir: str) -> CDBConnection:
    ChannelStore.init(bot_token, channel_id, data_dir)
    return CDBConnection()


def cdb_fetch_assoc(result):
    if not isinstance(result, CDBResult):
        return None
    if result.pos >= len(result.rows):
        return None
    row = result.rows[result.pos]
    result.pos += 1
    return row


def cdb_fetch_all(result, mode=None) -> list:
    return result.rows if isinstance(result, CDBResult) else []


def cdb_num_rows(result) -> int:
    return len(result.rows) if isinstance(result, CDBResult) else 0


def cdb_affected_rows(connect: CDBConnection) -> int:
    return connect.affected_rows


def cdb_insert_id(connect: CDBConnection) -> int:
    return connect.insert_id


def cdb_real_escape_string(connect: CDBConnection, s: str) -> str:
    # Haqiqiy SQL qurilmayapti, lekin literal ichidagi ' belgisi bizning
    # parserni chalg'itmasligi uchun ekranlanadi (keyin avtomatik ochiladi).
    return s.replace('\\', '\\\\').replace("'", "\\'")


def cdb_query(connect: CDBConnection, sql: str):
    return cdb_exec_sql(connect, sql)


def cdb_prepare(connect: CDBConnection, sql: str) -> CDBStatement:
    return CDBStatement(connect, sql)


def cdb_stmt_bind_param(stmt: CDBStatement, types: str, *values):
    stmt.types = types
    stmt.bound_refs = list(values[:len(types)])


def cdb_stmt_execute(stmt: CDBStatement) -> bool:
    sql = stmt.sql
    types = stmt.types

    if types:
        idx = {'i': 0}

        def _sub(m):
            i = idx['i']
            t = types[i] if i < len(types) else 's'
            val = stmt.bound_refs[i] if i < len(stmt.bound_refs) else None
            idx['i'] += 1
            if val is None:
                return 'NULL'
            if t in ('i', 'd'):
                return str(val)
            return "'" + str(val).replace('\\', '\\\\').replace("'", "\\'") + "'"

        sql = re.sub(r'\?', _sub, sql)

    result = cdb_exec_sql(stmt.connect, sql)
    stmt.result = result if isinstance(result, CDBResult) else None
    return True


def cdb_stmt_get_result(stmt: CDBStatement):
    return stmt.result


def cdb_stmt_close(stmt: CDBStatement) -> None:
    pass  # xotirada saqlanadigan hech narsa yo'q — bo'sh.


# --------------------------------------------------------------------------
# Mini SQL-ga o'xshash parser
# --------------------------------------------------------------------------

def cdb_exec_sql(connect: CDBConnection, sql: str):
    sql = sql.strip()
    upper = sql.upper()

    if upper.startswith('SELECT'):
        return cdb_do_select(connect, sql)
    if upper.startswith('INSERT'):
        return cdb_do_insert(connect, sql)
    if upper.startswith('UPDATE'):
        return cdb_do_update(connect, sql)
    if upper.startswith('DELETE'):
        return cdb_do_delete(connect, sql)

    logger.error("[ChannelDB] Noma'lum so'rov turi: %s", sql)
    return False


def _php_numeric_value(raw: str):
    """PHP'dagi `$raw + 0` (sonli satrni int/float'ga aylantirish) mos keladi."""
    try:
        if re.search(r'[.eE]', raw):
            return float(raw)
        return int(raw)
    except ValueError:
        return float(raw)


def cdb_parse_literal(raw: str):
    """'val' yoki oddiy sonni asl Python qiymatiga aylantiradi."""
    raw = raw.strip()
    if raw == '':
        return ''
    if raw[0] == "'" and raw[-1] == "'":
        inner = raw[1:-1]
        return inner.replace("\\'", "'").replace('\\\\', '\\')
    if re.fullmatch(r'-?\d+(\.\d+)?', raw):
        return _php_numeric_value(raw)
    if raw.upper() == 'NOW()':
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if raw.upper() == 'NULL':
        return None
    return raw.strip('`')


def cdb_build_where_filter(where_str):
    """
    "col = 'val' AND col2 = 5 [AND DATE(col3) = 'YYYY-MM-DD']" -> filter funksiyasi.
    "col = ? OR col2 = ?" ko'rinishidagi eng tashqi OR ham qo'llab-quvvatlanadi
    (AND dan past ustuvorlikda) — bu loyihada faqat "id = ? OR order_id = ?"
    shaklida ishlatiladi.
    """
    if where_str is None or where_str.strip() == '':
        return lambda row: True

    where_str = where_str.strip()
    or_parts = re.split(r'\s+OR\s+', where_str, flags=re.IGNORECASE)
    if len(or_parts) > 1:
        sub_filters = [cdb_build_where_filter(p) for p in or_parts]

        def _or_filter(row):
            return any(f(row) for f in sub_filters)
        return _or_filter

    conditions = re.split(r'\s+AND\s+', where_str, flags=re.IGNORECASE)
    parsed = []
    for cond in conditions:
        cond = cond.strip()
        # "1=1" kabi ikkala tomoni ham son bo'lgan literal taqqoslash (ustun nomi emas) —
        # dinamik so'rov qurishda ("WHERE 1=1 AND ...") ishlatiladi, doim rost/yolg'on deb baholanadi.
        m = re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*=\s*(-?\d+(?:\.\d+)?)', cond)
        if m:
            parsed.append({'type': 'literal', 'val': float(m.group(1)) == float(m.group(2))})
            continue

        m = re.fullmatch(r"DATE\(\s*`?(\w+)`?\s*\)\s*=\s*'(.*)'", cond, flags=re.IGNORECASE | re.DOTALL)
        if m:
            parsed.append({'type': 'date_eq', 'col': m.group(1), 'val': m.group(2)})
            continue

        m = re.fullmatch(r"`?(\w+)`?\s*=\s*'((?:[^'\\]|\\.)*)'", cond, flags=re.DOTALL)
        if m:
            val = m.group(2).replace("\\'", "'").replace('\\\\', '\\')
            parsed.append({'type': 'eq', 'col': m.group(1), 'val': val})
            continue

        m = re.fullmatch(r'`?(\w+)`?\s*=\s*(-?\d+(?:\.\d+)?)', cond)
        if m:
            parsed.append({'type': 'eq', 'col': m.group(1), 'val': _php_numeric_value(m.group(2))})
            continue

        # Tushunarsiz shart bo'lsa, xavfsizlik uchun hech narsaga mos kelmaydigan filtr qaytaramiz.
        logger.error("[ChannelDB] WHERE shartini tushunolmadim: %s", cond)
        return lambda row: False

    def _filter(row):
        for p in parsed:
            if p['type'] == 'literal':
                if not p['val']:
                    return False
            elif p['type'] == 'date_eq':
                row_val = row.get(p['col'], '')
                if str(row_val)[:10] != p['val']:
                    return False
            else:
                if p['col'] not in row or str(row[p['col']]) != str(p['val']):
                    return False
        return True

    return _filter


def cdb_extract_clause(sql: str, after_keyword: str, stop_keywords: list):
    m = re.search(r'\b' + after_keyword + r'\b(.*)$', sql, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    rest = m.group(1)
    if stop_keywords:
        stop_pattern = r'\b(' + '|'.join(stop_keywords) + r')\b'
        sm = re.search(stop_pattern, rest, flags=re.IGNORECASE)
        if sm:
            rest = rest[:sm.start()]
    return rest.strip()


def cdb_do_select(connect: CDBConnection, sql: str):
    m = re.search(r'FROM\s+`?(\w+)`?', sql, flags=re.IGNORECASE)
    if not m:
        logger.error("[ChannelDB] SELECT: jadval nomi topilmadi: %s", sql)
        return CDBResult([])
    table = m.group(1)

    select_clause = re.sub(r'^SELECT\s+', '', sql[:m.start()], flags=re.IGNORECASE).strip()
    where_str = cdb_extract_clause(sql, 'WHERE', ['ORDER BY', 'LIMIT', 'GROUP BY'])
    order_str = cdb_extract_clause(sql, 'ORDER BY', ['LIMIT'])
    limit_str = cdb_extract_clause(sql, 'LIMIT', [])

    rows = ChannelStore.table(table)
    filter_fn = cdb_build_where_filter(where_str)
    filtered = [r for r in rows if filter_fn(r)]

    # --- Agregat SELECT (COUNT/SUM/COALESCE) ---
    if re.search(r'\b(COUNT|SUM)\s*\(', select_clause, flags=re.IGNORECASE):
        result = cdb_compute_aggregates(select_clause, filtered)
        return CDBResult([result])

    # --- Oddiy SELECT ---
    if order_str:
        om = re.search(r'`?(\w+)`?\s*(ASC|DESC)?', order_str, flags=re.IGNORECASE)
        if om:
            col = om.group(1)
            desc = bool(om.group(2)) and om.group(2).upper() == 'DESC'

            def _cmp(a, b):
                av, bv = a.get(col), b.get(col)
                if av is None and bv is None:
                    return 0
                if av is None:
                    return -1
                if bv is None:
                    return 1
                if av < bv:
                    return -1
                if av > bv:
                    return 1
                return 0

            filtered.sort(key=cmp_to_key(_cmp), reverse=desc)

    if limit_str:
        lm = re.search(r'(\d+)\s*,\s*(\d+)', limit_str)
        if lm:
            offset, count = int(lm.group(1)), int(lm.group(2))
            filtered = filtered[offset:offset + count]
        else:
            lm = re.search(r'(\d+)', limit_str)
            if lm:
                filtered = filtered[:int(lm.group(1))]

    if select_clause.strip() != '*':
        cols = [c.strip().strip('`') for c in select_clause.split(',')]

        def _project(row):
            projected = {}
            for c in cols:
                alias = c
                am = re.search(r'\bAS\s+(\w+)$', c, flags=re.IGNORECASE)
                if am:
                    alias = am.group(1)
                    c_name = c[:am.start()].strip()
                else:
                    c_name = c
                projected[alias] = row.get(c_name.strip('`'))
            return projected

        filtered = [_project(r) for r in filtered]

    return CDBResult(filtered)


def cdb_compute_aggregates(select_clause: str, rows: list) -> dict:
    """SELECT ichidagi COUNT(*)/SUM(col)/COUNT(CASE WHEN...)/COALESCE(...) ifodalarini hisoblaydi."""
    exprs = cdb_split_top_level_commas(select_clause)
    result = {}

    for expr in exprs:
        expr = expr.strip()
        alias = None
        am = re.search(r'\bAS\s+(\w+)$', expr, flags=re.IGNORECASE)
        if am:
            alias = am.group(1)
            expr = expr[:am.start()].strip()

        m = re.search(r'COALESCE\s*\(\s*SUM\(\s*`?(\w+)`?\s*\)\s*,\s*0\s*\)', expr, flags=re.IGNORECASE)
        if m:
            s = sum(float(r.get(m.group(1)) or 0) for r in rows)
            result[alias or expr] = s
            continue
        m = re.fullmatch(r'SUM\(\s*`?(\w+)`?\s*\)', expr, flags=re.IGNORECASE)
        if m:
            s = sum(float(r.get(m.group(1)) or 0) for r in rows)
            result[alias or expr] = s
            continue
        if re.fullmatch(r'COUNT\(\s*\*\s*\)', expr, flags=re.IGNORECASE):
            result[alias or 'COUNT(*)'] = len(rows)
            continue
        # COUNT(CASE WHEN col = val THEN 1 END)
        m = re.search(r"COUNT\(\s*CASE\s+WHEN\s+`?(\w+)`?\s*=\s*('?[\w.\-]*'?)\s+THEN\s+1\s+END\s*\)", expr, flags=re.IGNORECASE)
        if m:
            col = m.group(1)
            val = cdb_parse_literal(m.group(2))
            count = sum(1 for r in rows if str(r.get(col)) == str(val))
            result[alias or expr] = count
            continue

        logger.error("[ChannelDB] Agregat ifodani tushunolmadim: %s", expr)
        result[alias or expr] = None

    return result


def cdb_split_top_level_commas(s: str) -> list:
    parts = []
    depth = 0
    current = ''
    for ch in s:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(current)
            current = ''
        else:
            current += ch
    if current.strip() != '':
        parts.append(current)
    return parts


def cdb_do_insert(connect: CDBConnection, sql: str) -> bool:
    on_dup_update = None
    row = None
    table = None

    # Shakl 1: INSERT INTO t (col1, col2) VALUES ('v1', 'v2') [ON DUPLICATE KEY UPDATE ...]
    m = re.search(
        r'INSERT\s+INTO\s+`?(\w+)`?\s*\(([^)]*)\)\s*VALUES\s*\(([^;]*)\)(?:\s*ON\s+DUPLICATE\s+KEY\s+UPDATE\s+(.*))?$',
        sql, flags=re.IGNORECASE | re.DOTALL)
    if m:
        table = m.group(1)
        cols = [c.strip(' `') for c in m.group(2).split(',')]
        raw_values = cdb_split_top_level_commas(m.group(3))
        values = [cdb_parse_literal(v) for v in raw_values]
        on_dup_update = m.group(4)
        row = dict(zip(cols, values))
    else:
        # Shakl 2: INSERT INTO t SET col1 = 'v1', col2 = 'v2' [ON DUPLICATE KEY UPDATE ...]
        m = re.search(
            r'INSERT\s+INTO\s+`?(\w+)`?\s+SET\s+(.*?)(?:\s*ON\s+DUPLICATE\s+KEY\s+UPDATE\s+(.*))?$',
            sql, flags=re.IGNORECASE | re.DOTALL)
        if m:
            table = m.group(1)
            on_dup_update = m.group(3)
            row = {}
            for assign in cdb_split_top_level_commas(m.group(2)):
                am = re.match(r'`?(\w+)`?\s*=\s*(.+)', assign.strip(), flags=re.DOTALL)
                if am:
                    row[am.group(1)] = cdb_parse_literal(am.group(2))
        else:
            logger.error("[ChannelDB] INSERT tushunolmadi: %s", sql)
            return False

    rows = ChannelStore.table(table)

    if on_dup_update:
        unique_cols = CDB_UNIQUE_KEYS.get(table, list(row.keys()))
        for existing in rows:
            matches = True
            for uc in unique_cols:
                if uc not in row or str(existing.get(uc)) != str(row[uc]):
                    matches = False
                    break
            if matches:
                for assign in cdb_split_top_level_commas(on_dup_update):
                    am = re.match(r'`?(\w+)`?\s*=\s*(.+)', assign.strip(), flags=re.DOTALL)
                    if am:
                        existing[am.group(1)] = cdb_parse_literal(am.group(2))
                ChannelStore.persist(table)
                connect.affected_rows = 1
                return True

    if 'id' not in row:
        row['id'] = ChannelStore.next_id(table)
    rows.append(row)
    ChannelStore.persist(table)

    connect.insert_id = int(row['id'])
    connect.affected_rows = 1
    return True


def cdb_do_update(connect: CDBConnection, sql: str) -> bool:
    m = re.search(r'UPDATE\s+`?(\w+)`?\s+SET\s+(.*?)(?:\s+WHERE\s+(.*))?$', sql, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        logger.error("[ChannelDB] UPDATE tushunolmadi: %s", sql)
        return False
    table = m.group(1)
    set_clause = m.group(2)
    where_str = m.group(3)

    filter_fn = cdb_build_where_filter(where_str)
    assignments = cdb_split_top_level_commas(set_clause)

    rows = ChannelStore.table(table)
    affected = 0

    for row in rows:
        if not filter_fn(row):
            continue
        for assign in assignments:
            am = re.match(r'`?(\w+)`?\s*=\s*(.+)', assign.strip(), flags=re.DOTALL)
            if not am:
                continue
            col = am.group(1)
            expr = am.group(2).strip()

            # "balance = balance + 1" / "balance = balance - 1500" / "captcha_try=captcha_try+1"
            opm = re.fullmatch(r'`?' + re.escape(col) + r'`?\s*([+-])\s*(-?[\d.]+)', expr)
            if opm:
                delta = float(opm.group(2))
                row[col] = float(row.get(col) or 0) + (delta if opm.group(1) == '+' else -delta)
                continue

            row[col] = cdb_parse_literal(expr)
        affected += 1

    if affected > 0:
        ChannelStore.persist(table)
    connect.affected_rows = affected
    return True


def cdb_do_delete(connect: CDBConnection, sql: str) -> bool:
    m = re.search(r'DELETE\s+FROM\s+`?(\w+)`?(?:\s+WHERE\s+(.*))?$', sql, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        logger.error("[ChannelDB] DELETE tushunolmadi: %s", sql)
        return False
    table = m.group(1)
    where_str = m.group(2)
    filter_fn = cdb_build_where_filter(where_str)

    rows = ChannelStore.table(table)
    before = len(rows)
    kept = [r for r in rows if not filter_fn(r)]
    rows.clear()
    rows.extend(kept)
    affected = before - len(rows)

    if affected > 0:
        ChannelStore.persist(table)
    connect.affected_rows = affected
    return True
