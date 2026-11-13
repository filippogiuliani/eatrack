"""Helpers shared by the API modules."""

from flask import abort, g, request

from famkit.web import body, placeholders, rows, text, valid_date  # noqa: F401  (the base helpers)


def id_list(values, field):
    if values is None:
        return []
    if not isinstance(values, list):
        abort(400, f'{field}: list expected')
    try:
        return list(dict.fromkeys(int(v) for v in values))  # no duplicates, order preserved
    except (TypeError, ValueError):
        abort(400, f'{field}: invalid ids')


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
