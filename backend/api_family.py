"""API: family, members, invitations and children."""
from flask import Blueprint, abort, g, jsonify, session

from famkit import backup
import db
from famkit import hub
import i18n
from auth import app_link, create_token, rate_limit, read_token, require_admin, use_token
from common import body, family_child, placeholders, text, valid_date

bp = Blueprint('family', __name__)


@bp.get('/family')
def family():
    with db.transaction() as conn:
        f = conn.execute('SELECT id, name, created_at FROM families WHERE id = ?', (g.family_id,)).fetchone()
        members = [dict(r) for r in conn.execute('''SELECT u.id, u.name, u.email, m.role FROM members m JOIN users u ON u.id = m.user_id
                                                    WHERE m.family_id = ? ORDER BY m.created_at''', (g.family_id,))]
    for m in members:
        m['me'] = m['id'] == g.user['id']
    return jsonify(**dict(f), members=members, role=g.role)


@bp.put('/family')
def rename():
    hub.guard()
    require_admin()
    name = text(body().get('name'), 80)
    if not name:
        abort(400, 'Name is required')
    with db.transaction() as conn:
        conn.execute('UPDATE families SET name = ? WHERE id = ?', (name, g.family_id))
    return jsonify(ok=True)


@bp.post('/family/switch')
def switch():
    try:
        family_id = int(body().get('family_id'))
    except (TypeError, ValueError):
        abort(400, 'invalid family_id')
    if not any(f['id'] == family_id for f in g.families):
        abort(404, 'Family not found')
    session['family_id'] = family_id
    return jsonify(ok=True)


@bp.post('/family/invites')
def create_invite():
    """Invitation link, valid for 7 days and usable once."""
    hub.guard()
    require_admin()
    rate_limit(f'invite:{g.user["id"]}', 20, 3600)
    with db.transaction() as conn:
        token, expires = create_token(conn, 'invite', 24 * 7, user_id=g.user['id'], family_id=g.family_id)
    return jsonify(link=app_link('invite/' + token), expires_at=expires), 201


@bp.delete('/family/members/<int:uid>')
def remove_member(uid):
    """An admin can remove a member; anyone can leave (uid = their own id)."""
    hub.guard()
    if uid != g.user['id']:
        require_admin()
    with db.transaction() as conn:
        members = conn.execute('SELECT user_id, role FROM members WHERE family_id = ? ORDER BY created_at', (g.family_id,)).fetchall()
        if not any(m['user_id'] == uid for m in members):
            abort(404, 'Member not found')
        others = [m for m in members if m['user_id'] != uid]
        if not others:
            abort(400, "You're the only member: to delete the family, delete your account")
        conn.execute('DELETE FROM members WHERE family_id = ? AND user_id = ?', (g.family_id, uid))
        if not any(m['role'] == 'admin' for m in others):
            conn.execute("UPDATE members SET role = 'admin' WHERE family_id = ? AND user_id = ?", (g.family_id, others[0]['user_id']))
        # Whoever leaves their only family gets a new, empty one
        if uid == g.user['id'] and len(g.families) == 1:
            family_id = db.create_family(conn, i18n.tr("{name}'s family", name=g.user['name']), g.user['language'])
            conn.execute("INSERT INTO members (family_id, user_id, role) VALUES (?, ?, 'admin')", (family_id, uid))
            session['family_id'] = family_id
    return jsonify(ok=True)


# ---------- Invitations (public: they can be opened without an account) ----------

@bp.get('/invites/<token>')
def invite_info(token):
    rate_limit(f'invite-info:{token[:12]}', 30, 3600)
    with db.transaction() as conn:
        t = read_token(conn, token, 'invite')
        if not t:
            abort(404, 'Invalid or expired invitation')
        f = conn.execute('SELECT name FROM families WHERE id = ?', (t['family_id'],)).fetchone()
        sender = conn.execute('SELECT name FROM users WHERE id = ?', (t['user_id'],)).fetchone()
    already_member = any(x['id'] == t['family_id'] for x in getattr(g, 'families', []) or [])
    return jsonify(family=f['name'], invited_by=sender['name'] if sender else None, already_member=already_member)


@bp.post('/invites/<token>/accept')
def accept_invite(token):
    hub.guard()
    if not getattr(g, 'user', None):
        abort(401, 'Sign in or sign up to accept')
    with db.transaction() as conn:
        t = read_token(conn, token, 'invite')
        if not t:
            abort(404, 'Invalid or expired invitation')
        conn.execute("INSERT OR IGNORE INTO members (family_id, user_id, role) VALUES (?, ?, 'member')",
                     (t['family_id'], g.user['id']))
        use_token(conn, token)
    session['family_id'] = t['family_id']
    return jsonify(ok=True)


# ---------- Children ----------

def _child_fields(d):
    name = text(d.get('name'), 60)
    if not name:
        abort(400, 'Name is required')
    birth = valid_date(d['birth_date'], 'birth date') if d.get('birth_date') else None
    return name, birth


@bp.post('/children')
def create_child():
    hub.guard()
    name, birth = _child_fields(body())
    with db.transaction() as conn:
        child_id = conn.execute('INSERT INTO children (family_id, name, birth_date) VALUES (?,?,?)',
                                (g.family_id, name, birth)).lastrowid
    return jsonify(id=child_id), 201


@bp.put('/children/<int:child_id>')
def update_child(child_id):
    d = body()
    if hub.enabled():
        # Name and birth date come from weHub; archiving (weaning over) is eaTrack's own
        with db.transaction() as conn:
            if conn.execute('UPDATE children SET archived = ? WHERE id = ? AND family_id = ?',
                            (1 if d.get('archived') else 0, child_id, g.family_id)).rowcount == 0:
                abort(404, 'Child not found')
        return jsonify(ok=True)
    name, birth = _child_fields(d)
    with db.transaction() as conn:
        cur = conn.execute('UPDATE children SET name = ?, birth_date = ?, archived = ? WHERE id = ? AND family_id = ?',
                           (name, birth, 1 if d.get('archived') else 0, child_id, g.family_id))
        if cur.rowcount == 0:
            abort(404, 'Child not found')
    return jsonify(ok=True)


@bp.delete('/children/<int:child_id>')
def delete_child(child_id):
    """Delete the profile and ALL its meals (admin only)."""
    hub.guard()
    require_admin()
    with db.transaction() as conn:
        if conn.execute('DELETE FROM children WHERE id = ? AND family_id = ?', (child_id, g.family_id)).rowcount == 0:
            abort(404, 'Child not found')
    return jsonify(ok=True)


@bp.post('/children/delete-data')
def delete_children_data():
    """Delete the meals of one or more children; with profile=true the profiles too (admin only)."""
    require_admin()
    d = body()
    ids = d.get('ids')
    if not isinstance(ids, list) or not ids:
        abort(400, 'Choose at least one child')
    if d.get('profile'):
        hub.guard()  # profiles come from weHub; deleting meals stays possible
    backup.create_backup('pre-delete')  # server-side safety copy of the whole database
    with db.transaction() as conn:
        ids = sorted({family_child(conn, v) for v in ids})
        meals = conn.execute(f'SELECT COUNT(*) FROM meals WHERE child_id IN ({placeholders(ids)})', ids).fetchone()[0]
        if d.get('profile'):
            conn.execute(f'DELETE FROM children WHERE family_id = ? AND id IN ({placeholders(ids)})', (g.family_id, *ids))
        else:
            conn.execute(f'DELETE FROM meals WHERE child_id IN ({placeholders(ids)})', ids)
    return jsonify(ok=True, children=len(ids), meals=meals)
