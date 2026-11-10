"""API: jars of baby food kept in the fridge, freezer or pantry."""
from flask import Blueprint, abort, g, jsonify, request

import db
from common import body, check_family_foods, id_list, placeholders, text, valid_date

bp = Blueprint('pantry', __name__)


def load_jars(conn, used=False):
    condition = 'j.used_on IS NOT NULL' if used else 'j.used_on IS NULL'
    order = 'j.used_on DESC, j.id DESC LIMIT 100' if used else 'CAST(j.label AS INTEGER), j.label, j.id'
    jars = [dict(r) for r in conn.execute(f'SELECT j.* FROM jars j WHERE j.family_id = ? AND {condition} ORDER BY {order}',
                                          (g.family_id,))]
    if jars:
        by_id = {j['id']: j for j in jars}
        for j in jars:
            j['foods'] = []
        ids = list(by_id)
        for row in conn.execute(f'''SELECT jf.jar_id, f.id, f.name, f.category_id FROM jar_foods jf
                                    JOIN foods f ON f.id = jf.food_id JOIN categories c ON c.id = f.category_id
                                    WHERE jf.jar_id IN ({placeholders(ids)}) ORDER BY c.sort_order, f.name''', ids):
            row = dict(row)
            by_id[row.pop('jar_id')]['foods'].append(row)
    return jars


@bp.get('/jars')
def list_jars():
    with db.transaction() as conn:
        return jsonify(load_jars(conn, used=request.args.get('status') == 'used'))


def _read(d):
    location = d.get('location')
    if location not in db.LOCATIONS:
        abort(400, 'Invalid location')
    foods = id_list(d.get('foods'), 'foods')
    if not foods:
        abort(400, 'Select at least one food')
    return location, valid_date(d.get('made_on'), 'preparation date'), text(d.get('notes'), 500), foods


def _set_foods(conn, jar_id, foods):
    check_family_foods(conn, foods)
    conn.execute('DELETE FROM jar_foods WHERE jar_id = ?', (jar_id,))
    for food_id in foods:
        conn.execute('INSERT INTO jar_foods (jar_id, food_id) VALUES (?, ?)', (jar_id, food_id))


@bp.post('/jars')
def create_jars():
    """Create one or more jars with the same contents (one per label given)."""
    d = body()
    location, made_on, notes, foods = _read(d)
    labels = [text(n, 30) for n in (d.get('labels') or [])[:50] if text(n, 30)]
    if not labels:
        abort(400, 'Enter at least one jar number/name')
    ids = []
    with db.transaction() as conn:
        for label in labels:
            jar_id = conn.execute('INSERT INTO jars (family_id, label, location, made_on, notes) VALUES (?,?,?,?,?)',
                                  (g.family_id, label, location, made_on, notes)).lastrowid
            _set_foods(conn, jar_id, foods)
            ids.append(jar_id)
    return jsonify(ids=ids), 201


@bp.put('/jars/<int:jar_id>')
def update_jar(jar_id):
    d = body()
    location, made_on, notes, foods = _read(d)
    label = text(d.get('label'), 30)
    if not label:
        abort(400, 'Number/name is required')
    with db.transaction() as conn:
        cur = conn.execute('UPDATE jars SET label=?, location=?, made_on=?, notes=? WHERE id=? AND family_id=?',
                           (label, location, made_on, notes, jar_id, g.family_id))
        if cur.rowcount == 0:
            abort(404, 'Jar not found')
        _set_foods(conn, jar_id, foods)
    return jsonify(ok=True)


@bp.post('/jars/<int:jar_id>/move')
def move_jar(jar_id):
    location = body().get('location')
    if location not in db.LOCATIONS:
        abort(400, 'Invalid location')
    with db.transaction() as conn:
        if conn.execute('UPDATE jars SET location = ? WHERE id = ? AND family_id = ?', (location, jar_id, g.family_id)).rowcount == 0:
            abort(404, 'Jar not found')
    return jsonify(ok=True)


@bp.delete('/jars/<int:jar_id>')
def delete_jar(jar_id):
    """Delete a jar (e.g. thrown away). Jars used in a meal are managed from the meal."""
    with db.transaction() as conn:
        if conn.execute('DELETE FROM jars WHERE id = ? AND family_id = ?', (jar_id, g.family_id)).rowcount == 0:
            abort(404, 'Jar not found')
    return jsonify(ok=True)
