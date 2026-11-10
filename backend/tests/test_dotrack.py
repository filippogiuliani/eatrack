"""Link with doTrack: the weekly menu's foods go to a doTrack shopping list (doTrack's API is simulated)."""
import requests

import api_dotrack
from conftest import PASSWORD, invite_token, ok


class FakeDoTrack:
    """Answers like doTrack's API: /api/lists and /api/lists/<id>/items."""

    def __init__(self):
        self.calls = []
        self.token = 'dt_good'
        self.down = False

    def __call__(self, method, url, json=None, headers=None, **kw):
        self.calls.append((method, url, json, headers))
        if self.down:
            raise requests.ConnectionError()
        r = requests.Response()
        r.headers['Content-Type'] = 'application/json'
        if headers['Authorization'] != 'Bearer ' + self.token:
            r.status_code, r._content = 401, b'{"error": "Sign-in required"}'
        elif url.endswith('/api/lists'):
            r.status_code = 200
            r._content = (b'[{"id": 3, "name": "Spesa", "kind": "checklist", "archived": false, "template": false},'
                          b' {"id": 4, "name": "Bagno", "kind": "project", "archived": false, "template": false}]')
        elif url.endswith('/api/lists/3/items'):
            r.status_code = 201
            r._content = b'{"added": [{"id": 1}, {"id": 2}], "skipped": ["Mela"]}'
        else:
            r.status_code, r._content = 404, b'{}'
        return r


def test_connect_and_send(family, client, monkeypatch):
    fake = FakeDoTrack()
    monkeypatch.setattr(api_dotrack.requests, 'request', fake)
    c = family.c
    assert ok(c.get('/api/integrations/dotrack')) == {'connected': False}
    assert c.put('/api/integrations/dotrack', json={'url': 'ftp://x', 'token': 'dt_good'}).status_code == 400
    assert c.put('/api/integrations/dotrack', json={'url': 'https://dotrack.example', 'token': 'dt_bad'}).status_code == 502
    r = ok(c.put('/api/integrations/dotrack', json={'url': 'https://dotrack.example/api/', 'token': 'dt_good'}))
    # Only shopping-style lists; the only one is chosen
    assert r['lists'] == [{'id': 3, 'name': 'Spesa'}] and (r['list_id'], r['list_name'], r['url']) == (3, 'Spesa', 'https://dotrack.example')
    status = ok(c.get('/api/integrations/dotrack'))
    assert status['connected'] and 'token' not in status  # the token never goes back to the browser

    sent = ok(c.post('/api/integrations/dotrack/send', json={'items': ['Zucchine', 'Mela', 'Ricotta']}))
    assert sent == {'added': 2, 'skipped': 1, 'list_name': 'Spesa'}
    method, url, payload, headers = fake.calls[-1]
    assert (method, url, payload) == ('POST', 'https://dotrack.example/api/lists/3/items', {'items': ['Zucchine', 'Mela', 'Ricotta']})
    assert headers['Authorization'] == 'Bearer dt_good'
    assert c.post('/api/integrations/dotrack/send', json={'items': []}).status_code == 400
    fake.down = True
    assert c.post('/api/integrations/dotrack/send', json={'items': ['x']}).status_code == 502

    # Only the admin connects; members can send
    member = client()
    ok(member.post('/api/signup', json={'name': 'Sara', 'email': 'sara@example.com', 'password': PASSWORD, 'consent': True,
                                         'invite': invite_token(c)}), 201)
    assert member.put('/api/integrations/dotrack', json={'url': 'https://x.example', 'token': 'dt_good'}).status_code == 403
    assert member.delete('/api/integrations/dotrack').status_code == 403
    ok(c.delete('/api/integrations/dotrack'))
    assert c.post('/api/integrations/dotrack/send', json={'items': ['x']}).status_code == 400
