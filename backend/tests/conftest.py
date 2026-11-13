"""Shared fixtures: every test gets a fresh database in a temporary directory, emails are captured
instead of being sent and rate limits start from zero."""
import os
import re
import sys
import tempfile

# Modules read EATRACK_DATA on import: point it at a throwaway directory right away,
# so no test can ever touch backend/data or a real data directory.
os.environ['EATRACK_DATA'] = tempfile.mkdtemp(prefix='eatrack-test-')
for k in [k for k in os.environ if k.startswith('EATRACK_') and k != 'EATRACK_DATA']:
    del os.environ[k]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import auth  # noqa: E402
from famkit import backup  # noqa: E402
import db  # noqa: E402
from famkit import mail  # noqa: E402
from famkit import oidc  # noqa: E402
from app import create_app  # noqa: E402

PASSWORD = 'secret123'


@pytest.fixture
def outbox(monkeypatch):
    """Emails "sent" during the test: list of (to, subject, body)."""
    sent = []
    monkeypatch.setattr(mail, 'send', lambda to, subject, body: sent.append((to, subject, body)))
    return sent


@pytest.fixture
def app(tmp_path, monkeypatch, outbox):
    monkeypatch.setattr(db, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'eatrack.db'))
    monkeypatch.setattr(backup, 'BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setattr(auth, 'SIGNUP_OPEN', True)
    monkeypatch.setattr(oidc, 'PROVIDERS', {})
    auth._attempts.clear()
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client


def ok(r, code=200):
    """Check the status code and return the JSON body."""
    assert r.status_code == code, (r.status_code, r.get_data(as_text=True)[:500])
    return r.get_json()


def sign_up(c, email='fil@example.com', name='Fil', child=None, **extra):
    """Sign up with client `c` (which stays signed in) and return /api/me."""
    ok(c.post('/api/signup', json={'name': name, 'email': email, 'password': PASSWORD, 'consent': True,
                                   'child': child, **extra}), 201)
    return ok(c.get('/api/me'))


def emailed_token(outbox, to, kind):
    """Token of the latest #/<kind>/<token> link sent to `to`."""
    for dest, _, body in reversed(outbox):
        if dest == to and (m := re.search(r'#/' + kind + r'/(\S+)', body)):
            return m.group(1)
    return None


def invite_token(c):
    return ok(c.post('/api/family/invites'), 201)['link'].split('#/invite/')[1]


class Family:
    """An admin with two children ("One" and "Two") and the Italian starter catalog."""

    def __init__(self, c):
        self.c = c
        self.me = sign_up(c, child='One', language='it')
        self.one = self.me['children'][0]['id']
        self.two = ok(c.post('/api/children', json={'name': 'Two'}), 201)['id']
        self.food = {f['name']: f['id'] for f in ok(c.get('/api/foods'))}

    def meal(self, child, date, items, meal_type='lunch', **extra):
        """items: food names or (name, amount) pairs."""
        items = [(i, 'full') if isinstance(i, str) else i for i in items]
        return ok(self.c.post('/api/meals', json={'child_id': child, 'date': date, 'meal_type': meal_type,
                                                  'foods': [{'id': self.food[n], 'amount': a} for n, a in items],
                                                  **extra}), 201)['id']


@pytest.fixture
def family(client):
    return Family(client())
