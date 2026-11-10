"""API: statistics on how balanced the meals are."""
import datetime
from collections import Counter, defaultdict

from flask import Blueprint, abort, jsonify, request

import db
from common import requested_child, valid_date

bp = Blueprint('stats', __name__)


@bp.get('/stats')
def stats():
    """For each macro category, count in how many lunches/dinners (and snacks) it appeared.
    Several vegetables in the same meal (e.g. a purée) count as one appearance.
    `today` comes from the browser to avoid server time zone issues."""
    today = datetime.date.fromisoformat(valid_date(request.args.get('today') or datetime.date.today().isoformat()))
    try:
        days = max(1, min(int(request.args.get('days', 7)), 3650))
    except ValueError:
        abort(400, 'invalid days')
    start = (today - datetime.timedelta(days=days - 1)).isoformat()
    end = today.isoformat()

    with db.transaction() as conn:
        child_id = requested_child(conn)
        categories = [dict(r) for r in conn.execute('SELECT * FROM categories ORDER BY sort_order')]
        meals = [dict(r) for r in conn.execute(
            'SELECT id, date, meal_type, reaction FROM meals WHERE child_id = ? AND date BETWEEN ? AND ?', (child_id, start, end))]
        items = conn.execute('''SELECT mf.meal_id, mf.amount, f.id AS food_id, f.name, c.macro, c.id AS category_id
                                FROM meal_foods mf JOIN meals m ON m.id = mf.meal_id
                                JOIN foods f ON f.id = mf.food_id JOIN categories c ON c.id = f.category_id
                                WHERE m.child_id = ? AND m.date BETWEEN ? AND ?''', (child_id, start, end)).fetchall()
        first_times = conn.execute('''SELECT f.id, f.name, f.category_id, MIN(m.date) AS first_time
                                      FROM meal_foods mf JOIN meals m ON m.id = mf.meal_id JOIN foods f ON f.id = mf.food_id
                                      WHERE m.child_id = ? AND mf.amount != 'refused' GROUP BY f.id HAVING first_time BETWEEN ? AND ?
                                      ORDER BY first_time DESC''', (child_id, start, end)).fetchall()

    type_of = {m['id']: m['meal_type'] for m in meals}
    appearances = defaultdict(set)  # macro -> ids of the meals where it appears
    eaten, refused, category_of = Counter(), Counter(), {}
    for i in items:
        category_of[i['name']] = i['category_id']
        if i['amount'] == 'refused':
            refused[i['name']] += 1
            continue
        appearances[i['macro']].add(i['meal_id'])
        eaten[i['name']] += 1

    main_meals = sum(1 for m in meals if m['meal_type'] in db.MAIN_MEALS)
    snacks = sum(1 for m in meals if m['meal_type'] == 'snack')

    seen, rows = set(), []
    for c in categories:
        macro = c['macro']
        if macro in seen:
            continue
        seen.add(macro)
        ids = appearances.get(macro, set())
        main = sum(1 for meal_id in ids if type_of[meal_id] in db.MAIN_MEALS)
        rows.append({
            'macro': macro,
            'main': main,
            'pct': round(main / main_meals * 100) if main_meals else 0,
            'snack': sum(1 for meal_id in ids if type_of[meal_id] == 'snack'),
        })

    return jsonify(
        start=start, end=end, days=days,
        main_meals=main_meals, snacks=snacks,
        days_logged=len({m['date'] for m in meals}),
        reactions=sum(1 for m in meals if m['reaction']),
        categories=rows,
        top=[{'name': n, 'times': k, 'category_id': category_of[n]} for n, k in eaten.most_common()],
        refused=[{'name': n, 'times': k, 'category_id': category_of[n]} for n, k in refused.most_common(10)],
        new=[dict(r) for r in first_times],
        variety=len(eaten),
    )
