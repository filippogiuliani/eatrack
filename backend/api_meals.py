"""API: diary meals (always of a child of the current family)."""
from flask import Blueprint, abort, g, jsonify, request

import db
from common import body, check_family_foods, family_child, id_list, placeholders, requested_child, text, valid_date

bp = Blueprint('meals', __name__)

MEAL_ORDER = "CASE m.meal_type WHEN 'breakfast' THEN 0 WHEN 'lunch' THEN 1 WHEN 'snack' THEN 2 WHEN 'dinner' THEN 3 ELSE 4 END"


def load_meals(conn, where, params):
    """Meals with their foods and jars. `where` must already restrict to the family/child."""
    meals = [dict(r) for r in conn.execute(
        f'''SELECT m.*, u.name AS created_by_name FROM meals m LEFT JOIN users u ON u.id = m.created_by
            WHERE {where} ORDER BY m.date DESC, {MEAL_ORDER}, m.id''', params)]
    if not meals:
        return []
    by_id = {m['id']: m for m in meals}
    for m in meals:
        m['foods'], m['jars'] = [], []
    ids = list(by_id)
    for r in conn.execute(f'''SELECT mf.meal_id, mf.food_id AS id, f.name, f.category_id, mf.amount
                              FROM meal_foods mf JOIN foods f ON f.id = mf.food_id
                              JOIN categories c ON c.id = f.category_id
                              WHERE mf.meal_id IN ({placeholders(ids)}) ORDER BY c.sort_order, f.name''', ids):
        r = dict(r)
        by_id[r.pop('meal_id')]['foods'].append(r)
    for r in conn.execute(f'SELECT id, label, location, meal_id FROM jars WHERE meal_id IN ({placeholders(ids)})', ids):
        r = dict(r)
        by_id[r.pop('meal_id')]['jars'].append(r)
    return meals


@bp.get('/meals')
def list_meals():
    start, end = request.args.get('from'), request.args.get('to')
    if not start or not end:
        abort(400, 'from/to parameters are required')
    with db.transaction() as conn:
        child_id = requested_child(conn)
        return jsonify(load_meals(conn, 'm.child_id = ? AND m.date BETWEEN ? AND ?', (child_id, valid_date(start), valid_date(end))))


@bp.get('/meals/recent')
def recent():
    """Latest meals of a given type, for the "repeat a meal" feature."""
    meal_type = request.args.get('meal_type', 'lunch')
    with db.transaction() as conn:
        child_id = requested_child(conn)
        ids = [r[0] for r in conn.execute(
            'SELECT id FROM meals WHERE child_id = ? AND meal_type = ? ORDER BY date DESC, id DESC LIMIT 8', (child_id, meal_type))]
        if not ids:
            return jsonify([])
        return jsonify(load_meals(conn, f'm.id IN ({placeholders(ids)})', ids))


def _read(d):
    meal_type = d.get('meal_type')
    if meal_type not in db.MEAL_TYPES:
        abort(400, 'Invalid meal type')
    foods = d.get('foods') or []
    if not isinstance(foods, list) or len(foods) > 100:
        abort(400, 'foods: invalid list')
    items = {}
    for f in foods:
        try:
            food_id = int(f['id'])
        except (TypeError, ValueError, KeyError):
            abort(400, 'foods: invalid id')
        amount = f.get('amount', 'full')
        if amount not in db.AMOUNTS:
            abort(400, f'Invalid amount: {amount}')
        items[food_id] = amount
    jars = id_list(d.get('jars'), 'jars')[:20]
    if not items and not jars:
        abort(400, 'Select at least one food')
    return {
        'date': valid_date(d.get('date')),
        'meal_type': meal_type,
        'notes': text(d.get('notes')),
        'reaction': 1 if d.get('reaction') else 0,
        'items': items,
        'jars': jars,
    }


def _save_contents(conn, meal_id, v):
    # Jars used in the meal: their foods join the meal (unless already listed) and the jar is marked as used
    for jar_id in v['jars']:
        j = conn.execute('SELECT id, meal_id, used_on FROM jars WHERE id = ? AND family_id = ?', (jar_id, g.family_id)).fetchone()
        if not j:
            abort(400, 'Jar does not exist')
        if j['used_on'] and j['meal_id'] != meal_id:
            abort(409, 'One of the jars has already been used')
        for (food_id,) in conn.execute('SELECT food_id FROM jar_foods WHERE jar_id = ?', (jar_id,)):
            v['items'].setdefault(food_id, 'full')
        conn.execute('UPDATE jars SET used_on = ?, meal_id = ? WHERE id = ?', (v['date'], meal_id, jar_id))

    check_family_foods(conn, list(v['items']))
    conn.execute('DELETE FROM meal_foods WHERE meal_id = ?', (meal_id,))
    for food_id, amount in v['items'].items():
        conn.execute('INSERT INTO meal_foods (meal_id, food_id, amount) VALUES (?,?,?)', (meal_id, food_id, amount))


def _check_family_meal(conn, meal_id):
    r = conn.execute('SELECT m.id FROM meals m JOIN children c ON c.id = m.child_id WHERE m.id = ? AND c.family_id = ?',
                     (meal_id, g.family_id)).fetchone()
    if not r:
        abort(404, 'Meal not found')


@bp.post('/meals')
def create_meal():
    d = body()
    v = _read(d)
    with db.transaction() as conn:
        child_id = family_child(conn, d.get('child_id'))
        meal_id = conn.execute('INSERT INTO meals (child_id, date, meal_type, notes, reaction, created_by) VALUES (?,?,?,?,?,?)',
                               (child_id, v['date'], v['meal_type'], v['notes'], v['reaction'], g.user['id'])).lastrowid
        _save_contents(conn, meal_id, v)
    return jsonify(id=meal_id), 201


@bp.put('/meals/<int:meal_id>')
def update_meal(meal_id):
    d = body()
    v = _read(d)
    with db.transaction() as conn:
        _check_family_meal(conn, meal_id)
        child_id = family_child(conn, d.get('child_id'))
        conn.execute('UPDATE meals SET child_id=?, date=?, meal_type=?, notes=?, reaction=? WHERE id=?',
                     (child_id, v['date'], v['meal_type'], v['notes'], v['reaction'], meal_id))
        # Jars removed from the meal go back to the pantry
        kept = v['jars']
        exclude = f' AND id NOT IN ({placeholders(kept)})' if kept else ''
        conn.execute(f'UPDATE jars SET used_on = NULL, meal_id = NULL WHERE meal_id = ?{exclude}', (meal_id, *kept))
        _save_contents(conn, meal_id, v)
    return jsonify(ok=True)


@bp.delete('/meals/<int:meal_id>')
def delete_meal(meal_id):
    with db.transaction() as conn:
        _check_family_meal(conn, meal_id)
        # The meal's jars go back to the pantry
        conn.execute('UPDATE jars SET used_on = NULL, meal_id = NULL WHERE meal_id = ?', (meal_id,))
        conn.execute('DELETE FROM meals WHERE id = ?', (meal_id,))
    return jsonify(ok=True)
