"""Link with doTrack (the family organizer): the foods of the weekly menu go to a doTrack shopping list.

The family admin pastes the doTrack address and an API token created in doTrack (Family page → Integrations),
then picks the list. The token stays on this server: the browser never sees it."""
from urllib.parse import urlparse

import requests
from flask import Blueprint, abort, g, jsonify

import db
from auth import require_admin
from common import body, text

bp = Blueprint('dotrack', __name__)
TIMEOUT = 10


def _link(conn):
    return conn.execute('SELECT * FROM dotrack_links WHERE family_id = ?', (g.family_id,)).fetchone()


def _call(url, token, method, path, payload=None):
    """A request to doTrack's API; errors become a 502 with a readable reason."""
    try:
        r = requests.request(method, f"{url}/api{path}", json=payload, timeout=TIMEOUT, allow_redirects=False,
                             headers={'Authorization': f'Bearer {token}', 'User-Agent': 'eaTrack'})
    except requests.RequestException:
        abort(502, 'doTrack is not reachable')
    if r.status_code == 401:
        abort(502, 'doTrack refused the token')
    if r.status_code >= 400:
        abort(502, 'doTrack answered with an error')
    try:
        return r.json()
    except ValueError:
        abort(502, 'doTrack answered with an error')


def _url(value):
    url = text(value, 300).rstrip('/')
    if url.endswith('/api'):
        url = url[:-4]
    p = urlparse(url)
    if p.scheme not in ('http', 'https') or not p.hostname:
        abort(400, 'Invalid address')
    return url


def _lists(url, token):
    return [{'id': x['id'], 'name': x['name']} for x in _call(url, token, 'GET', '/lists')
            if x.get('kind') == 'checklist' and not x.get('archived') and not x.get('template')]


@bp.get('/integrations/dotrack')
def status():
    with db.transaction() as conn:
        link = _link(conn)
    if not link:
        return jsonify(connected=False)
    return jsonify(connected=True, url=link['url'], list_id=link['list_id'], list_name=link['list_name'])


@bp.put('/integrations/dotrack')
def connect():
    """Save address and token (checked against doTrack); returns the shopping lists to choose from."""
    require_admin()
    d = body()
    with db.transaction() as conn:
        current = _link(conn)
    url = _url(d.get('url') or (current['url'] if current else ''))
    token = text(d.get('token'), 200) or (current['token'] if current else '')
    if not token:
        abort(400, 'The doTrack token is required')
    lists = _lists(url, token)
    list_id = d.get('list_id') if d.get('list_id') in [x['id'] for x in lists] else (current['list_id'] if current else None)
    if list_id not in [x['id'] for x in lists]:
        list_id = lists[0]['id'] if len(lists) == 1 else None
    list_name = next((x['name'] for x in lists if x['id'] == list_id), None)
    with db.transaction() as conn:
        conn.execute('''INSERT INTO dotrack_links (family_id, url, token, list_id, list_name) VALUES (?,?,?,?,?)
                        ON CONFLICT(family_id) DO UPDATE SET url = excluded.url, token = excluded.token,
                        list_id = excluded.list_id, list_name = excluded.list_name''', (g.family_id, url, token, list_id, list_name))
    return jsonify(connected=True, url=url, list_id=list_id, list_name=list_name, lists=lists)


@bp.delete('/integrations/dotrack')
def disconnect():
    require_admin()
    with db.transaction() as conn:
        conn.execute('DELETE FROM dotrack_links WHERE family_id = ?', (g.family_id,))
    return jsonify(connected=False)


@bp.post('/integrations/dotrack/send')
def send():
    """items: names of foods → added to the chosen doTrack list (doTrack skips what is already on it)."""
    names = body().get('items')
    if not isinstance(names, list) or not names or len(names) > 200:
        abort(400, 'Nothing to send')
    names = [text(n, 120) for n in names if isinstance(n, str) and text(n, 120)]
    with db.transaction() as conn:
        link = _link(conn)
    if not link or not link['list_id']:
        abort(400, 'Connect doTrack and choose a list first')
    r = _call(link['url'], link['token'], 'POST', f"/lists/{link['list_id']}/items", {'items': names})
    return jsonify(added=len(r.get('added', [])), skipped=len(r.get('skipped', [])), list_name=link['list_name'])
