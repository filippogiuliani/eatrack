"""eaTrack's part of the weHub link (the rest is famkit.hub): who this app's people are, what happens when a
member leaves, how two families made separately are merged. Registered in app.py with hub.use(hub_hooks)."""
from flask import g, jsonify

from famkit import hub

# ======================================================================
# This app's people: the children (weHub people marked as children)
# ======================================================================

def bump(conn, family_id):
    pass  # eaTrack has no family version: pages reload on their own


def apply_people(conn, family_id, snap):
    """weHub children become eaTrack children. Someone removed in weHub is only archived: meals are never deleted."""
    seen = set()
    for p in snap['people']:
        if p.get('kind') != 'child':
            continue
        r = conn.execute('SELECT id FROM children WHERE family_id = ? AND hub_id = ?', (family_id, p['hub_id'])).fetchone()
        if not r and p.get('local_id'):
            r = conn.execute('SELECT id FROM children WHERE family_id = ? AND id = ? AND hub_id IS NULL',
                             (family_id, p['local_id'])).fetchone()
        if not r:
            r = conn.execute('SELECT id FROM children WHERE family_id = ? AND name = ? COLLATE NOCASE AND hub_id IS NULL',
                             (family_id, p['name'])).fetchone()
        if r:
            conn.execute('UPDATE children SET hub_id = ?, name = ?, birth_date = COALESCE(?, birth_date) WHERE id = ?',
                         (p['hub_id'], p['name'], p.get('birth_date'), r['id']))
            seen.add(r['id'])
        else:
            seen.add(conn.execute('INSERT INTO children (family_id, name, birth_date, hub_id) VALUES (?,?,?,?)',
                                  (family_id, p['name'], p.get('birth_date'), p['hub_id'])).lastrowid)
    for (cid,) in conn.execute('SELECT id FROM children WHERE family_id = ? AND hub_id IS NOT NULL', (family_id,)).fetchall():
        if cid not in seen:
            conn.execute('UPDATE children SET archived = 1, hub_id = NULL WHERE id = ?', (cid,))


def export_people(conn, family_id):
    return [{'local_id': r['id'], 'name': r['name'], 'birth_date': r['birth_date'], 'kind': 'child'}
            for r in conn.execute('SELECT id, name, birth_date FROM children WHERE family_id = ?', (family_id,))]


def on_member_removed(conn, family_id, user_id):
    pass


def merge_data(conn, src, dst, report):
    """eaTrack: foods and children with the same name become one (meals, jars and plans follow); the rest moves."""
    for f in conn.execute('SELECT id, name FROM foods WHERE family_id = ?', (src,)).fetchall():
        t = conn.execute('SELECT id FROM foods WHERE family_id = ? AND name = ? COLLATE NOCASE', (dst, f['name'])).fetchone()
        if t:
            for table in ('meal_foods', 'jar_foods', 'plan_meal_foods'):
                conn.execute(f'UPDATE OR IGNORE {table} SET food_id = ? WHERE food_id = ?', (t['id'], f['id']))
                conn.execute(f'DELETE FROM {table} WHERE food_id = ?', (f['id'],))
            conn.execute('DELETE FROM foods WHERE id = ?', (f['id'],))
            hub.count(report, 'foods_merged', 1)
        else:
            conn.execute('UPDATE foods SET family_id = ? WHERE id = ?', (dst, f['id']))
            hub.count(report, 'foods', 1)
    for c in conn.execute('SELECT * FROM children WHERE family_id = ?', (src,)).fetchall():
        t = conn.execute('SELECT * FROM children WHERE family_id = ? AND name = ? COLLATE NOCASE', (dst, c['name'])).fetchone()
        if not t:
            conn.execute('UPDATE children SET family_id = ? WHERE id = ?', (dst, c['id']))
            hub.count(report, 'children', 1)
            continue
        # The same child, tracked twice: one child with all the meals; the destination's plan wins
        hub.count(report, 'meals', conn.execute('UPDATE meals SET child_id = ? WHERE child_id = ?', (t['id'], c['id'])).rowcount)
        if c['birth_date'] and not t['birth_date']:
            conn.execute('UPDATE children SET birth_date = ? WHERE id = ?', (c['birth_date'], t['id']))
        conn.execute('UPDATE OR IGNORE plan_frequencies SET child_id = ? WHERE child_id = ?', (t['id'], c['id']))
        conn.execute('DELETE FROM plan_frequencies WHERE child_id = ?', (c['id'],))
        for pm in conn.execute('SELECT id, weekday, meal_type FROM plan_meals WHERE child_id = ?', (c['id'],)).fetchall():
            if conn.execute('SELECT 1 FROM plan_meals WHERE child_id = ? AND weekday = ? AND meal_type = ?',
                            (t['id'], pm['weekday'], pm['meal_type'])).fetchone():
                conn.execute('DELETE FROM plan_meal_foods WHERE plan_meal_id = ?', (pm['id'],))
                conn.execute('DELETE FROM plan_meals WHERE id = ?', (pm['id'],))
            else:
                conn.execute('UPDATE plan_meals SET child_id = ? WHERE id = ?', (t['id'], pm['id']))
        conn.execute('DELETE FROM children WHERE id = ?', (c['id'],))
        hub.count(report, 'children_merged', 1)
    hub.count(report, 'jars', conn.execute('UPDATE jars SET family_id = ? WHERE family_id = ?', (dst, src)).rowcount)
    if conn.execute('SELECT 1 FROM dotrack_links WHERE family_id = ?', (dst,)).fetchone():
        conn.execute('DELETE FROM dotrack_links WHERE family_id = ?', (src,))
    else:
        conn.execute('UPDATE dotrack_links SET family_id = ? WHERE family_id = ?', (dst, src))


# ---------- weHub's home: today's meals and the jars to use soon ----------

JAR_WARN_DAYS = {'fridge': 2, 'freezer': 30, 'pantry': 60}   # as in the interface (frontend/src/lib/constants.js)


@hub.service('/summary')
def summary():
    """{children: [{name, meals_today: [meal types]}], jars_soon, url}"""
    import datetime

    import db
    from auth import BASE_URL
    today = datetime.date.today()
    with db.transaction() as conn:
        children = conn.execute('SELECT id, name FROM children WHERE family_id = ? AND archived = 0 ORDER BY birth_date DESC, name',
                                (g.family_id,)).fetchall()
        meals = {}
        for r in conn.execute('''SELECT m.child_id, m.meal_type FROM meals m JOIN children c ON c.id = m.child_id
                                 WHERE c.family_id = ? AND m.date = ? ORDER BY m.created_at''', (g.family_id, today.isoformat())):
            meals.setdefault(r['child_id'], []).append(r['meal_type'])
        soon = 0
        for j in conn.execute('SELECT location, made_on FROM jars WHERE family_id = ? AND used_on IS NULL', (g.family_id,)):
            age = (today - datetime.date.fromisoformat(j['made_on'])).days
            soon += age >= JAR_WARN_DAYS.get(j['location'], 2)
    return jsonify(children=[{'name': c['name'], 'meals_today': meals.get(c['id'], [])} for c in children],
                   jars_soon=soon, url=BASE_URL or None)
