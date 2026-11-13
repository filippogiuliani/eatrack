"""The pediatrician's weekly plan: frequencies per category and a menu per weekday."""
import db
from conftest import ok

EMPTY = {'frequencies': [], 'menu': []}


def save(f, child, **plan):
    return f.c.put('/api/plan', json={'child_id': child, **plan})


def test_empty_plan_and_saving(family):
    f = family
    assert ok(f.c.get(f'/api/plan?child={f.one}')) == EMPTY
    p = ok(save(f, f.one,
                frequencies=[{'macro': 'fish', 'min': 2, 'max': 3}, {'macro': 'meat', 'min': None, 'max': ''},
                             {'macro': 'eggs', 'max': '1'}],
                menu=[{'weekday': 0, 'meal_type': 'lunch', 'notes': '30 g', 'foods': [f.food['Zucchina'], f.food['Platessa']]},
                      {'weekday': 1, 'meal_type': 'dinner', 'notes': '  ', 'foods': []}]))
    # Empty entries are dropped
    assert {x['macro']: (x['min'], x['max']) for x in p['frequencies']} == {'fish': (2, 3), 'eggs': (None, 1)}
    assert p['menu'] == [{'weekday': 0, 'meal_type': 'lunch', 'notes': '30 g', 'foods': [f.food['Zucchina'], f.food['Platessa']]}]
    assert ok(f.c.get(f'/api/plan?child={f.one}')) == p
    assert ok(f.c.get(f'/api/plan?child={f.two}')) == EMPTY  # each child has their own


def test_invalid_plan_changes_nothing(family):
    f = family
    before = ok(save(f, f.one, frequencies=[{'macro': 'fish', 'min': 2}]))
    invalid = [
        {'frequencies': [{'macro': 'fish', 'min': 4, 'max': 3}]},
        {'frequencies': [{'macro': 'unknown', 'min': 1}]},
        {'frequencies': [{'macro': 'fish', 'min': -1}]},
        {'frequencies': [{'macro': 'fish', 'min': 'three'}]},
        {'frequencies': 'x'},
        {'menu': [{'weekday': 7, 'meal_type': 'lunch', 'foods': [f.food['Mela']]}]},
        {'menu': [{'weekday': 0, 'meal_type': 'brunch', 'foods': [f.food['Mela']]}]},
        {'menu': [{'weekday': 0, 'meal_type': 'lunch', 'foods': [999999]}]},
    ]
    for d in invalid:
        assert save(f, f.one, **d).status_code == 400, d
    assert ok(f.c.get(f'/api/plan?child={f.one}')) == before


def test_week_progress(family):
    f = family
    ok(save(f, f.one, frequencies=[{'macro': 'fish', 'min': 2, 'max': 3}, {'macro': 'eggs', 'max': 1},
                                   {'macro': 'legumes', 'min': 2}]))
    f.meal(f.one, '2026-11-08', ['Platessa'])                         # Sunday of the week before: excluded
    f.meal(f.one, '2026-11-09', ['Platessa'])                         # Monday
    f.meal(f.one, '2026-11-10', [('Nasello', 'refused')])             # refused: doesn't count
    f.meal(f.one, '2026-11-11', ['Platessa', 'Nasello'])              # two fish in the same meal: counts once
    f.meal(f.one, '2026-11-12', [('Uovo intero', 'taste')])
    f.meal(f.one, '2026-11-13', ['Uovo intero'], meal_type='dinner')
    f.meal(f.one, '2026-11-15', ['Platessa'], meal_type='dinner')     # Sunday: included
    f.meal(f.one, '2026-11-16', ['Platessa'])                         # next Monday: excluded
    f.meal(f.two, '2026-11-12', ['Platessa'])                         # another child: excluded
    w = ok(f.c.get(f'/api/plan/week?child={f.one}&date=2026-11-12'))
    assert (w['start'], w['end']) == ('2026-11-09', '2026-11-15')
    assert {x['macro']: x['times'] for x in w['frequencies']} == {'fish': 3, 'eggs': 2, 'legumes': 0}


def test_week_without_frequencies(family):
    assert ok(family.c.get(f'/api/plan/week?child={family.one}&date=2026-11-12'))['frequencies'] == []


def test_copy_plan_between_siblings(family):
    f = family
    p = ok(save(f, f.one, frequencies=[{'macro': 'fish', 'min': 2}],
                menu=[{'weekday': 3, 'meal_type': 'dinner', 'notes': '', 'foods': [f.food['Pollo']]}]))
    ok(save(f, f.two, frequencies=[{'macro': 'meat', 'min': 5}]))
    assert ok(f.c.post('/api/plan/copy', json={'from': f.one, 'to': f.two})) == p  # replaces the existing one
    assert f.c.post('/api/plan/copy', json={'from': f.one, 'to': f.one}).status_code == 400


def test_plan_deleted_with_the_child(family):
    f = family
    ok(save(f, f.two, menu=[{'weekday': 0, 'meal_type': 'lunch', 'foods': [f.food['Mela']]}]))
    ok(f.c.delete(f'/api/children/{f.two}'))
    conn = db.connect()
    try:
        assert conn.execute('SELECT COUNT(*) FROM plan_meals WHERE child_id = ?', (f.two,)).fetchone()[0] == 0
    finally:
        conn.close()


def test_paediatrician_plans_from_patrack(family, monkeypatch):
    """weHub mode: the child's plans archived in paTrack, asked through weHub; nothing for someone without paTrack."""
    import requests

    import db
    from famkit import hub
    c = family.c
    assert ok(c.get(f'/api/plan/documents?child={family.one}')) == {'available': False, 'documents': []}   # no weHub
    monkeypatch.setattr(hub, 'URL', 'http://wehub.test')
    monkeypatch.setattr(hub, 'KEY', 'k' * 40)
    with db.transaction() as conn:
        conn.execute('UPDATE families SET hub_id = 7')
        conn.execute('UPDATE users SET hub_id = 10')
        conn.execute('UPDATE children SET hub_id = 102 WHERE id = ?', (family.one,))
    calls, answer = [], {'code': 200, 'body': [{'id': 3, 'title': 'Piano', 'doc_date': '2026-11-10', 'excerpt': 'zucchine',
                                                  'url': 'https://pa/#/doc/3', 'ocr_text': 'not passed on'}]}

    def fake(method, url, params=None, **kw):
        calls.append((method, url, params))
        r = requests.Response()
        r.status_code, r._content = answer['code'], __import__('json').dumps(answer['body']).encode()
        return r
    monkeypatch.setattr(requests, 'request', fake)
    r = ok(c.get(f'/api/plan/documents?child={family.one}'))
    assert r['available'] and [d['id'] for d in r['documents']] == [3] and 'ocr_text' not in r['documents'][0]
    assert calls[-1] == ('GET', 'http://wehub.test/api/service/apps/patrack/families/7/plans?child=102', {'user': 10})
    assert ok(c.get(f'/api/plan/documents?child={family.two}')) == {'available': False, 'documents': []}  # not from weHub
    answer.update(code=403, body={'error': 'You do not use paTrack in this family'})
    assert ok(c.get(f'/api/plan/documents?child={family.one}')) == {'available': False, 'documents': []}
    answer.update(code=502, body={'error': 'paTrack is not reachable'})
    r = ok(c.get(f'/api/plan/documents?child={family.one}'))
    assert r['available'] and r['documents'] == [] and r['error'] == 'paTrack non è raggiungibile'
