import copy
import json
import time
from dataclasses import replace

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import fixture


def model_reply(request, mutate=None):
    payload=json.loads(request.content)
    checklist=json.loads(payload['messages'][1]['content'].split('\n',1)[1])
    conv=json.loads(payload['messages'][2]['content'])['untrusted_conversation_evidence']
    ids=[m['message_id'] for m in conv['messages']]
    mapped={f'msg_demo_{i}':id for i,id in enumerate(ids,1)}
    judgments=fixture('evaluation-original')['original_ai_result']['judgments']
    by_id={j['criterion_id']:j for j in judgments}
    js=[]
    for c in checklist['criteria']:
        j=copy.deepcopy(by_id.get(c['criterion_id'],dict(criterion_id=c['criterion_id'],answer='yes',numeric_value=None,
                rationale='New criterion evaluated from saved configuration.',evidence=dict(message_ids=['msg_demo_2'],inspected_ranges=[]))))
        j['evidence']['message_ids']=[mapped[id] for id in j['evidence']['message_ids']]
        for r in j['evidence']['inspected_ranges']:
            r.update(start_message_id=mapped[r['start_message_id']],end_message_id=mapped[r['end_message_id']])
        js.append(j)
    if mutate:mutate(js)
    body=dict(model='gpt-4.1-mini-2025-04-14',choices=[dict(finish_reason='stop',message=dict(content=json.dumps({'judgments':js})))],
              usage=dict(prompt_tokens=2000,completion_tokens=600,prompt_tokens_details=dict(cached_tokens=100)))
    return httpx.Response(200,json=body,headers={'x-request-id':'upstream-test'})


def wait_result(client,id):
    for _ in range(200):
        res=client.get('/api/v1/evaluations/'+id)
        assert res.status_code==200
        doc=res.json()
        if doc['status'] in ('succeeded','failed'):return doc
        time.sleep(.01)
    raise AssertionError('Evaluation did not terminate')


def submit(client,version=1):
    conv=client.post('/api/v1/conversations',json=fixture('upload-request')).json()
    res=client.post('/api/v1/evaluations',json=dict(conversation_id=conv['conversation_id'],checklist_id='checklist_seed',checklist_version=version))
    assert res.status_code==202 and res.json()['status']=='queued'
    assert res.headers['location'].endswith(res.json()['evaluation_id'])
    return wait_result(client,res.json()['evaluation_id'])


def test_success_real_adapter_pipeline_and_audit(settings):
    seen=[]
    def upstream(request):
        seen.append(json.loads(request.content))
        return model_reply(request)
    cfg=replace(settings,provider_api_key='test-only')
    with TestClient(create_app(cfg,provider_transport=httpx.MockTransport(upstream))) as c:
        result=submit(c)
        assert result['status']=='succeeded'
        assert result['original_ai_result']['total']==92.31
        assert result['original_ai_result']==result['final_result']
        assert 'UNTRUSTED' in seen[0]['messages'][0]['content']
        assert seen[0]['messages'][2]['role']=='user'
        assert seen[0]['response_format']['json_schema']['strict'] is True
        assert seen[0]['store'] is False
        with c.app.state.store.transaction() as db:
            raw=json.loads(db.execute('SELECT document FROM provider_calls').fetchone()[0])
            assert raw['usage']['prompt_tokens']==2000 and raw['model_returned']=='gpt-4.1-mini-2025-04-14'
            assert raw['estimated_cost_usd']>0 and raw['raw_response']['choices']
    # A fresh process/factory sees completed results, not a regenerated model answer.
    with TestClient(create_app(cfg)) as c:
        assert c.get('/api/v1/evaluations/'+result['evaluation_id']).json()==result


def test_one_bounded_repair(settings):
    calls=[]
    def upstream(req):
        calls.append(json.loads(req.content))
        return model_reply(req,(lambda js:js[3].update(numeric_value=17)) if len(calls)==1 else None)
    with TestClient(create_app(replace(settings,provider_api_key='test-only'),provider_transport=httpx.MockTransport(upstream))) as c:
        result=submit(c)
        assert result['status']=='succeeded' and len(calls)==2
        assert calls[1]['messages'][-1]['role']=='user'
        assert 'previous_untrusted_response' in calls[1]['messages'][-1]['content']
        with c.app.state.store.transaction() as db:
            records=[json.loads(r[0]) for r in db.execute('SELECT document FROM provider_calls')]
            assert [r['kind'] for r in records]==['initial','repair']
            assert sum(r['estimated_cost_usd'] for r in records)>records[0]['estimated_cost_usd']


def test_invalid_output_never_success(settings):
    count=[]
    def upstream(req):
        count.append(1)
        return model_reply(req,lambda js:js[0]['evidence'].update(message_ids=['not-a-message']))
    with TestClient(create_app(replace(settings,provider_api_key='test-only'),provider_transport=httpx.MockTransport(upstream))) as c:
        result=submit(c)
        assert len(count)==2
        assert result['status']=='failed' and result['provider']['error']['code']=='provider_invalid_output'
        assert result['original_ai_result'] is None and result['final_result'] is None


def test_provider_failures(settings):
    for status,code,retries in [(401,'provider_auth',1),(429,'provider_rate_limited',2),(503,'provider_unavailable',2)]:
        count=[]
        def upstream(req):
            count.append(1)
            return httpx.Response(status,json={'secret':'do not leak'})
        # Separate DB per case to keep expected import/source identities isolated.
        cfg=replace(settings,database_path=settings.database_path+str(status),provider_api_key='test-only')
        with TestClient(create_app(cfg,provider_transport=httpx.MockTransport(upstream))) as c:
            result=submit(c)
            assert result['status']=='failed' and result['provider']['error']['code']==code
            assert result['final_result'] is None and 'do not leak' not in json.dumps(result)
            assert len(count)==retries


def test_missing_credentials_is_failed_not_mock(client):
    result=submit(client)
    assert result['status']=='failed' and result['provider']['error']['code']=='provider_auth'
    assert result['final_result'] is None


def test_dynamic_saved_new_criterion_and_pinned_old_version(settings):
    seen=[]
    def upstream(req):
        seen.append(json.loads(req.content))
        return model_reply(req)
    with TestClient(create_app(replace(settings,provider_api_key='test-only'),provider_transport=httpx.MockTransport(upstream))) as c:
        conf={k:fixture('checklist')[k] for k in ('name','sections','criteria')}
        criterion=copy.deepcopy(conf['criteria'][0]);criterion.update(criterion_id='added_without_code',wording='Check an additional configured behavior.',weight=20)
        conf['criteria'].append(criterion)
        assert c.put('/api/v1/checklists/checklist_seed',json=dict(expected_version=1,configuration=conf)).status_code==201
        v2=submit(c,2)
        v1=submit(c,1)
        assert v2['status']==v1['status']=='succeeded'
        assert len(v2['final_result']['judgments'])==9 and len(v1['final_result']['judgments'])==8
        assert v2['final_result']['judgments'][-1]['criterion_id']=='added_without_code'
        assert 'added_without_code' in seen[0]['messages'][1]['content']
        assert 'added_without_code' not in seen[1]['messages'][1]['content']


def test_timeout_is_bounded(settings):
    calls=[]
    def upstream(req):
        calls.append(1)
        raise httpx.ReadTimeout('secret upstream URL')
    with TestClient(create_app(replace(settings,provider_api_key='test-only'),provider_transport=httpx.MockTransport(upstream))) as c:
        result=submit(c)
        assert result['provider']['error']['code']=='provider_timeout'
        assert result['status']=='failed' and len(calls)==2
