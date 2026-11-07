import json
from pathlib import Path

from .db import dump, new_id
from .errors import APIError
from .models import ChecklistInput


def seed(store):
    # Read the committed normative seed; no duplicate hardcoded interpretation.
    path = Path(__file__).resolve().parents[2] / 'fixtures' / 'checklist.json'
    doc = json.loads(path.read_text(encoding='utf-8'))
    ChecklistInput.model_validate({k: doc[k] for k in ('name', 'sections', 'criteria')})
    with store.transaction() as db:
        if not db.execute('SELECT 1 FROM checklists WHERE id=?', (doc['checklist_id'],)).fetchone():
            db.execute('INSERT INTO checklists(id,latest) VALUES(?,?)', (doc['checklist_id'], 1))
            db.execute('INSERT INTO checklist_versions VALUES(?,?,?)', (doc['checklist_id'], 1, dump(doc)))


def head(db, id, active=False):
    row = db.execute('SELECT * FROM checklists WHERE id=?', (id,)).fetchone()
    if not row:
        raise APIError(404, 'not_found', 'Checklist not found.')
    if active and row['archived']:
        raise APIError(409, 'checklist_archived', 'Checklist is archived.')
    return row


def version(db, id, version):
    row = db.execute('SELECT document FROM checklist_versions WHERE checklist_id=? AND version=?', (id, version)).fetchone()
    if row is None:
        raise APIError(404, 'not_found', 'Checklist version not found.')
    return json.loads(row['document'])


def create(db, configuration):
    id = new_id('checklist')
    doc = dict(checklist_id=id, version=1, **configuration.model_dump())
    db.execute('INSERT INTO checklists(id,latest) VALUES(?,1)', (id,))
    db.execute('INSERT INTO checklist_versions VALUES(?,?,?)', (id, 1, dump(doc)))
    return doc


def update(db, id, expected, configuration):
    row = head(db, id, active=True)
    if row['latest'] != expected:
        raise APIError(409, 'version_conflict', 'Checklist version changed; reload before saving.')
    doc = dict(checklist_id=id, version=expected+1, **configuration.model_dump())
    db.execute('INSERT INTO checklist_versions VALUES(?,?,?)', (id, expected+1, dump(doc)))
    db.execute('UPDATE checklists SET latest=? WHERE id=?', (expected+1, id))
    return doc
