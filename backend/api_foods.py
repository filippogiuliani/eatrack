"""API: categories (shared by everyone) and foods (per family)."""
import sqlite3

from flask import Blueprint, abort, g, jsonify, request

import db
from common import body, family_child, rows, text

bp = Blueprint('foods', __name__)

MAX_FOODS = 2000


@bp.get('/categories')
def categories():
    with db.transaction() as conn:
        return jsonify(rows(conn.execute('SELECT id, key, diary_group, macro, sort_order FROM categories ORDER BY sort_order, key')))


@bp.get('/foods')
def list_foods():
    """Family foods with a usage summary for the given child (?child=)."""
    with db.transaction() as conn:
        child_id = family_child(conn, request.args['child']) if request.args.get('child') else -1
        return jsonify(rows(conn.execute('''
            SELECT f.id, f.name, f.category_id, f.archived,
                   COUNT(m.id) AS times,
                   SUM(CASE WHEN m.id IS NOT NULL AND mf.amount = 'refused' THEN 1 ELSE 0 END) AS refused,
                   SUM(CASE WHEN m.reaction = 1 THEN 1 ELSE 0 END) AS reactions,
                   MIN(CASE WHEN mf.amount != 'refused' THEN m.date END) AS first_time,
                   MAX(m.date) AS last_time
            FROM foods f
            JOIN categories c ON c.id = f.category_id
            LEFT JOIN meal_foods mf ON mf.food_id = f.id
            LEFT JOIN meals m ON m.id = mf.meal_id AND m.child_id = ?
            WHERE f.family_id = ?
            GROUP BY f.id
            ORDER BY c.sort_order, f.name COLLATE NOCASE
        ''', (child_id, g.family_id))))


def _validate(d, conn):
    name = text(d.get('name'), 100)
    if not name:
        abort(400, 'Name is required')
    try:
        category = int(d.get('category_id'))
    except (TypeError, ValueError):
        abort(400, 'Category is required')
    if not conn.execute('SELECT 1 FROM categories WHERE id = ?', (category,)).fetchone():
        abort(400, 'Category does not exist')
    return name, category


@bp.post('/foods')
def create_food():
    try:
        with db.transaction() as conn:
            if conn.execute('SELECT COUNT(*) FROM foods WHERE family_id = ?', (g.family_id,)).fetchone()[0] >= MAX_FOODS:
                abort(400, 'You have reached the maximum number of foods')
            name, category = _validate(body(), conn)
            food_id = conn.execute('INSERT INTO foods (family_id, name, category_id) VALUES (?,?,?)',
                                   (g.family_id, name, category)).lastrowid
    except sqlite3.IntegrityError:
        abort(409, 'A food with this name already exists')
    return jsonify(id=food_id), 201


@bp.put('/foods/<int:food_id>')
def update_food(food_id):
    d = body()
    try:
        with db.transaction() as conn:
            name, category = _validate(d, conn)
            cur = conn.execute('UPDATE foods SET name = ?, category_id = ?, archived = ? WHERE id = ? AND family_id = ?',
                               (name, category, 1 if d.get('archived') else 0, food_id, g.family_id))
            if cur.rowcount == 0:
                abort(404, 'Food not found')
    except sqlite3.IntegrityError:
        abort(409, 'A food with this name already exists')
    return jsonify(ok=True)


@bp.delete('/foods/<int:food_id>')
def delete_food(food_id):
    """A food that was already used is only archived, so the history stays intact."""
    with db.transaction() as conn:
        if not conn.execute('SELECT 1 FROM foods WHERE id = ? AND family_id = ?', (food_id, g.family_id)).fetchone():
            abort(404, 'Food not found')
        used = conn.execute('''SELECT EXISTS(SELECT 1 FROM meal_foods WHERE food_id = ?)
                                   OR EXISTS(SELECT 1 FROM jar_foods WHERE food_id = ?)
                                   OR EXISTS(SELECT 1 FROM plan_meal_foods WHERE food_id = ?)''',
                            (food_id, food_id, food_id)).fetchone()[0]
        if used:
            conn.execute('UPDATE foods SET archived = 1 WHERE id = ?', (food_id,))
            return jsonify(archived=True)
        conn.execute('DELETE FROM foods WHERE id = ?', (food_id,))
    return jsonify(deleted=True)
