"""Families, invitations, roles and above all isolation: nobody can see or change another family's data."""
from conftest import PASSWORD, invite_token, ok, sign_up


def test_families_are_isolated(client, family):
    f = family
    meal_id = f.meal(f.one, '2026-11-08', ['Zucchina'])
    ok(f.c.post('/api/jars', json={'labels': ['1'], 'location': 'fridge', 'made_on': '2026-11-01', 'foods': [f.food['Carota']]}), 201)
    jar_id = ok(f.c.get('/api/jars'))[0]['id']
    food_id = f.food['Zucchina']

    other = client()
    me2 = sign_up(other, email='anna@example.com', name='Anna', child='Leo')
    child2 = me2['children'][0]['id']
    own_food = ok(other.get('/api/foods'))[0]['id']

    attempts = {
        'read meals': other.get(f'/api/meals?child={f.one}&from=2000-01-01&to=2100-01-01'),
        'stats': other.get(f'/api/stats?child={f.one}'),
        'foods with usage': other.get(f'/api/foods?child={f.one}'),
        'read plan': other.get(f'/api/plan?child={f.one}'),
        'write plan': other.put('/api/plan', json={'child_id': f.one, 'frequencies': []}),
        'copy plan': other.post('/api/plan/copy', json={'from': f.one, 'to': child2}),
        'plan week': other.get(f'/api/plan/week?child={f.one}'),
        'update meal': other.put(f'/api/meals/{meal_id}', json={'child_id': child2, 'date': '2026-11-08', 'meal_type': 'lunch', 'foods': []}),
        'delete meal': other.delete(f'/api/meals/{meal_id}'),
        'meal with foreign food': other.post('/api/meals', json={'child_id': child2, 'date': '2026-11-08', 'meal_type': 'lunch', 'foods': [{'id': food_id}]}),
        'meal with foreign jar': other.post('/api/meals', json={'child_id': child2, 'date': '2026-11-08', 'meal_type': 'lunch', 'jars': [jar_id]}),
        'meal for foreign child': other.post('/api/meals', json={'child_id': f.one, 'date': '2026-11-08', 'meal_type': 'lunch', 'foods': [{'id': own_food}]}),
        'update food': other.put(f'/api/foods/{food_id}', json={'name': 'hack', 'category_id': 1}),
        'delete food': other.delete(f'/api/foods/{food_id}'),
        'update jar': other.put(f'/api/jars/{jar_id}', json={'label': 'x', 'location': 'fridge', 'made_on': '2026-11-01', 'foods': [own_food]}),
        'move jar': other.post(f'/api/jars/{jar_id}/move', json={'location': 'freezer'}),
        'delete jar': other.delete(f'/api/jars/{jar_id}'),
        'jar with foreign food': other.post('/api/jars', json={'labels': ['1'], 'location': 'fridge', 'made_on': '2026-11-01', 'foods': [food_id]}),
        'update child': other.put(f'/api/children/{f.one}', json={'name': 'hack'}),
        'delete child': other.delete(f'/api/children/{f.one}'),
        'delete child data': other.post('/api/children/delete-data', json={'ids': [f.one]}),
        'export foreign child': other.get(f'/api/export/csv?child={f.one}'),
        'switch to foreign family': other.post('/api/family/switch', json={'family_id': f.me['family']['id']}),
    }
    passed = {k: r.status_code for k, r in attempts.items() if r.status_code not in (400, 403, 404)}
    assert not passed, f'isolation broken: {passed}'

    # Unfiltered export: only the header, none of the first family's meals
    assert other.get('/api/export/csv').data.decode('utf-8-sig').strip().count('\n') == 0
    # The first family's data is untouched
    assert len(ok(f.c.get(f'/api/meals?child={f.one}&from=2026-11-08&to=2026-11-08'))) == 1
    assert len(ok(f.c.get('/api/jars'))) == 1
    assert [c['name'] for c in ok(f.c.get('/api/me'))['children']] == ['One', 'Two']


def test_invitation_for_new_user_and_roles(client, family):
    f = family
    invite = invite_token(f.c)
    partner = client()
    assert ok(partner.get(f'/api/invites/{invite}'))['family']
    me = sign_up(partner, email='partner@example.com', name='Partner', invite=invite)
    assert me['family']['id'] == f.me['family']['id'] and me['family']['role'] == 'member'
    # Sees and writes the shared diary
    meal_id = ok(partner.post('/api/meals', json={'child_id': f.one, 'date': '2026-11-08', 'meal_type': 'dinner',
                                                   'foods': [{'id': f.food['Carota']}]}), 201)['id']
    meals = ok(f.c.get(f'/api/meals?child={f.one}&from=2026-11-08&to=2026-11-08'))
    assert [m['created_by_name'] for m in meals if m['id'] == meal_id] == ['Partner']
    # Single-use invitation
    assert client().post('/api/signup', json={'name': 'Z', 'email': 'z@example.com', 'password': PASSWORD,
                                              'consent': True, 'invite': invite}).status_code == 400
    # A member cannot do admin operations
    assert partner.post('/api/family/invites').status_code == 403
    assert partner.delete(f'/api/children/{f.one}').status_code == 403
    assert partner.post('/api/children/delete-data', json={'ids': [f.one]}).status_code == 403
    assert partner.post('/api/import', data={}, content_type='multipart/form-data').status_code == 403


def test_existing_user_accepts_invitation_and_is_removed(client, family):
    f = family
    anna = client()
    me_anna = sign_up(anna, email='anna@example.com', name='Anna')
    ok(anna.post(f'/api/invites/{invite_token(f.c)}/accept'))
    me = ok(anna.get('/api/me'))
    assert len(me['families']) == 2 and me['family']['id'] == f.me['family']['id']
    ok(anna.post('/api/family/switch', json={'family_id': me_anna['family']['id']}))
    ok(f.c.delete(f"/api/family/members/{me_anna['user']['id']}"))
    assert anna.post('/api/family/switch', json={'family_id': f.me['family']['id']}).status_code == 404


def test_children_create_update_archive_delete(family):
    f = family
    assert f.c.post('/api/children', json={'name': ''}).status_code == 400
    ok(f.c.put(f'/api/children/{f.two}', json={'name': 'Second', 'birth_date': '2026-03-01', 'archived': True}))
    c = next(x for x in ok(f.c.get('/api/me'))['children'] if x['id'] == f.two)
    assert (c['name'], c['birth_date'], bool(c['archived'])) == ('Second', '2026-03-01', True)
    f.meal(f.two, '2026-11-01', ['Mela'])
    ok(f.c.delete(f'/api/children/{f.two}'))
    assert [x['id'] for x in ok(f.c.get('/api/me'))['children']] == [f.one]
    assert f.c.get(f'/api/meals?child={f.two}&from=2026-11-01&to=2026-11-01').status_code == 404
