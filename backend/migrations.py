"""Upgrades from older database layouts and backup formats.

Before v5 the schema, the stored values and the JSON backups used Italian names. Those names
only appear here, as the description of the old format being converted:
- v1/v2: a single family, no users (tables `alimenti`, `pasti`, … without `famiglia_id`);
- v3/v4: multi-family with Italian table and column names (`utenti`, `famiglie`, `bambini`, …).
Everything is converted to the current English schema in db.py. A full copy of the database is
saved by db.init_db() before any upgrade.
"""
import db

# Old stored values -> current keys
MEAL_TYPES = {'Colazione': 'breakfast', 'Pranzo': 'lunch', 'Merenda': 'snack', 'Cena': 'dinner'}
AMOUNTS = {'Porzione intera': 'full', 'Metà porzione': 'half', 'In Passato': 'puree', 'Assaggio': 'taste', 'Rifiutato': 'refused'}
LOCATIONS = {'Frigorifero': 'fridge', 'Surgelatore': 'freezer', 'Dispensa (Secco)': 'pantry'}
CATEGORIES = {'Carboidrati': 'carbs', 'Brodo': 'broth', 'Verdura': 'vegetables', 'Carne Bianca': 'white_meat',
              'Carne Rossa': 'red_meat', 'Pesce': 'fish', 'Legumi': 'legumes', 'Uova': 'eggs', 'Latticini': 'dairy',
              'Frutta': 'fruit', 'Altro': 'other'}
MACROS = {'Carboidrati': 'carbs', 'Brodo': 'broth', 'Verdura': 'vegetables', 'Carne': 'meat', 'Pesce': 'fish',
          'Legumi': 'legumes', 'Uova': 'eggs', 'Latticini': 'dairy', 'Frutta': 'fruit'}
DIARY_GROUPS = {'carboidrati': 'carbs', 'brodo': 'broth', 'verdura': 'vegetables', 'proteine': 'protein', 'frutta': 'fruit'}
ROLES = {'admin': 'admin', 'membro': 'member'}
TOKEN_KINDS = {'verifica': 'verify', 'reset': 'reset', 'invito': 'invite'}


def _map(mapping, value):
    return mapping.get(value, value)


def category_key(old_name):
    return CATEGORIES.get(old_name, old_name)


def needs_upgrade(conn, existing):
    return 'alimenti' in existing or 'utenti' in existing


def upgrade(conn, existing):
    conn.execute('PRAGMA foreign_keys = OFF')
    if 'utenti' in existing:
        _from_italian_multi_family(conn, existing)
    else:
        _from_single_family(conn, existing)
    conn.commit()
    conn.execute('PRAGMA foreign_keys = ON')


def _rows(conn, existing, table):
    return [dict(r) for r in conn.execute(f'SELECT * FROM {table}')] if table in existing else []


def _insert(conn, table, row):
    cols = list(row)
    conn.execute(f'INSERT OR IGNORE INTO {table} ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})',
                 [row[c] for c in cols])


def _drop(conn, existing, names):
    for t in names:
        if t in existing:
            conn.execute(f'DROP TABLE {t}')


def _from_italian_multi_family(conn, existing):
    """v3/v4 -> v5: same data, English names and values. Ids are preserved."""
    old = {t: _rows(conn, existing, t) for t in [
        'categorie', 'famiglie', 'utenti', 'membri', 'identita', 'token', 'bambini', 'alimenti', 'pasti',
        'pasto_alimenti', 'recipienti', 'recipiente_alimenti', 'piano_frequenze', 'piano_menu', 'piano_menu_alimenti']}
    _drop(conn, existing, reversed(list(old)))
    conn.executescript(db.SCHEMA)

    for r in old['categorie']:
        _insert(conn, 'categories', {'id': r['id'], 'key': category_key(r['nome']),
                                     'diary_group': _map(DIARY_GROUPS, r.get('gruppo') or 'proteine'),
                                     'macro': _map(MACROS, r['macro']), 'sort_order': r.get('ordine') or 0})
    for r in old['famiglie']:
        _insert(conn, 'families', {'id': r['id'], 'name': r['nome'], 'created_at': r['creato_il']})
    for r in old['utenti']:
        _insert(conn, 'users', {'id': r['id'], 'email': r['email'], 'name': r['nome'], 'password_hash': r['password_hash'],
                                'email_verified': r['email_verificata'], 'session_version': r['sessione_ver'],
                                'consent_at': r.get('consenso_il'), 'language': r.get('lingua') or 'it',
                                'created_at': r['creato_il']})
    for r in old['membri']:
        _insert(conn, 'members', {'family_id': r['famiglia_id'], 'user_id': r['utente_id'],
                                  'role': _map(ROLES, r['ruolo']), 'created_at': r['creato_il']})
    for r in old['identita']:
        _insert(conn, 'identities', {'provider': r['provider'], 'subject': r['soggetto'], 'user_id': r['utente_id'],
                                     'email': r.get('email'), 'created_at': r['creato_il']})
    for r in old['token']:
        _insert(conn, 'tokens', {'hash': r['hash'], 'kind': _map(TOKEN_KINDS, r['tipo']), 'user_id': r.get('utente_id'),
                                 'family_id': r.get('famiglia_id'), 'expires_at': r['scade_il'], 'used_at': r.get('usato_il'),
                                 'created_at': r['creato_il']})
    for r in old['bambini']:
        _insert(conn, 'children', {'id': r['id'], 'family_id': r['famiglia_id'], 'name': r['nome'],
                                   'birth_date': r.get('data_nascita'), 'archived': r.get('archiviato') or 0,
                                   'created_at': r['creato_il']})
    for r in old['alimenti']:
        _insert(conn, 'foods', {'id': r['id'], 'family_id': r['famiglia_id'], 'name': r['nome'],
                                'category_id': r['categoria_id'], 'archived': r.get('archiviato') or 0})
    for r in old['pasti']:
        _insert(conn, 'meals', {'id': r['id'], 'child_id': r['bambino_id'], 'date': r['data'],
                                'meal_type': _map(MEAL_TYPES, r['pasto_tipo']), 'notes': r.get('note') or '',
                                'reaction': r.get('reazione') or 0, 'created_by': r.get('creato_da'),
                                'created_at': r['creato_il']})
    for r in old['pasto_alimenti']:
        _insert(conn, 'meal_foods', {'meal_id': r['pasto_id'], 'food_id': r['alimento_id'], 'amount': _map(AMOUNTS, r['quantita'])})
    for r in old['recipienti']:
        _insert(conn, 'jars', {'id': r['id'], 'family_id': r['famiglia_id'], 'label': r['numero'],
                               'location': _map(LOCATIONS, r['posizione']), 'made_on': r['data_creazione'],
                               'notes': r.get('note') or '', 'used_on': r.get('consumato_il'), 'meal_id': r.get('pasto_id')})
    for r in old['recipiente_alimenti']:
        _insert(conn, 'jar_foods', {'jar_id': r['recipiente_id'], 'food_id': r['alimento_id']})
    for r in old['piano_frequenze']:
        _insert(conn, 'plan_frequencies', {'child_id': r['bambino_id'], 'macro': _map(MACROS, r['macro']),
                                           'min_times': r.get('minimo'), 'max_times': r.get('massimo')})
    for r in old['piano_menu']:
        _insert(conn, 'plan_meals', {'id': r['id'], 'child_id': r['bambino_id'], 'weekday': r['giorno'],
                                     'meal_type': _map(MEAL_TYPES, r['pasto_tipo']), 'notes': r.get('note') or ''})
    for r in old['piano_menu_alimenti']:
        _insert(conn, 'plan_meal_foods', {'plan_meal_id': r['menu_id'], 'food_id': r['alimento_id']})


def _from_single_family(conn, existing):
    """v1/v2 -> v5. The data goes into a family with no members: the first user who signs up claims it."""
    category_names = {r['id']: r['nome'] for r in _rows(conn, existing, 'categorie')}
    foods, meals = _rows(conn, existing, 'alimenti'), _rows(conn, existing, 'pasti')
    meal_foods, jars, jar_foods = (_rows(conn, existing, t) for t in ('pasto_alimenti', 'recipienti', 'recipiente_alimenti'))
    _drop(conn, existing, ['recipiente_alimenti', 'recipienti', 'pasto_alimenti', 'pasti', 'alimenti', 'categorie'])
    conn.executescript(db.SCHEMA)
    db.seed_categories(conn)

    family_id = conn.execute("INSERT INTO families (name) VALUES ('La mia famiglia')").lastrowid
    child_id = conn.execute("INSERT INTO children (family_id, name) VALUES (?, 'Il mio bambino')", (family_id,)).lastrowid
    for f in foods:
        category = f.get('categoria') or category_names.get(f.get('categoria_id')) or 'Altro'
        _insert(conn, 'foods', {'id': f['id'], 'family_id': family_id, 'name': f['nome'],
                                'category_id': db.category_id(conn, category_key(category)), 'archived': f.get('archiviato') or 0})
    for m in meals:
        _insert(conn, 'meals', {'id': m['id'], 'child_id': child_id, 'date': m['data'], 'meal_type': _map(MEAL_TYPES, m['pasto_tipo']),
                                'notes': m.get('note') or '', 'reaction': m.get('reazione') or 0})
    food_ids, meal_ids = {f['id'] for f in foods}, {m['id'] for m in meals}
    for r in meal_foods:  # skip orphan rows (foreign keys were not enforced in v1)
        if r['pasto_id'] in meal_ids and r['alimento_id'] in food_ids:
            _insert(conn, 'meal_foods', {'meal_id': r['pasto_id'], 'food_id': r['alimento_id'], 'amount': _map(AMOUNTS, r['quantita'])})
    for j in jars:
        _insert(conn, 'jars', {'id': j['id'], 'family_id': family_id, 'label': j['numero'], 'location': _map(LOCATIONS, j['posizione']),
                               'made_on': j['data_creazione'], 'notes': j.get('note') or '', 'used_on': j.get('consumato_il'),
                               'meal_id': j.get('pasto_id') if j.get('pasto_id') in meal_ids else None})
    jar_ids = {j['id'] for j in jars}
    for r in jar_foods:
        if r['recipiente_id'] in jar_ids and r['alimento_id'] in food_ids:
            _insert(conn, 'jar_foods', {'jar_id': r['recipiente_id'], 'food_id': r['alimento_id']})


# ---------- JSON backups made before v5 ----------

_TABLES = {'bambini': 'children', 'alimenti': 'foods', 'pasti': 'meals', 'pasto_alimenti': 'meal_foods',
           'recipienti': 'jars', 'recipiente_alimenti': 'jar_foods', 'categorie': 'categories'}
_COLUMNS = {'nome': 'name', 'data_nascita': 'birth_date', 'archiviato': 'archived', 'categoria_id': 'category_id',
            'categoria': 'category', 'bambino_id': 'child_id', 'data': 'date', 'pasto_tipo': 'meal_type', 'note': 'notes',
            'reazione': 'reaction', 'pasto_id': 'meal_id', 'alimento_id': 'food_id', 'quantita': 'amount', 'numero': 'label',
            'posizione': 'location', 'data_creazione': 'made_on', 'consumato_il': 'used_on', 'recipiente_id': 'jar_id'}
_VALUES = {'meal_type': MEAL_TYPES, 'amount': AMOUNTS, 'location': LOCATIONS}


def is_legacy_backup(data):
    return isinstance(data, dict) and isinstance(data.get('tabelle'), dict)


def legacy_backup(data):
    """Convert a backup exported before v5 (Italian keys and values) to the current format."""
    def row(r):
        if not isinstance(r, dict):
            return r
        out = {_COLUMNS.get(k, k): v for k, v in r.items()}
        for col, mapping in _VALUES.items():
            if col in out:
                out[col] = _map(mapping, out[col])
        if 'category' in out:
            out['category'] = category_key(out['category'])
        return out

    tables = {}
    for name, rows in data['tabelle'].items():
        tables[_TABLES.get(name, name)] = [row(r) for r in rows] if isinstance(rows, list) else rows
    categories = data.get('categorie') or data['tabelle'].get('categorie') or []
    plans = {}
    for child, plan in (data.get('piani') or {}).items():
        if not isinstance(plan, dict):
            continue
        plans[child] = {
            'frequencies': [{'macro': _map(MACROS, f.get('macro')), 'min': f.get('minimo'), 'max': f.get('massimo')}
                            for f in plan.get('frequenze') or [] if isinstance(f, dict)],
            'menu': [{'weekday': m.get('giorno'), 'meal_type': _map(MEAL_TYPES, m.get('pasto_tipo')), 'notes': m.get('note'),
                      'foods': m.get('alimenti')} for m in plan.get('menu') or [] if isinstance(m, dict)],
        }
    return {
        'app': data.get('app'),
        'version': data.get('versione'),
        'family': data.get('famiglia'),
        'categories': [{'id': c.get('id'), 'key': category_key(c.get('nome'))} for c in categories if isinstance(c, dict)],
        'tables': tables,
        'plans': plans,
    }
