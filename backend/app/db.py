"""Small SQLite repository. JSON snapshots retain exact historical wire values."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4, uuid5, NAMESPACE_URL

from .errors import APIError


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def new_id(prefix):
    return f'{prefix}_{uuid4().hex}'


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
                INSERT INTO schema_version SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_version);
                CREATE TABLE IF NOT EXISTS conversations (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    kind TEXT NOT NULL, group_id TEXT NOT NULL, source_id TEXT NOT NULL,
                    source_json TEXT NOT NULL, document TEXT NOT NULL,
                    UNIQUE(kind, group_id, source_id));
                CREATE TABLE IF NOT EXISTS checklists (
                    id TEXT PRIMARY KEY, latest INTEGER NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS checklist_versions (
                    checklist_id TEXT NOT NULL REFERENCES checklists(id), version INTEGER NOT NULL,
                    document TEXT NOT NULL, PRIMARY KEY(checklist_id, version));
                CREATE TABLE IF NOT EXISTS evaluations (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    checklist_id TEXT NOT NULL, checklist_version INTEGER NOT NULL,
                    document TEXT NOT NULL,
                    FOREIGN KEY(checklist_id, checklist_version) REFERENCES checklist_versions(checklist_id, version));
                CREATE TABLE IF NOT EXISTS appeals (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    evaluation_id TEXT NOT NULL REFERENCES evaluations(id), criterion_id TEXT NOT NULL,
                    document TEXT NOT NULL, UNIQUE(evaluation_id, criterion_id));
                CREATE TABLE IF NOT EXISTS provider_calls (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
                    document TEXT NOT NULL);
            ''')
            if db.execute('SELECT version FROM schema_version').fetchone()[0] != 1:
                raise RuntimeError('Unsupported database schema version')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, db, table, id):
        # table is an internal constant, never supplied by HTTP callers.
        row = db.execute(f'SELECT document FROM {table} WHERE id=?', (id,)).fetchone()
        if row is None:
            raise APIError(404, 'not_found', 'Resource not found.')
        return json.loads(row['document'])

    def save(self, db, table, doc, key):
        db.execute(f'UPDATE {table} SET document=? WHERE id=?', (dump(doc), doc[key]))

    def normalize(self, db, source, kind, group_id=None):
        raw = source.model_dump()
        key = (kind, group_id or '', raw['conversation_id'])
        row = db.execute('SELECT source_json,document FROM conversations WHERE kind=? AND group_id=? AND source_id=?', key).fetchone()
        if row:
            if json.loads(row['source_json']) != raw:
                raise APIError(409, 'source_conflict', 'Source identity already exists with different content.')
            return json.loads(row['document']), False
        id = new_id('conv')
        doc = dict(conversation_id=id, source=dict(kind=kind, group_id=group_id, conversation_id=raw['conversation_id']),
                   channel=raw['channel'], language=raw['language'], audio_url=raw['audio_url'],
                   messages=[dict(message_id='msg_'+uuid5(NAMESPACE_URL, f'cqa:{id}:{i}').hex,
                                  ordinal=i, **m) for i, m in enumerate(raw['transcript'], 1)])
        db.execute('INSERT INTO conversations(id,kind,group_id,source_id,source_json,document) VALUES(?,?,?,?,?,?)',
                   (id, *key, dump(raw), dump(doc)))
        return doc, True
