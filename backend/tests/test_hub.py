"""weHub mode for eaTrack: members and children come from weHub (simulated here); meals are never lost."""
import pytest
from flask import redirect

import auth
import db
import hub
import oidc
from conftest import PASSWORD, ok, sign_up

KEY = 'k' * 40


class FakeHub:
    """Stands in for weHub's service API."""

    def __init__(self):
        self.users = {}       # (issuer, subject) or email → user
        self.families = {}    # hub id → snapshot
        self.access = {}      # user hub id → [family hub ids]
        self.down = False

    def __call__(self, method, path, payload=None):
        if self.down:
            raise hub.Unavailable('down')
        if path == '/whoami':
            u = self.users.get(payload['email'])
            if not u:
                return {'known': False}
            return {'known': True, 'user': u, 'families': [self.families[f] for f in self.access.get(u['hub_id'], [])]}
        fid = int(path.split('/')[2].split('?')[0])
        snap = self.families.get(fid)
        if snap and f"version={snap['version']}" in path:
            return {'unchanged': True}
        return snap


class FakeProvider:
    user = None

    def authorize_redirect(self, url):
        return redirect('https://id.example/auth')

    def authorize_access_token(self):
        return {'userinfo': self.user}


@pytest.fixture
def wehub(app, monkeypatch):
    fake = FakeHub()
    monkeypatch.setattr(hub, 'URL', 'http://wehub.test')
    monkeypatch.setattr(hub, 'KEY', KEY)
    monkeypatch.setattr(hub, '_call', fake)
    monkeypatch.setattr(auth, 'PASSWORD_LOGIN', False)
    provider = FakeProvider()
    monkeypatch.setattr(oidc, 'PROVIDERS', {'pocketid': 'Pocket ID'})
    monkeypatch.setattr(oidc, '_client', lambda pid: provider)
    fake.provider = provider
    return fake


def user(hub_id, name, email):
    return {'hub_id': hub_id, 'name': name, 'email': email, 'language': 'it'}


def family(fake, hub_id=1, version=1, members=(), people=(), local_id=None, name='Casa'):
    fake.families[hub_id] = {'hub_id': hub_id, 'name': name, 'version': version, 'local_id': local_id,
                             'members': [{**m, 'role': m.get('role', 'member'), 'level': 'full'} for m in members],
                             'people': list(people)}


def sign_in(c, fake, email, sub=None):
    c.get('/api/oidc/pocketid/login')
    fake.provider.user = {'sub': sub or email, 'email': email, 'email_verified': True, 'name': 'X', 'iss': 'https://id.example'}
    r = c.get('/api/oidc/pocketid/callback?code=x&state=y')
    assert r.status_code == 302
    return r.headers['Location'].split('#/', 1)[1]


def test_sign_in_creates_family_and_children(client, wehub):
    fil, sara = user(10, 'Fil', 'fil@example.com'), user(11, 'Sara', 'sara@example.com')
    wehub.users = {'fil@example.com': fil, 'sara@example.com': sara}
    family(wehub, members=[{**fil, 'role': 'admin'}, sara],
           people=[{'hub_id': 100, 'name': 'Fil', 'kind': 'adult', 'user_hub_id': 10},
                   {'hub_id': 102, 'name': 'Luca', 'kind': 'child', 'birth_date': '2025-01-10', 'user_hub_id': None},
                   {'hub_id': 103, 'name': 'Nonna', 'kind': 'adult', 'user_hub_id': None}])
    wehub.access = {10: [1], 11: [1]}
    c = client()
    assert sign_in(c, wehub, 'fil@example.com') == ''
    me = ok(c.get('/api/me'))
    assert me['family']['name'] == 'Casa' and [ch['name'] for ch in me['children']] == ['Luca']
    assert me['children'][0]['birth_date'] == '2025-01-10'
    assert me['hub']['name'] == 'weHub' and me['password_login'] is False
    # The family's foods were created as for any new family
    assert ok(c.get('/api/foods'))
    luca = me['children'][0]['id']
    # Name and birth date come from weHub; archiving stays here
    ok(c.put(f'/api/children/{luca}', json={'name': 'Altro', 'archived': True}))
    me = ok(c.get('/api/me'))
    assert me['children'][0]['name'] == 'Luca' and me['children'][0]['archived']
    assert c.post('/api/children', json={'name': 'X'}).status_code == 409
    assert c.delete(f'/api/children/{luca}').status_code == 409
    assert c.post('/api/children/delete-data', json={'ids': [luca], 'profile': True}).status_code == 409
    assert c.post('/api/family/invites').status_code == 409
    assert c.post('/api/login', json={'email': 'fil@example.com', 'password': PASSWORD}).status_code == 403


def test_existing_child_and_meals_are_kept(client, wehub, monkeypatch):
    monkeypatch.setattr(hub, 'URL', '')
    monkeypatch.setattr(auth, 'PASSWORD_LOGIN', True)
    c = client()
    local = sign_up(c, child='Lucas', birth_date='2025-01-10')
    child = local['children'][0]['id']
    food = ok(c.get('/api/foods'))[0]['id']
    ok(c.post('/api/meals', json={'child_id': child, 'date': '2026-03-01', 'meal_type': 'lunch',
                                  'foods': [{'id': food, 'amount': 'full'}]}), 201)
    monkeypatch.setattr(hub, 'URL', 'http://wehub.test')
    monkeypatch.setattr(auth, 'PASSWORD_LOGIN', False)
    fil = user(10, 'Fil', 'fil@example.com')
    wehub.users = {'fil@example.com': fil}
    family(wehub, local_id=local['family']['id'], members=[{**fil, 'role': 'admin'}],
           people=[{'hub_id': 102, 'name': 'Luca', 'kind': 'child', 'birth_date': None, 'local_id': child, 'user_hub_id': None}])
    wehub.access = {10: [1]}
    c2 = client()
    sign_in(c2, wehub, 'fil@example.com')
    me = ok(c2.get('/api/me'))
    assert me['family']['id'] == local['family']['id']
    assert me['children'] == [{'id': child, 'name': 'Luca', 'birth_date': '2025-01-10', 'archived': 0}]
    # Removed in weHub: archived, the meals stay
    family(wehub, version=2, local_id=local['family']['id'], members=[{**fil, 'role': 'admin'}], people=[])
    hub.sync_all()
    me = ok(c2.get('/api/me'))
    assert me['children'][0]['archived'] == 1
    with db.transaction() as conn:
        assert conn.execute('SELECT COUNT(*) FROM meals WHERE child_id = ?', (child,)).fetchone()[0] == 1


def test_no_access(client, wehub):
    wehub.users = {'tata@example.com': user(12, 'Tata', 'tata@example.com')}
    assert 'login?error=' in sign_in(client(), wehub, 'tata@example.com')


def test_export_for_the_import(client, wehub, monkeypatch):
    monkeypatch.setattr(hub, 'URL', '')
    monkeypatch.setattr(auth, 'PASSWORD_LOGIN', True)
    sign_up(client(), child='Luca', birth_date='2025-01-10')
    assert client().get('/api/hub/export').status_code == 401
    f = ok(client().get('/api/hub/export', headers={'Authorization': 'Bearer ' + KEY}))['families'][0]
    assert f['members'][0]['email'] == 'fil@example.com'
    assert f['people'] == [{'local_id': 1, 'name': 'Luca', 'birth_date': '2025-01-10', 'kind': 'child'}]
