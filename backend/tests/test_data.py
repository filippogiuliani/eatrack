"""Export (Excel, CSV, JSON), backup import and deleting data per child."""
import io
import json
import os

import db
from conftest import ok


def csv_rows(r):
    assert r.status_code == 200
    return [line.split(';') for line in r.data.decode('utf-8-sig').strip().splitlines()[1:]]


def upload(c, content, name='backup.json'):
    return c.post('/api/import', data={'file': (io.BytesIO(content), name)}, content_type='multipart/form-data')


def backups():
    return os.listdir(os.path.join(db.DATA_DIR, 'backups'))


def test_csv_export_filtered_by_child(family):
    f = family
    f.meal(f.one, '2026-11-08', ['Mela'])
    f.meal(f.two, '2026-11-08', ['Pera'])
    assert {r[2] for r in csv_rows(f.c.get('/api/export/csv'))} == {'One', 'Two'}
    assert {r[2] for r in csv_rows(f.c.get(f'/api/export/csv?child={f.two}'))} == {'Two'}
    assert len(csv_rows(f.c.get(f'/api/export/csv?child={f.one}&child={f.two}'))) == 2
    assert f.c.get('/api/export/csv?child=abc').status_code == 400
    assert f.c.get('/api/export/csv?child=999999').status_code == 404


def test_csv_export_translates_stored_values(family):
    f = family
    f.meal(f.one, '2026-11-08', [('Zucchina', 'half')])
    row = csv_rows(f.c.get('/api/export/csv', headers={'Accept-Language': 'it'}))[0]
    assert (row[1], row[3], row[5], row[6]) == ('Domenica', 'Pranzo', 'Verdura', 'Metà porzione')


def test_excel_export_filtered_on_every_sheet(family):
    from openpyxl import load_workbook
    f = family
    f.meal(f.one, '2026-11-08', ['Mela'])
    f.meal(f.two, '2026-11-08', ['Pera'])
    r = f.c.get(f'/api/export/excel?child={f.one}')
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.data))
    for name, child_col in (('Diario', 2), ('Dettaglio', 2), ('Introduzioni', 0)):
        assert {row[child_col] for row in wb[name].iter_rows(min_row=2, values_only=True)} == {'One'}, name


def test_json_backup_and_import(family):
    f = family
    f.meal(f.one, '2026-11-08', [('Zucchina', 'taste')], notes='note')
    ok(f.c.post('/api/jars', json={'labels': ['3'], 'location': 'fridge', 'made_on': '2026-11-01', 'foods': [f.food['Carota']]}), 201)
    ok(f.c.put('/api/plan', json={'child_id': f.one, 'frequencies': [{'macro': 'fish', 'min': 2}],
                                  'menu': [{'weekday': 0, 'meal_type': 'lunch', 'notes': '30 g', 'foods': [f.food['Zucchina']]}]}))
    dump = f.c.get('/api/export/json').data
    data = json.loads(dump)
    assert data['app'] == 'eatrack' and len(data['tables']['meals']) == 1 and str(f.one) in data['plans']

    # Later changes are replaced by the import
    f.meal(f.two, '2026-11-09', ['Pera'])
    r = ok(upload(f.c, dump))
    assert r['imported']['meals'] == 1 and r['imported']['children'] == 2
    me = ok(f.c.get('/api/me'))
    one = next(c['id'] for c in me['children'] if c['name'] == 'One')
    m = ok(f.c.get(f'/api/meals?child={one}&from=2026-11-01&to=2026-11-30'))
    assert [(x['name'], x['amount']) for x in m[0]['foods']] == [('Zucchina', 'taste')] and m[0]['notes'] == 'note'
    assert len(ok(f.c.get('/api/jars'))) == 1
    plan = ok(f.c.get(f'/api/plan?child={one}'))
    zucchina = next(x['id'] for x in ok(f.c.get('/api/foods')) if x['name'] == 'Zucchina')
    assert plan['frequencies'][0]['macro'] == 'fish' and plan['menu'][0]['foods'] == [zucchina]
    # A copy of the whole database is saved before importing
    assert any(n.startswith('pre-import-') for n in backups())


def test_import_of_a_backup_made_before_v5(family):
    """Backups exported by older versions use Italian names and values."""
    legacy = {
        'app': 'eatrack', 'versione': 4, 'famiglia': 'Vecchia',
        'categorie': [{'id': 3, 'nome': 'Verdura'}, {'id': 6, 'nome': 'Pesce'}],
        'tabelle': {
            'bambini': [{'id': 10, 'nome': 'Giulia', 'data_nascita': '2026-01-15', 'archiviato': 0}],
            'alimenti': [{'id': 20, 'nome': 'Zucca', 'categoria_id': 3, 'archiviato': 0},
                         {'id': 21, 'nome': 'Orata', 'categoria_id': 6, 'archiviato': 0}],
            'pasti': [{'id': 30, 'bambino_id': 10, 'data': '2026-11-02', 'pasto_tipo': 'Cena', 'note': 'ok', 'reazione': 0}],
            'pasto_alimenti': [{'pasto_id': 30, 'alimento_id': 20, 'quantita': 'Metà porzione'},
                               {'pasto_id': 30, 'alimento_id': 21, 'quantita': 'Rifiutato'}],
            'recipienti': [{'id': 40, 'numero': '5', 'posizione': 'Surgelatore', 'data_creazione': '2026-10-30', 'note': '',
                            'consumato_il': None, 'pasto_id': None}],
            'recipiente_alimenti': [{'recipiente_id': 40, 'alimento_id': 20}],
        },
        'piani': {'10': {'frequenze': [{'macro': 'Pesce', 'minimo': 2, 'massimo': None}],
                         'menu': [{'giorno': 2, 'pasto_tipo': 'Pranzo', 'note': 'n', 'alimenti': [21]}]}},
    }
    f = family
    ok(upload(f.c, json.dumps(legacy).encode()))
    me = ok(f.c.get('/api/me'))
    assert [c['name'] for c in me['children']] == ['Giulia']
    child = me['children'][0]['id']
    m = ok(f.c.get(f'/api/meals?child={child}&from=2026-11-02&to=2026-11-02'))[0]
    assert m['meal_type'] == 'dinner' and {(x['name'], x['amount']) for x in m['foods']} == {('Zucca', 'half'), ('Orata', 'refused')}
    jar = ok(f.c.get('/api/jars'))[0]
    assert (jar['label'], jar['location'], [x['name'] for x in jar['foods']]) == ('5', 'freezer', ['Zucca'])
    categories = {c['id']: c['key'] for c in ok(f.c.get('/api/categories'))}
    assert {x['name']: categories[x['category_id']] for x in ok(f.c.get('/api/foods'))} == {'Zucca': 'vegetables', 'Orata': 'fish'}
    plan = ok(f.c.get(f'/api/plan?child={child}'))
    orata = next(x['id'] for x in ok(f.c.get('/api/foods')) if x['name'] == 'Orata')
    assert plan == {'frequencies': [{'macro': 'fish', 'min': 2, 'max': None}],
                    'menu': [{'weekday': 2, 'meal_type': 'lunch', 'notes': 'n', 'foods': [orata]}]}


def test_import_rejects_invalid_files(family):
    f = family
    assert upload(f.c, b'{}', 'b.txt').status_code == 400
    assert upload(f.c, b'not json').status_code == 400
    assert upload(f.c, json.dumps({'app': 'other'}).encode()).status_code == 400
    assert upload(f.c, json.dumps({'app': 'eatrack', 'tables': {'meals': 'x'}}).encode()).status_code == 400
    assert len(ok(f.c.get('/api/me'))['children']) == 2  # nothing changed


def count_meals(*children):
    conn = db.connect()
    try:
        return [conn.execute('SELECT COUNT(*) FROM meals WHERE child_id = ?', (c,)).fetchone()[0] for c in children]
    finally:
        conn.close()


def test_delete_only_the_meals_of_a_child(family):
    f = family
    for day in ('2026-11-01', '2026-11-02'):
        f.meal(f.one, day, ['Mela'])
        f.meal(f.two, day, ['Pera'])
    ok(f.c.put('/api/plan', json={'child_id': f.one, 'frequencies': [{'macro': 'fish', 'min': 2}]}))
    r = ok(f.c.post('/api/children/delete-data', json={'ids': [f.one]}))
    assert (r['children'], r['meals']) == (1, 2)
    assert count_meals(f.one, f.two) == [0, 2]
    assert len(ok(f.c.get('/api/me'))['children']) == 2  # the profile stays
    assert ok(f.c.get(f'/api/plan?child={f.one}'))['frequencies']  # and so does the plan
    assert any(n.startswith('pre-delete-') for n in backups())


def test_delete_children_and_meals(family):
    f = family
    f.meal(f.one, '2026-11-01', ['Mela'])
    f.meal(f.two, '2026-11-01', ['Pera'])
    ok(f.c.post('/api/children/delete-data', json={'ids': [f.one, f.two], 'profile': True}))
    assert ok(f.c.get('/api/me'))['children'] == []
    assert count_meals(f.one, f.two) == [0, 0]


def test_delete_data_invalid_request(family):
    f = family
    assert f.c.post('/api/children/delete-data', json={'ids': []}).status_code == 400
    assert f.c.post('/api/children/delete-data', json={}).status_code == 400
    f.meal(f.one, '2026-11-01', ['Mela'])
    assert f.c.post('/api/children/delete-data', json={'ids': [f.one, 999999]}).status_code == 404
    assert count_meals(f.one) == [1]  # a request with one wrong id deletes nothing


def test_export_labels_in_every_language(family):
    f = family
    f.meal(f.one, '2026-11-08', [('Zucchina', 'half')])
    expected = {'en': ('Sunday', 'Lunch', 'Half portion'), 'es': ('Domingo', 'Comida', 'Media ración'),
                'pt': ('Domingo', 'Almoço', 'Meia dose'), 'fr': ('Dimanche', 'Déjeuner', 'Demi-portion'),
                'de': ('Sonntag', 'Mittagessen', 'Halbe Portion')}
    for lang, (day, meal, amount) in expected.items():
        ok(f.c.put('/api/account', json={'language': lang}))
        row = csv_rows(f.c.get('/api/export/csv'))[0]
        assert (row[1], row[3], row[6]) == (day, meal, amount), lang
