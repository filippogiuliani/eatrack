"""Diary, foods, pantry (jars) and statistics."""
from conftest import ok


def meals(f, child, start, end=None):
    return ok(f.c.get(f'/api/meals?child={child}&from={start}&to={end or start}'))


def test_meal_create_update_delete(family):
    f = family
    meal_id = f.meal(f.one, '2026-11-08', [('Zucchina', 'taste'), 'Pollo'], notes='ok', reaction=True)
    m = meals(f, f.one, '2026-11-08')[0]
    assert (m['id'], m['notes'], bool(m['reaction'])) == (meal_id, 'ok', True)
    assert {(x['name'], x['amount']) for x in m['foods']} == {('Zucchina', 'taste'), ('Pollo', 'full')}

    ok(f.c.put(f'/api/meals/{meal_id}', json={'child_id': f.one, 'date': '2026-11-09', 'meal_type': 'dinner',
                                              'foods': [{'id': f.food['Carota'], 'amount': 'refused'}]}))
    assert meals(f, f.one, '2026-11-08') == []
    m = meals(f, f.one, '2026-11-09')[0]
    assert m['meal_type'] == 'dinner' and [(x['name'], x['amount']) for x in m['foods']] == [('Carota', 'refused')]

    ok(f.c.delete(f'/api/meals/{meal_id}'))
    assert meals(f, f.one, '2026-11-09') == []


def test_meal_invalid_values(family):
    f = family
    base = {'child_id': f.one, 'date': '2026-11-08', 'meal_type': 'lunch', 'foods': [{'id': f.food['Mela']}]}
    assert f.c.post('/api/meals', json={**base, 'meal_type': 'brunch'}).status_code == 400
    assert f.c.post('/api/meals', json={**base, 'date': '8/11/2026'}).status_code == 400
    assert f.c.post('/api/meals', json={**base, 'foods': [{'id': f.food['Mela'], 'amount': 'lots'}]}).status_code == 400
    assert f.c.post('/api/meals', json={**base, 'foods': [{'id': 999999}]}).status_code == 400
    assert f.c.post('/api/meals', json={**base, 'foods': []}).status_code == 400


def test_meals_are_per_child(family):
    f = family
    f.meal(f.one, '2026-11-08', ['Mela'])
    f.meal(f.two, '2026-11-08', ['Pera'])
    assert [x['name'] for m in meals(f, f.one, '2026-11-08') for x in m['foods']] == ['Mela']
    assert [x['name'] for m in meals(f, f.two, '2026-11-08') for x in m['foods']] == ['Pera']


def test_repeat_a_previous_meal(family):
    f = family
    f.meal(f.one, '2026-11-07', ['Zucchina', 'Pollo'])
    f.meal(f.one, '2026-11-07', ['Mela'], meal_type='snack')
    recent = ok(f.c.get(f'/api/meals/recent?child={f.one}&meal_type=lunch'))
    assert [sorted(x['name'] for x in m['foods']) for m in recent] == [['Pollo', 'Zucchina']]


def test_foods_create_duplicate_archive_delete(family):
    f = family
    category = ok(f.c.get('/api/categories'))[0]['id']
    new = ok(f.c.post('/api/foods', json={'name': 'Avocado', 'category_id': category}), 201)['id']
    assert f.c.post('/api/foods', json={'name': 'avocado', 'category_id': category}).status_code == 409
    assert ok(f.c.delete(f'/api/foods/{new}')).get('deleted')  # never used: really deleted
    f.meal(f.one, '2026-11-08', ['Mela'])
    assert ok(f.c.delete(f"/api/foods/{f.food['Mela']}")).get('archived')  # used: only archived
    assert meals(f, f.one, '2026-11-08')[0]['foods'][0]['name'] == 'Mela'


def test_food_in_a_plan_is_archived_not_deleted(family):
    f = family
    ok(f.c.put('/api/plan', json={'child_id': f.one, 'menu': [{'weekday': 0, 'meal_type': 'lunch', 'foods': [f.food['Pera']]}]}))
    assert ok(f.c.delete(f"/api/foods/{f.food['Pera']}")).get('archived')
    assert ok(f.c.get(f'/api/plan?child={f.one}'))['menu'][0]['foods'] == [f.food['Pera']]


def test_categories_use_stable_keys(family):
    keys = [c['key'] for c in ok(family.c.get('/api/categories'))]
    assert keys[:3] == ['carbs', 'broth', 'vegetables'] and 'white_meat' in keys


def test_jar_used_by_a_meal(family):
    f = family
    ok(f.c.post('/api/jars', json={'labels': ['7'], 'location': 'freezer', 'made_on': '2026-11-01', 'foods': [f.food['Zucca']]}), 201)
    jar_id = ok(f.c.get('/api/jars'))[0]['id']
    meal_id = f.meal(f.one, '2026-11-08', ['Zucca'], jars=[jar_id])
    assert ok(f.c.get('/api/jars')) == []
    assert [j['id'] for j in ok(f.c.get('/api/jars?status=used'))] == [jar_id]
    # The same jar cannot be used twice
    assert f.c.post('/api/meals', json={'child_id': f.one, 'date': '2026-11-08', 'meal_type': 'dinner',
                                        'foods': [], 'jars': [jar_id]}).status_code == 409
    # Deleting the meal puts the jar back in the pantry
    ok(f.c.delete(f'/api/meals/{meal_id}'))
    assert [j['id'] for j in ok(f.c.get('/api/jars'))] == [jar_id]


def test_jars_move_and_validation(family):
    f = family
    ids = ok(f.c.post('/api/jars', json={'labels': ['1', '2', ' '], 'location': 'fridge', 'made_on': '2026-11-01',
                                         'foods': [f.food['Mela']]}), 201)['ids']
    assert len(ids) == 2
    ok(f.c.post(f'/api/jars/{ids[0]}/move', json={'location': 'freezer'}))
    assert {j['id']: j['location'] for j in ok(f.c.get('/api/jars'))} == {ids[0]: 'freezer', ids[1]: 'fridge'}
    assert f.c.post(f'/api/jars/{ids[0]}/move', json={'location': 'cellar'}).status_code == 400
    assert f.c.post('/api/jars', json={'labels': ['3'], 'location': 'fridge', 'made_on': '2026-11-01', 'foods': []}).status_code == 400


def test_stats(family):
    f = family
    f.meal(f.one, '2026-11-07', ['Pollo', 'Zucchina'])
    f.meal(f.one, '2026-11-08', ['Platessa', ('Carota', 'refused')], meal_type='dinner')
    f.meal(f.one, '2026-11-08', ['Mela'], meal_type='snack')
    s = ok(f.c.get(f'/api/stats?child={f.one}&days=7&today=2026-11-08'))
    assert (s['main_meals'], s['snacks'], s['days_logged']) == (2, 1, 2)
    by_macro = {c['macro']: c for c in s['categories']}
    assert by_macro['meat']['main'] == 1 and by_macro['fish']['main'] == 1
    assert by_macro['fruit']['snack'] == 1
    assert [r['name'] for r in s['refused']] == ['Carota']
