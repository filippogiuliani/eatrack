"""Sign-up, sign-in, email verification, password recovery and protections."""
import auth
from conftest import PASSWORD, emailed_token, invite_token, ok, sign_up


def test_api_requires_sign_in(client):
    c = client()
    assert c.get('/api/foods').status_code == 401
    assert ok(c.get('/api/me'))['authenticated'] is False


def test_sign_up_validates_input(client):
    c = client()
    base = {'name': 'X', 'email': 'x@example.com', 'password': PASSWORD, 'consent': True}
    assert c.post('/api/signup', json={**base, 'password': 'short'}).status_code == 400
    assert c.post('/api/signup', json={**base, 'email': 'not-an-email'}).status_code == 400
    assert c.post('/api/signup', json={**base, 'consent': False}).status_code == 400
    assert c.post('/api/signup', json={**base, 'name': ''}).status_code == 400
    ok(c.post('/api/signup', json=base), 201)
    assert client().post('/api/signup', json=base).status_code == 409


def test_sign_up_creates_family_admin_and_child(client):
    me = sign_up(client(), child='Leo')
    assert me['authenticated'] and me['family']['role'] == 'admin'
    assert [c['name'] for c in me['children']] == ['Leo']
    assert not me['user']['email_verified']


def test_login(client):
    sign_up(client())
    c = client()
    assert c.post('/api/login', json={'email': 'fil@example.com', 'password': 'wrong'}).status_code == 401
    assert c.post('/api/login', json={'email': 'nobody@example.com', 'password': PASSWORD}).status_code == 401
    ok(c.post('/api/login', json={'email': 'FIL@example.com', 'password': PASSWORD}))  # email is case-insensitive
    assert ok(c.get('/api/me'))['authenticated']
    ok(c.post('/api/logout'))
    assert ok(c.get('/api/me'))['authenticated'] is False


def test_email_verification_is_single_use(client, outbox):
    c = client()
    sign_up(c)
    token = emailed_token(outbox, 'fil@example.com', 'verify')
    assert token
    ok(c.post('/api/verify-email', json={'token': token}))
    assert ok(c.get('/api/me'))['user']['email_verified']
    assert c.post('/api/verify-email', json={'token': token}).status_code == 400


def test_password_reset_closes_other_sessions(client, outbox):
    old = client()
    sign_up(old)
    anon = client()
    ok(anon.post('/api/forgot-password', json={'email': 'fil@example.com'}))
    ok(anon.post('/api/forgot-password', json={'email': 'nobody@example.com'}))  # does not reveal who is registered
    token = emailed_token(outbox, 'fil@example.com', 'reset')
    ok(anon.post('/api/reset-password', json={'token': token, 'password': 'newpass123'}))
    assert ok(old.get('/api/me'))['authenticated'] is False
    assert client().post('/api/login', json={'email': 'fil@example.com', 'password': PASSWORD}).status_code == 401
    ok(client().post('/api/login', json={'email': 'fil@example.com', 'password': 'newpass123'}))
    assert anon.post('/api/reset-password', json={'token': token, 'password': 'another123'}).status_code == 400


def test_change_password(client):
    c = client()
    sign_up(c)
    assert c.post('/api/account/password', json={'current': 'wrong', 'new': 'newpass123'}).status_code == 403
    ok(c.post('/api/account/password', json={'current': PASSWORD, 'new': 'newpass123'}))
    ok(client().post('/api/login', json={'email': 'fil@example.com', 'password': 'newpass123'}))


def test_login_rate_limit(client):
    sign_up(client())
    c = client()
    codes = [c.post('/api/login', json={'email': 'fil@example.com', 'password': 'x'}).status_code for _ in range(12)]
    assert 429 in codes


def test_csrf_foreign_origin_is_blocked(client):
    c = client()
    sign_up(c)
    assert c.post('/api/logout', headers={'Origin': 'https://evil.example'}).status_code == 403
    ok(c.post('/api/logout', headers={'Origin': 'http://localhost'}))


def test_closed_sign_up_requires_invitation(client, monkeypatch):
    admin = client()
    sign_up(admin)
    monkeypatch.setattr(auth, 'SIGNUP_OPEN', False)
    assert ok(client().get('/api/me'))['signup_open'] is False
    base = {'name': 'X', 'email': 'x@example.com', 'password': PASSWORD, 'consent': True}
    assert client().post('/api/signup', json=base).status_code == 403
    new = client()
    ok(new.post('/api/signup', json={**base, 'invite': invite_token(admin)}), 201)
    assert ok(new.get('/api/me'))['family']['role'] == 'member'


def test_delete_account(client):
    c = client()
    sign_up(c)
    assert c.delete('/api/account', json={'password': 'wrong'}).status_code == 403
    ok(c.delete('/api/account', json={'password': PASSWORD}))
    assert client().post('/api/login', json={'email': 'fil@example.com', 'password': PASSWORD}).status_code == 401


def test_messages_follow_the_language(client):
    c = client()
    r = c.post('/api/signup', json={'name': 'J', 'email': 'j@example.com', 'password': 'short', 'consent': True},
               headers={'Accept-Language': 'it-IT,it;q=0.9'})
    assert r.status_code == 400 and r.get_json()['error'] == 'La password deve avere almeno 8 caratteri'
    sign_up(c, email='j@example.com', language='en', child='Mia')
    assert c.get('/api/meals?child=999999&from=2026-01-01&to=2026-01-02').get_json()['error'] == 'Child not found'
    ok(c.put('/api/account', json={'language': 'it'}))
    assert c.get('/api/meals?child=999999&from=2026-01-01&to=2026-01-02').get_json()['error'] == 'Bambino non trovato'
    # Field names inside messages are translated too
    assert c.post('/api/children', json={'name': 'X', 'birth_date': 'ieri'}).get_json()['error'] == 'data di nascita: data non valida'


def test_new_family_gets_catalog_in_its_language(client):
    it = client()
    sign_up(it, language='it')
    assert 'Zucchina' in {f['name'] for f in ok(it.get('/api/foods'))}
    en = client()
    sign_up(en, email='en@example.com', language='en')
    assert 'Zucchini' in {f['name'] for f in ok(en.get('/api/foods'))}


def test_new_languages_messages_and_catalog(client):
    expected = {'es': ('Niño no encontrado', 'Calabacín'), 'pt': ('Criança não encontrada', 'Curgete'),
                'fr': ('Enfant introuvable', 'Courgette'), 'de': ('Kind nicht gefunden', 'Zucchini')}
    for i, (lang, (error, food)) in enumerate(expected.items()):
        c = client()
        sign_up(c, email=f'{lang}{i}@example.com', language=lang)
        assert c.get('/api/meals?child=999999&from=2026-01-01&to=2026-01-02').get_json()['error'] == error
        assert food in {f['name'] for f in ok(c.get('/api/foods'))}
    # Unauthenticated requests follow the browser language
    r = client().post('/api/signup', json={'name': 'X', 'email': 'x@example.com', 'password': 'short', 'consent': True},
                      headers={'Accept-Language': 'de-DE,de;q=0.9'})
    assert r.get_json()['error'] == 'Das Passwort muss mindestens 8 Zeichen lang sein'


def test_default_language_is_english_and_browser_language_is_detected(client):
    # No preference from the browser: English
    r = client().post('/api/signup', json={'name': 'X', 'email': 'x@example.com', 'password': 'short', 'consent': True})
    assert r.get_json()['error'] == 'Password must be at least 8 characters'
    # Regional browser language (e.g. Brazilian Portuguese) falls back to the base language
    r = client().post('/api/signup', json={'name': 'X', 'email': 'x@example.com', 'password': 'short', 'consent': True},
                      headers={'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5'})
    assert r.get_json()['error'] == 'A palavra-passe deve ter pelo menos 8 caracteres'
    # Unsupported language: English
    r = client().post('/api/signup', json={'name': 'X', 'email': 'x@example.com', 'password': 'short', 'consent': True},
                      headers={'Accept-Language': 'ja-JP,ja;q=0.9'})
    assert r.get_json()['error'] == 'Password must be at least 8 characters'
    # Account created without an explicit language and without browser hints: English catalog
    c = client()
    sign_up(c, email='nolang@example.com')
    assert ok(c.get('/api/me'))['user']['language'] == 'en'
    assert 'Zucchini' in {f['name'] for f in ok(c.get('/api/foods'))}
