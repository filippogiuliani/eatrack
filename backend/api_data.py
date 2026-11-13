"""API: export (Excel, CSV, JSON) and import of the current family's data."""
import csv
import datetime
import io
import json

from flask import Blueprint, abort, g, jsonify, request, send_file

from famkit import backup
import db
import i18n
import migrations
from api_plan import read_plan, write_plan
from auth import rate_limit, require_admin
from common import family_child, placeholders
from i18n import label, tr

bp = Blueprint('data', __name__)

DIARY_COLUMNS = ['carbs', 'broth', 'vegetables', 'protein', 'fruit']  # categories.diary_group
MAX_IMPORT_ROWS = 200_000
BACKUP_FORMAT = 5


def _today():
    return datetime.date.today().isoformat()


def _weekday(date):
    return i18n.WEEKDAYS.get(i18n.language(), i18n.WEEKDAYS['en'])[datetime.date.fromisoformat(date).weekday()]


def _child_filter(conn):
    """SQL filter on c.id from the (repeatable) ?child= parameters; none = every child of the family."""
    ids = [family_child(conn, v) for v in request.args.getlist('child') if v]
    if not ids:
        return '', []
    return f' AND c.id IN ({placeholders(ids)})', ids


def _detail_rows(conn, child_filter):
    """One row per meal × food for the family, limited to the chosen children."""
    where, params = 'c.family_id = ?' + child_filter[0], [g.family_id, *child_filter[1]]
    return conn.execute(f'''
        SELECT m.id AS meal_id, c.name AS child, m.date, m.meal_type, m.notes, m.reaction,
               f.name AS food, cat.key AS category, cat.diary_group, mf.amount
        FROM meals m JOIN children c ON c.id = m.child_id
        LEFT JOIN meal_foods mf ON mf.meal_id = m.id
        LEFT JOIN foods f ON f.id = mf.food_id
        LEFT JOIN categories cat ON cat.id = f.category_id
        WHERE {where}
        ORDER BY m.date, c.name, CASE m.meal_type WHEN 'breakfast' THEN 0 WHEN 'lunch' THEN 1 WHEN 'snack' THEN 2 WHEN 'dinner' THEN 3 ELSE 4 END,
                 m.id, cat.sort_order, f.name''', params).fetchall()


@bp.get('/export/excel')
def export_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    with db.transaction() as conn:
        child_filter = _child_filter(conn)
        rows = _detail_rows(conn, child_filter)
        foods = conn.execute('''SELECT f.name, cat.key AS category, f.archived FROM foods f JOIN categories cat ON cat.id = f.category_id
                                WHERE f.family_id = ? ORDER BY cat.sort_order, f.name''', (g.family_id,)).fetchall()
        firsts = conn.execute('''SELECT c.name AS child, f.name AS food, COUNT(*) AS times,
                                        MIN(CASE WHEN mf.amount != 'refused' THEN m.date END) AS first_time
                                 FROM meal_foods mf JOIN meals m ON m.id = mf.meal_id JOIN children c ON c.id = m.child_id
                                 JOIN foods f ON f.id = mf.food_id
                                 WHERE c.family_id = ?''' + child_filter[0] + ' GROUP BY c.id, f.id',
                              (g.family_id, *child_filter[1])).fetchall()

    wb = Workbook()
    header_font, header_fill = Font(bold=True, color='FFFFFF'), PatternFill('solid', fgColor='1E3A5F')

    def sheet(ws, headers, widths):
        ws.append(headers)
        for i, cell in enumerate(ws[1]):
            cell.font, cell.fill = header_font, header_fill
            ws.column_dimensions[cell.column_letter].width = widths[i]
        ws.freeze_panes = 'A2'

    def date_cell(ws, col, value):
        if value:
            ws.cell(ws.max_row, col).number_format = 'DD/MM/YYYY'

    # Sheet 1: one meal per row, like the diary view
    ws = wb.active
    ws.title = tr('Diary')
    sheet(ws, [tr('Date'), tr('Day'), tr('Child'), tr('Meal')] + [label(c) for c in DIARY_COLUMNS] + [tr('Notes'), tr('Reaction')],
          [12, 11, 14, 11, 28, 22, 34, 34, 22, 40, 10])
    meals = {}
    for r in rows:
        m = meals.setdefault(r['meal_id'], {'row': r, **{c: [] for c in DIARY_COLUMNS}})
        if r['food']:
            m.setdefault(r['diary_group'], []).append(f"{r['food']} ({label(r['amount'])})")
    for m in meals.values():
        r = m['row']
        ws.append([datetime.date.fromisoformat(r['date']), _weekday(r['date']), r['child'], label(r['meal_type'])]
                  + [', '.join(m[c]) for c in DIARY_COLUMNS] + [r['notes'], tr('Yes') if r['reaction'] else ''])
        date_cell(ws, 1, True)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')

    # Sheet 2: one food per row (handy for filters and pivot tables)
    ws = wb.create_sheet(tr('Detail'))
    sheet(ws, [tr('Date'), tr('Day'), tr('Child'), tr('Meal'), tr('Food'), tr('Category'), tr('Amount'), tr('Reaction'), tr('Notes')],
          [12, 11, 14, 11, 28, 16, 16, 10, 40])
    for r in rows:
        if r['food']:
            ws.append([datetime.date.fromisoformat(r['date']), _weekday(r['date']), r['child'], label(r['meal_type']), r['food'],
                       label(r['category']), label(r['amount']), tr('Yes') if r['reaction'] else '', r['notes']])
            date_cell(ws, 1, True)

    # Sheet 3: foods introduced, per child
    ws = wb.create_sheet(tr('Introductions'))
    sheet(ws, [tr('Child'), tr('Food'), tr('Times'), tr('First time')], [14, 30, 8, 13])
    for f in sorted(firsts, key=lambda x: (x['child'], x['first_time'] or '9999')):
        ws.append([f['child'], f['food'], f['times'], datetime.date.fromisoformat(f['first_time']) if f['first_time'] else None])
        date_cell(ws, 4, f['first_time'])

    ws = wb.create_sheet(tr('Foods'))
    sheet(ws, [tr('Food'), tr('Category'), tr('Archived')], [30, 16, 11])
    for f in foods:
        ws.append([f['name'], label(f['category']), tr('Yes') if f['archived'] else ''])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f'eatrack-{tr("diary")}-{_today()}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@bp.get('/export/csv')
def export_csv():
    with db.transaction() as conn:
        rows = _detail_rows(conn, _child_filter(conn))
    buf = io.StringIO()
    buf.write('﻿')  # BOM: lets Excel detect UTF-8
    w = csv.writer(buf, delimiter=';')
    w.writerow([tr('Date'), tr('Day'), tr('Child'), tr('Meal'), tr('Food'), tr('Category'), tr('Amount'), tr('Reaction'), tr('Notes')])
    for r in rows:
        w.writerow([r['date'], _weekday(r['date']), r['child'], label(r['meal_type']), r['food'] or '', label(r['category']),
                    label(r['amount']), tr('Yes') if r['reaction'] else '', r['notes']])
    return send_file(io.BytesIO(buf.getvalue().encode('utf-8')), as_attachment=True,
                     download_name=f'eatrack-{tr("diary")}-{_today()}.csv', mimetype='text/csv')


# ---------- Family JSON backup ----------

def dump_family(conn, family_id):
    q = lambda sql: [dict(r) for r in conn.execute(sql, (family_id,))]
    return {
        'app': 'eatrack',
        'version': BACKUP_FORMAT,
        'exported_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'family': conn.execute('SELECT name FROM families WHERE id = ?', (family_id,)).fetchone()['name'],
        'categories': [dict(r) for r in conn.execute('SELECT id, key FROM categories')],
        'tables': {
            'children': q('SELECT id, name, birth_date, archived FROM children WHERE family_id = ?'),
            'foods': q('SELECT id, name, category_id, archived FROM foods WHERE family_id = ?'),
            'meals': q('''SELECT m.id, m.child_id, m.date, m.meal_type, m.notes, m.reaction FROM meals m
                          JOIN children c ON c.id = m.child_id WHERE c.family_id = ?'''),
            'meal_foods': q('''SELECT mf.* FROM meal_foods mf JOIN meals m ON m.id = mf.meal_id
                               JOIN children c ON c.id = m.child_id WHERE c.family_id = ?'''),
            'jars': q('SELECT id, label, location, made_on, notes, used_on, meal_id FROM jars WHERE family_id = ?'),
            'jar_foods': q('SELECT jf.* FROM jar_foods jf JOIN jars j ON j.id = jf.jar_id WHERE j.family_id = ?'),
        },
        # Weekly plan per child (child and food ids as in the tables above)
        'plans': {str(r[0]): read_plan(conn, r[0]) for r in conn.execute('SELECT id FROM children WHERE family_id = ?', (family_id,))},
    }


@bp.get('/export/json')
def export_json():
    with db.transaction() as conn:
        data = dump_family(conn, g.family_id)
    payload = json.dumps(data, ensure_ascii=False, indent=1).encode('utf-8')
    return send_file(io.BytesIO(payload), as_attachment=True, download_name=f'eatrack-backup-{_today()}.json',
                     mimetype='application/json')


def _date(value, what):
    try:
        return datetime.date.fromisoformat(str(value)).isoformat()
    except ValueError:
        abort(400, f'Invalid backup: {what} with wrong date ({value!r})')


def import_family(conn, data, family_id):
    """Replace the family's data with the backup's (any version). Ids are regenerated."""
    if migrations.is_legacy_backup(data):
        data = migrations.legacy_backup(data)
    if not isinstance(data, dict) or data.get('app') != 'eatrack' or not isinstance(data.get('tables'), dict):
        abort(400, 'The file is not an eaTrack backup')
    t = data['tables']
    rows = {k: t.get(k) or [] for k in ['categories', 'children', 'foods', 'meals', 'meal_foods', 'jars', 'jar_foods']}
    if any(not isinstance(v, list) or any(not isinstance(x, dict) for x in v) for v in rows.values()):
        abort(400, 'Invalid backup: malformed tables')
    if sum(len(v) for v in rows.values()) > MAX_IMPORT_ROWS:
        abort(400, 'Backup too large')
    category_keys = {c.get('id'): c.get('key') for c in (data.get('categories') or []) if isinstance(c, dict)}

    conn.execute('DELETE FROM jars WHERE family_id = ?', (family_id,))
    conn.execute('DELETE FROM children WHERE family_id = ?', (family_id,))
    conn.execute('DELETE FROM foods WHERE family_id = ?', (family_id,))

    child_ids, food_ids, meal_ids, jar_ids = {}, {}, {}, {}
    for c in rows['children']:
        birth = _date(c['birth_date'], 'birth date') if c.get('birth_date') else None
        child_ids[c.get('id')] = conn.execute('INSERT INTO children (family_id, name, birth_date, archived) VALUES (?,?,?,?)',
                                              (family_id, str(c.get('name') or 'Baby')[:60], birth, 1 if c.get('archived') else 0)).lastrowid
    fallback_child = None
    if not child_ids:  # very old backups: a single implicit child
        fallback_child = conn.execute('INSERT INTO children (family_id, name) VALUES (?, ?)',
                                      (family_id, i18n.tr('Child'))).lastrowid

    for f in rows['foods']:
        name = str(f.get('name') or '').strip()[:100]
        if not name:
            continue
        key = str(category_keys.get(f.get('category_id')) or f.get('category') or 'other')[:60]
        conn.execute('INSERT OR IGNORE INTO foods (family_id, name, category_id, archived) VALUES (?,?,?,?)',
                     (family_id, name, db.category_id(conn, key), 1 if f.get('archived') else 0))
        food_ids[f.get('id')] = conn.execute('SELECT id FROM foods WHERE family_id = ? AND name = ?', (family_id, name)).fetchone()[0]

    for m in rows['meals']:
        child = child_ids.get(m.get('child_id'), fallback_child) or next(iter(child_ids.values()), None)
        if child is None or m.get('meal_type') not in db.MEAL_TYPES:
            abort(400, 'Invalid backup: meal without child or with wrong type')
        meal_ids[m.get('id')] = conn.execute('INSERT INTO meals (child_id, date, meal_type, notes, reaction) VALUES (?,?,?,?,?)',
                                             (child, _date(m.get('date'), 'meal'), m['meal_type'], str(m.get('notes') or '')[:2000],
                                              1 if m.get('reaction') else 0)).lastrowid
    for r in rows['meal_foods']:
        if r.get('meal_id') in meal_ids and r.get('food_id') in food_ids and r.get('amount') in db.AMOUNTS:
            conn.execute('INSERT OR IGNORE INTO meal_foods VALUES (?,?,?)', (meal_ids[r['meal_id']], food_ids[r['food_id']], r['amount']))

    for j in rows['jars']:
        if j.get('location') not in db.LOCATIONS:
            continue
        jar_ids[j.get('id')] = conn.execute(
            '''INSERT INTO jars (family_id, label, location, made_on, notes, used_on, meal_id) VALUES (?,?,?,?,?,?,?)''',
            (family_id, str(j.get('label') or '?')[:30], j['location'], _date(j.get('made_on'), 'jar'),
             str(j.get('notes') or '')[:500], _date(j['used_on'], 'jar') if j.get('used_on') else None,
             meal_ids.get(j.get('meal_id')))).lastrowid
    for r in rows['jar_foods']:
        if r.get('jar_id') in jar_ids and r.get('food_id') in food_ids:
            conn.execute('INSERT OR IGNORE INTO jar_foods VALUES (?,?)', (jar_ids[r['jar_id']], food_ids[r['food_id']]))

    plans = data.get('plans') or {}
    if isinstance(plans, dict):
        for old_id, plan in plans.items():
            child = next((new for old, new in child_ids.items() if str(old) == str(old_id)), None)
            if child is None or not isinstance(plan, dict):
                continue
            menu = plan.get('menu') if isinstance(plan.get('menu'), list) else []
            for m in menu:  # remap food ids, dropping unknown ones
                if isinstance(m, dict) and isinstance(m.get('foods'), list):
                    m['foods'] = [food_ids[f] for f in m['foods'] if f in food_ids]
            write_plan(conn, child, {'frequencies': plan.get('frequencies'), 'menu': menu}, check_foods=False)

    return {'children': len(child_ids) or 1, 'foods': len(food_ids), 'meals': len(meal_ids), 'jars': len(jar_ids)}


@bp.post('/import')
def import_backup():
    """Import a .json backup: it REPLACES all of the family's data (admin only)."""
    require_admin()
    rate_limit(f'import:{g.family_id}', 10, 3600)
    f = request.files.get('file')
    if not f or not f.filename:
        abort(400, 'No file uploaded')
    if not f.filename.lower().endswith('.json'):
        abort(400, 'Unsupported format: upload an eaTrack .json backup')
    try:
        data = json.load(f.stream)
    except (ValueError, UnicodeDecodeError):
        abort(400, 'Unreadable JSON')
    backup.create_backup('pre-import')  # server-side safety copy of the whole database
    with db.transaction() as conn:
        imported = import_family(conn, data, g.family_id)
    return jsonify(ok=True, imported=imported)
