"""Database schema and upgrades from older versions."""
import os
import sqlite3

import db
from app import create_app
from conftest import PASSWORD, ok, sign_up

# The v4 schema (Italian names), as it was before v5. Only the parts the upgrade reads.
V4_SCHEMA = '''
CREATE TABLE categorie (id INTEGER PRIMARY KEY, nome TEXT, emoji TEXT, colore TEXT, gruppo TEXT, macro TEXT, ordine INTEGER);
CREATE TABLE famiglie (id INTEGER PRIMARY KEY, nome TEXT, creato_il TEXT);
CREATE TABLE utenti (id INTEGER PRIMARY KEY, email TEXT, nome TEXT, password_hash TEXT, email_verificata INTEGER,
                     sessione_ver INTEGER, consenso_il TEXT, lingua TEXT, creato_il TEXT);
CREATE TABLE membri (famiglia_id INTEGER, utente_id INTEGER, ruolo TEXT, creato_il TEXT);
CREATE TABLE identita (provider TEXT, soggetto TEXT, utente_id INTEGER, email TEXT, creato_il TEXT);
CREATE TABLE token (hash TEXT, tipo TEXT, utente_id INTEGER, famiglia_id INTEGER, scade_il TEXT, usato_il TEXT, creato_il TEXT);
CREATE TABLE bambini (id INTEGER PRIMARY KEY, famiglia_id INTEGER, nome TEXT, data_nascita DATE, archiviato INTEGER, creato_il TEXT);
CREATE TABLE alimenti (id INTEGER PRIMARY KEY, famiglia_id INTEGER, nome TEXT, categoria_id INTEGER, archiviato INTEGER);
CREATE TABLE pasti (id INTEGER PRIMARY KEY, bambino_id INTEGER, data DATE, pasto_tipo TEXT, note TEXT, reazione INTEGER,
                    creato_da INTEGER, creato_il TEXT);
CREATE TABLE pasto_alimenti (pasto_id INTEGER, alimento_id INTEGER, quantita TEXT);
CREATE TABLE recipienti (id INTEGER PRIMARY KEY, famiglia_id INTEGER, numero TEXT, posizione TEXT, data_creazione DATE,
                         note TEXT, consumato_il DATE, pasto_id INTEGER);
CREATE TABLE recipiente_alimenti (recipiente_id INTEGER, alimento_id INTEGER);
CREATE TABLE piano_frequenze (bambino_id INTEGER, macro TEXT, minimo INTEGER, massimo INTEGER);
CREATE TABLE piano_menu (id INTEGER PRIMARY KEY, bambino_id INTEGER, giorno INTEGER, pasto_tipo TEXT, note TEXT);
CREATE TABLE piano_menu_alimenti (menu_id INTEGER, alimento_id INTEGER);
PRAGMA user_version = 4;
'''


def test_new_database_is_at_current_version(app):
    conn = sqlite3.connect(db.DB_PATH)
    assert conn.execute('PRAGMA user_version').fetchone()[0] == db.SCHEMA_VERSION
    assert conn.execute('PRAGMA foreign_key_check').fetchall() == []


def _fresh_app_on(tmp_path, monkeypatch, setup_sql):
    """Write an old database, then start the app on it (which upgrades it)."""
    path = tmp_path / 'old' / 'eatrack.db'
    path.parent.mkdir()
    conn = sqlite3.connect(path)
    conn.executescript(setup_sql)
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, 'DATA_DIR', str(path.parent))
    monkeypatch.setattr(db, 'DB_PATH', str(path))
    from famkit import backup
    monkeypatch.setattr(backup, 'BACKUP_DIR', str(path.parent / 'backups'))
    return create_app(), path


def test_upgrade_from_v4_italian_schema(app, tmp_path, monkeypatch):
    from werkzeug.security import generate_password_hash
    pw = generate_password_hash(PASSWORD)
    app, path = _fresh_app_on(tmp_path, monkeypatch, V4_SCHEMA + f'''
        INSERT INTO categorie VALUES (1, 'Verdura', '', '', 'verdura', 'Verdura', 2), (2, 'Carne Bianca', '', '', 'proteine', 'Carne', 3);
        INSERT INTO famiglie VALUES (1, 'Casa', '2026-11-01');
        INSERT INTO utenti VALUES (1, 'fil@example.com', 'Fil', '{pw}', 1, 1, '2026-11-01', 'it', '2026-11-01');
        INSERT INTO membri VALUES (1, 1, 'admin', '2026-11-01');
        INSERT INTO bambini VALUES (5, 1, 'Giulia', '2026-01-15', 0, '2026-11-01');
        INSERT INTO alimenti VALUES (7, 1, 'Zucca', 1, 0), (8, 1, 'Pollo', 2, 0);
        INSERT INTO pasti VALUES (9, 5, '2026-11-02', 'Merenda', 'ok', 1, 1, '2026-11-02');
        INSERT INTO pasto_alimenti VALUES (9, 7, 'In Passato'), (9, 8, 'Rifiutato');
        INSERT INTO recipienti VALUES (3, 1, '12', 'Dispensa (Secco)', '2026-10-30', '', '2026-11-02', 9);
        INSERT INTO recipiente_alimenti VALUES (3, 7);
        INSERT INTO piano_frequenze VALUES (5, 'Carne', 1, 3);
        INSERT INTO piano_menu VALUES (4, 5, 6, 'Cena', 'poco sale');
        INSERT INTO piano_menu_alimenti VALUES (4, 8);
    ''')
    c = app.test_client()
    ok(c.post('/api/login', json={'email': 'fil@example.com', 'password': PASSWORD}))  # sessions/passwords survive
    me = ok(c.get('/api/me'))
    assert me['family']['role'] == 'admin' and [x['name'] for x in me['children']] == ['Giulia']
    meal = ok(c.get('/api/meals?child=5&from=2026-11-02&to=2026-11-02'))[0]
    assert (meal['meal_type'], meal['notes'], meal['reaction']) == ('snack', 'ok', 1)
    assert {(x['name'], x['amount']) for x in meal['foods']} == {('Zucca', 'puree'), ('Pollo', 'refused')}
    assert [(j['label'], j['location']) for j in meal['jars']] == [('12', 'pantry')]
    assert ok(c.get('/api/plan?child=5')) == {'frequencies': [{'macro': 'meat', 'min': 1, 'max': 3}],
                                              'menu': [{'weekday': 6, 'meal_type': 'dinner', 'notes': 'poco sale', 'foods': [8]}]}
    conn = sqlite3.connect(path)
    assert conn.execute('PRAGMA user_version').fetchone()[0] == db.SCHEMA_VERSION
    assert not {'utenti', 'pasti', 'alimenti'} & {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    assert any(n.startswith('pre-migration-') for n in os.listdir(path.parent / 'backups'))


def test_upgrade_from_v1_single_family(app, tmp_path, monkeypatch):
    app, _ = _fresh_app_on(tmp_path, monkeypatch, '''
        CREATE TABLE categorie (id INTEGER PRIMARY KEY, nome TEXT);
        CREATE TABLE alimenti (id INTEGER PRIMARY KEY, nome TEXT, categoria_id INTEGER);
        CREATE TABLE pasti (id INTEGER PRIMARY KEY, data DATE, pasto_tipo TEXT, note TEXT);
        CREATE TABLE pasto_alimenti (pasto_id INTEGER, alimento_id INTEGER, quantita TEXT);
        CREATE TABLE recipienti (id INTEGER PRIMARY KEY, numero TEXT, posizione TEXT, data_creazione DATE, note TEXT,
                                 consumato_il DATE, pasto_id INTEGER);
        CREATE TABLE recipiente_alimenti (recipiente_id INTEGER, alimento_id INTEGER);
        INSERT INTO categorie VALUES (1, 'Frutta');
        INSERT INTO alimenti VALUES (1, 'Mela', 1);
        INSERT INTO pasti VALUES (1, '2026-10-01', 'Pranzo', '');
        INSERT INTO pasto_alimenti VALUES (1, 1, 'Assaggio'), (1, 99, 'Assaggio');
        INSERT INTO recipienti VALUES (1, '4', 'Frigorifero', '2026-09-30', '', NULL, NULL);
        INSERT INTO recipiente_alimenti VALUES (1, 1);
    ''')
    # The first user to sign up claims the migrated data
    c = app.test_client()
    me = sign_up(c)
    child = me['children'][0]['id']
    meal = ok(c.get(f'/api/meals?child={child}&from=2026-10-01&to=2026-10-01'))[0]
    assert meal['meal_type'] == 'lunch' and [(x['name'], x['amount']) for x in meal['foods']] == [('Mela', 'taste')]
    assert [(j['label'], j['location']) for j in ok(c.get('/api/jars'))] == [('4', 'fridge')]
