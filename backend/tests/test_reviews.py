import copy
import json
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import fixture
from test_evaluations import model_reply, submit


def make_appeal(c,e,criterion='c07',revision=None):
    return c.post('/api/v1/evaluations/'+e['evaluation_id']+'/appeals',json=dict(
        expected_revision=revision or e['revision'],criterion_id=criterion,comment='Please review this criterion.'))


def replacement(e):
    j=copy.deepcopy(next(j for j in e['final_result']['judgments'] if j['criterion_id']=='c07'))
    j.update(answer='na',rationale='Chat ended before an opportunity to conclude.')
    return j


def test_appeal_no_score_change_decision_recalculates_and_persists(settings):
    cfg=replace(settings,provider_api_key='test-only')
    with TestClient(create_app(cfg,provider_transport=httpx.MockTransport(model_reply))) as c:
        e=submit(c); original=copy.deepcopy(e['original_ai_result'])
        a=make_appeal(c,e)
        assert a.status_code==201 and a.json()['status']=='pending'
        pending=c.get('/api/v1/evaluations/'+e['evaluation_id']).json()
        assert pending['revision']==2 and pending['final_result']==e['final_result']
        assert pending['original_ai_result']==original
        req=dict(expected_revision=2,action='change',reason='N/A condition confirmed.',replacement=replacement(e))
        url='/api/v1/appeals/'+a.json()['appeal_id']+'/decision'
        changed=c.post(url,json=req)
        assert changed.status_code==200
        final=changed.json()
        assert final['final_result']['total']==100 and final['original_ai_result']==original
        assert final['revision']==3 and final['appeals'][0]['decision']['reason']==req['reason']
        assert c.post(url,json=req).json()['error']['code']=='appeal_resolved'
        assert make_appeal(c,final).json()['error']['code']=='duplicate_appeal'
        assert c.get('/api/v1/appeals?status=pending').json()['items']==[]
    with TestClient(create_app(cfg)) as c:
        assert c.get('/api/v1/evaluations/'+e['evaluation_id']).json()==final
        assert c.get('/api/v1/appeals/'+a.json()['appeal_id']).json()['decision'] is not None


def test_confirm_and_stale_revision(settings):
    with TestClient(create_app(replace(settings,provider_api_key='test-only'),provider_transport=httpx.MockTransport(model_reply))) as c:
        e=submit(c)
        a=make_appeal(c,e).json()
        url='/api/v1/appeals/'+a['appeal_id']+'/decision'
        req=dict(expected_revision=1,action='confirm',reason='Original judgment is supported.',replacement=None)
        assert c.post(url,json=req).json()['error']['code']=='version_conflict'
        req['expected_revision']=2
        result=c.post(url,json=req).json()
        assert result['final_result']==e['final_result']
        assert result['original_ai_result']==e['original_ai_result']


def test_invalid_review_cannot_corrupt_result(settings):
    with TestClient(create_app(replace(settings,provider_api_key='test-only'),provider_transport=httpx.MockTransport(model_reply))) as c:
        e=submit(c);a=make_appeal(c,e).json()
        for mutate in [
            lambda j:j.update(criterion_id='c01'),
            lambda j:j['evidence'].update(message_ids=['unknown']),
            lambda j:j.update(answer='numeric',numeric_value=8),
            lambda j:j.update(rationale=''),
        ]:
            j=replacement(e);mutate(j)
            r=c.post('/api/v1/appeals/'+a['appeal_id']+'/decision',json=dict(expected_revision=2,action='change',reason='Review',replacement=j))
            assert r.status_code==422 and r.json()['error']['code']=='invalid_judgment'
        after=c.get('/api/v1/evaluations/'+e['evaluation_id']).json()
        assert after['final_result']==e['final_result'] and after['revision']==2
        assert after['appeals'][0]['status']=='pending'


def test_two_decisions_preserve_each_other_and_gross_flag(settings):
    with TestClient(create_app(replace(settings,provider_api_key='test-only'),provider_transport=httpx.MockTransport(model_reply))) as c:
        e=submit(c)
        a=make_appeal(c,e).json()
        gross=make_appeal(c,e,criterion='c08',revision=2).json()
        first=c.post('/api/v1/appeals/'+a['appeal_id']+'/decision',json=dict(expected_revision=3,action='change',reason='Review',replacement=replacement(e))).json()
        assert first['final_result']['total']==100
        j=copy.deepcopy(e['original_ai_result']['judgments'][-1]);j.update(answer='yes',rationale='Reviewer identified a gross violation in the inspected range.')
        final=c.post('/api/v1/appeals/'+gross['appeal_id']+'/decision',json=dict(expected_revision=4,action='change',reason='Review gross error',replacement=j)).json()
        assert final['final_result']['gross_error'] is True and final['final_result']['total']==100
        assert final['original_ai_result']['gross_error'] is False


def test_concurrent_appeals_compare_revision_transactionally(settings):
    with TestClient(create_app(replace(settings,provider_api_key='test-only'),provider_transport=httpx.MockTransport(model_reply))) as c:
        e=submit(c)
        with ThreadPoolExecutor(2) as pool:
            replies=list(pool.map(lambda criterion:make_appeal(c,e,criterion),['c01','c07']))
        assert sorted(r.status_code for r in replies)==[201,409]
        assert c.get('/api/v1/evaluations/'+e['evaluation_id']).json()['revision']==2
