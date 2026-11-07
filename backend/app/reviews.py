"""Transactional, optimistic review workflow over immutable original results."""
import copy
import json

from . import checklists
from .db import dump, new_id
from .errors import APIError
from .provider import now
from .scoring import InvalidJudgment, calculate, validate_evidence, validate_judgment


def check_revision(doc, expected):
    if doc['revision'] != expected:
        raise APIError(409,'version_conflict','Evaluation changed; reload before saving.')


def submit(store, id, request):
    with store.transaction() as db:
        evaluation=store.get(db,'evaluations',id)
        if evaluation['status'] != 'succeeded':
            raise APIError(409,'evaluation_not_ready','Only successful evaluations may be appealed.')
        check_revision(evaluation,request.expected_revision)
        checklist=checklists.version(db,evaluation['checklist_id'],evaluation['checklist_version'])
        if request.criterion_id not in {c['criterion_id'] for c in checklist['criteria']}:
            raise APIError(422,'validation_error','Unknown criterion ID for this evaluation.')
        if db.execute('SELECT 1 FROM appeals WHERE evaluation_id=? AND criterion_id=?',(id,request.criterion_id)).fetchone():
            raise APIError(409,'duplicate_appeal','This criterion has already been appealed.')
        conversation=store.get(db,'conversations',evaluation['conversation_id'])
        try:
            validate_evidence(request.evidence,conversation)
        except InvalidJudgment as exc:
            raise APIError(422,'validation_error',str(exc)) from None
        appeal=dict(appeal_id=new_id('appeal'),evaluation_id=id,criterion_id=request.criterion_id,
                    comment=request.comment,evidence=request.evidence.model_dump(),status='pending',created_at=now(),decision=None)
        db.execute('INSERT INTO appeals(id,evaluation_id,criterion_id,document) VALUES(?,?,?,?)',
                   (appeal['appeal_id'],id,request.criterion_id,dump(appeal)))
        evaluation['appeals'].append(appeal)
        evaluation['revision']+=1
        # A pending appeal intentionally leaves both result snapshots untouched.
        store.save(db,'evaluations',evaluation,'evaluation_id')
        return appeal


def decide(store, id, request):
    with store.transaction() as db:
        appeal=store.get(db,'appeals',id)
        if appeal['status']=='resolved':
            raise APIError(409,'appeal_resolved','A reviewer decision is already saved.')
        evaluation=store.get(db,'evaluations',appeal['evaluation_id'])
        check_revision(evaluation,request.expected_revision)
        checklist=checklists.version(db,evaluation['checklist_id'],evaluation['checklist_version'])
        conversation=store.get(db,'conversations',evaluation['conversation_id'])
        criteria={c['criterion_id']:c for c in checklist['criteria']}
        if request.replacement is not None:
            try:
                validate_judgment(request.replacement,criteria[appeal['criterion_id']],conversation)
            except InvalidJudgment as exc:
                raise APIError(422,'invalid_judgment',str(exc)) from None
        decision=dict(decision_id=new_id('decision'),action=request.action,reason=request.reason,
                      replacement=request.replacement.model_dump() if request.replacement else None,created_at=now())
        appeal.update(status='resolved',decision=decision)
        # Use current final judgments to retain decisions on other criteria.
        judgments=copy.deepcopy(evaluation['final_result']['judgments'])
        if request.action=='change':
            judgments=[decision['replacement'] if j['criterion_id']==appeal['criterion_id'] else j for j in judgments]
        evaluation['final_result']=calculate(checklist,judgments,conversation)
        evaluation['appeals']=[appeal if a['appeal_id']==id else a for a in evaluation['appeals']]
        evaluation['revision']+=1
        store.save(db,'appeals',appeal,'appeal_id')
        store.save(db,'evaluations',evaluation,'evaluation_id')
        return evaluation
