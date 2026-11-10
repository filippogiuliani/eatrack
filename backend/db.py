"""SQLite database: connection, schema and upgrades from earlier versions (see migrations.py)."""
import os
import sqlite3
from contextlib import contextmanager

DATA_DIR = os.environ.get('EATRACK_DATA', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
DB_PATH = os.path.join(DATA_DIR, 'eatrack.db')

# v3: multi-family; v4: weekly plan; v5: English schema and stored values
SCHEMA_VERSION = 5

# Values stored in the database. They are stable keys: the UI and exports translate them.
MEAL_TYPES = ['breakfast', 'lunch', 'snack', 'dinner']
MAIN_MEALS = ('lunch', 'dinner')
AMOUNTS = ['full', 'half', 'puree', 'taste', 'refused']
LOCATIONS = ['fridge', 'freezer', 'pantry']
ROLES = ['admin', 'member']

# key, diary column (diary_group), macro category (used by statistics and the weekly plan)
BASE_CATEGORIES = [
    ('carbs', 'carbs', 'carbs'),
    ('broth', 'broth', 'broth'),
    ('vegetables', 'vegetables', 'vegetables'),
    ('white_meat', 'protein', 'meat'),
    ('red_meat', 'protein', 'meat'),
    ('fish', 'protein', 'fish'),
    ('legumes', 'protein', 'legumes'),
    ('eggs', 'protein', 'eggs'),
    ('dairy', 'protein', 'dairy'),
    ('fruit', 'fruit', 'fruit'),
]

SCHEMA = '''
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    diary_group TEXT NOT NULL DEFAULT 'protein',
    macro TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS families (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Link with doTrack: where the weekly menu's foods go shopping (the token is a doTrack API token)
CREATE TABLE IF NOT EXISTS dotrack_links (
    family_id INTEGER PRIMARY KEY REFERENCES families(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    token TEXT NOT NULL,
    list_id INTEGER,
    list_name TEXT
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
    session_version INTEGER NOT NULL DEFAULT 1,
    consent_at TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS members (
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (family_id, user_id)
);
CREATE TABLE IF NOT EXISTS identities (
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (provider, subject)
);
CREATE TABLE IF NOT EXISTS tokens (
    hash TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    family_id INTEGER REFERENCES families(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS children (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    birth_date DATE,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_children_family ON children(family_id);
CREATE TABLE IF NOT EXISTS foods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    archived INTEGER NOT NULL DEFAULT 0,
    UNIQUE (family_id, name)
);
CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    meal_type TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    reaction INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_meals_child_date ON meals(child_id, date);
CREATE TABLE IF NOT EXISTS meal_foods (
    meal_id INTEGER NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    food_id INTEGER NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
    amount TEXT NOT NULL,
    PRIMARY KEY (meal_id, food_id)
);
CREATE INDEX IF NOT EXISTS idx_meal_foods_food ON meal_foods(food_id);
CREATE TABLE IF NOT EXISTS jars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    location TEXT NOT NULL,
    made_on DATE NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    used_on DATE,
    meal_id INTEGER REFERENCES meals(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_jars_family ON jars(family_id);
CREATE TABLE IF NOT EXISTS jar_foods (
    jar_id INTEGER NOT NULL REFERENCES jars(id) ON DELETE CASCADE,
    food_id INTEGER NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
    PRIMARY KEY (jar_id, food_id)
);
-- Pediatrician's weekly plan, per child. Both parts are optional.
CREATE TABLE IF NOT EXISTS plan_frequencies (
    child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    macro TEXT NOT NULL,
    min_times INTEGER,
    max_times INTEGER,
    PRIMARY KEY (child_id, macro)
);
CREATE TABLE IF NOT EXISTS plan_meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    weekday INTEGER NOT NULL,          -- 0 = Monday … 6 = Sunday
    meal_type TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE (child_id, weekday, meal_type)
);
CREATE TABLE IF NOT EXISTS plan_meal_foods (
    plan_meal_id INTEGER NOT NULL REFERENCES plan_meals(id) ON DELETE CASCADE,
    food_id INTEGER NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
    PRIMARY KEY (plan_meal_id, food_id)
);
'''


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


@contextmanager
def transaction():
    """Connection that commits on success and rolls back on error."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info({table})')]


def seed_categories(conn):
    for i, (key, group, macro) in enumerate(BASE_CATEGORIES):
        conn.execute('INSERT OR IGNORE INTO categories (key, diary_group, macro, sort_order) VALUES (?,?,?,?)',
                     (key, group, macro, i))


def category_id(conn, key):
    """Id of the category with this key, created if missing (e.g. custom categories from old backups)."""
    row = conn.execute('SELECT id FROM categories WHERE key = ?', (key,)).fetchone()
    if row:
        return row[0]
    order = conn.execute('SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories').fetchone()[0]
    return conn.execute('INSERT INTO categories (key, macro, sort_order) VALUES (?,?,?)', (key, key, order)).lastrowid


def create_family(conn, name, language='en'):
    """Create a family with the starter food catalog in the given language."""
    import i18n
    family_id = conn.execute('INSERT INTO families (name) VALUES (?)', (name,)).lastrowid
    for food, category in i18n.starter_foods(language):
        conn.execute('INSERT INTO foods (family_id, name, category_id) VALUES (?,?,?)',
                     (family_id, food, category_id(conn, category)))
    return family_id


def init_db():
    import migrations
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = connect()
    try:
        existing = tables(conn)
        if migrations.needs_upgrade(conn, existing):
            import backup
            backup.create_backup('pre-migration')
            migrations.upgrade(conn, existing)
        conn.executescript(SCHEMA)
        # weHub link (see hub.py): which weHub family/user/person each row is, NULL = not managed there
        for table, column in (('families', 'hub_id'), ('families', 'hub_version'), ('users', 'hub_id'), ('children', 'hub_id')):
            if column not in {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} INTEGER')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_families_hub ON families(hub_id)')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_hub ON users(hub_id)')
        seed_categories(conn)
        conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        conn.execute('PRAGMA journal_mode = WAL')
        conn.commit()
    finally:
        conn.close()
