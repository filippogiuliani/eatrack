"""Helpers shared by the API modules."""
import datetime

from flask import abort, g, request


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, 'Invalid request (JSON expected)')
    return data


def valid_date(value, field='date'):
    try:
        return datetime.date.fromisoformat(str(value)).isoformat()
    except ValueError:
        abort(400, f'{field}: invalid date')


def text(value, max_len=2000):
    return str(value or '').strip()[:max_len]


def id_list(values, field):
    if values is None:
        return []
    if not isinstance(values, list):
        abort(400, f'{field}: list expected')
    try:
        return list(dict.fromkeys(int(v) for v in values))  # no duplicates, order preserved
    except (TypeError, ValueError):
        abort(400, f'{field}: invalid ids')


def rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def placeholders(values):
    return ','.join('?' * len(values))


# ---------- Ownership checks against the current family (g.family_id) ----------

def family_child(conn, value):
    """Id of a child of the current family, or 400/404."""
    try:
        child_id = int(value)
    except (TypeError, ValueError):
        abort(400, 'Invalid child')
    if not conn.execute('SELECT 1 FROM children WHERE id = ? AND family_id = ?', (child_id, g.family_id)).fetchone():
        abort(404, 'Child not found')
    return child_id


def requested_child(conn):
    """Child from the required ?child= query parameter."""
    return family_child(conn, request.args.get('child'))


def check_family_foods(conn, ids):
    if not ids:
        return
    n = conn.execute(f'SELECT COUNT(*) FROM foods WHERE family_id = ? AND id IN ({placeholders(ids)})',
                     (g.family_id, *ids)).fetchone()[0]
    if n != len(set(ids)):
        abort(400, 'Invalid food')
