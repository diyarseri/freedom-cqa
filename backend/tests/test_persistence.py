import copy
import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from conftest import fixture


def test_upload_idempotent_persistent_and_conflicts(client, settings):
    source = fixture('upload-request')
    first = client.post('/api/v1/conversations', json=source)
    assert first.status_code == 201
    doc = first.json()
    again = client.post('/api/v1/conversations', json=source)
    assert again.status_code == 200 and again.json() == doc
    with TestClient(create_app(settings)) as reopened:
        assert reopened.get('/api/v1/conversations/' + doc['conversation_id']).json() == doc
    source['transcript'][0]['timestamp'] = '00:01'
    assert client.post('/api/v1/conversations', json=source).json()['error']['code'] == 'source_conflict'
    assert [m['timestamp'] for m in doc['messages']] == ['00:00', '00:02', '00:04', '00:05']


def test_call_timestamps_and_audio_preserved(client):
    src = fixture('upload-request')
    src.update(channel='voice call', audio_url='https://example.com/audio.mp3')
    for i,m in enumerate(src['transcript']):
        m['timestamp'] = f'2026-11-07T12:00:0{i}+05:00'
    result = client.post('/api/v1/conversations', json=src)
    assert result.status_code == 201
    assert result.json()['messages'][0]['timestamp'] == src['transcript'][0]['timestamp']
    assert result.json()['audio_url'] == src['audio_url']
    assert 'audio_offset' not in result.text
    src['transcript'][0]['timestamp'] = '2026-11-07T12:00:00'
    assert client.post('/api/v1/conversations', json=src).status_code == 422


def test_organizer_atomic_repeat_and_signed_query(tmp_path):
    data = fixture('organizer-response')
    seen=[]
    def upstream(request):
        seen.append(request.url)
        return httpx.Response(200,json=data)
    cfg = Settings(database_path=str(tmp_path/'import.sqlite3'), organizer_url='https://example.com/data?sig=private%2Bvalue&group_id=OLD')
    with TestClient(create_app(cfg,organizer_transport=httpx.MockTransport(upstream))) as c:
        one = c.post('/api/v1/dataset-imports',json={'group_id':'DEMO'})
        assert one.status_code == 201 and one.json()['imported'] == 1
        two=c.post('/api/v1/dataset-imports',json={'group_id':'DEMO'})
        assert two.json()['unchanged'] == 1
        assert one.json()['conversation_ids'] == two.json()['conversation_ids']
        assert seen[0].params['sig'] == 'private+value' and seen[0].params.get_list('group_id') == ['DEMO']
        original=copy.deepcopy(data['data']['records'][0])
        data['data']['records'].insert(0,dict(original,conversation_id='new'))
        data['data']['total_records']=2
        data['data']['records'][1]['transcript'][0]['text']='changed'
        assert c.post('/api/v1/dataset-imports',json={'group_id':'DEMO'}).status_code == 409
        assert len(c.get('/api/v1/conversations').json()['items']) == 1


def test_errors_are_envelopes(client):
    assert client.post('/api/v1/dataset-imports',json={'group_id':'DEV'}).status_code == 503
    for path in ['/api/v1/nope','/api/v1/conversations?surprise=1','/api/v1/conversations?language=XX']:
        response=client.get(path)
        assert response.status_code in (404,422)
        assert set(response.json()) == {'error','request_id'}
    assert client.post('/api/v1/conversations',json={}).status_code == 422


def test_unknown_fields_error_paths_and_method(client):
    data=fixture('upload-request');data['unexpected']='secret'
    r=client.post('/api/v1/conversations',json=data)
    assert r.status_code==422 and r.json()['error']['details'][0]['path']=='unexpected'
    r=client.put('/api/v1/conversations',json={})
    assert r.status_code==405 and r.json()['error']['code']=='method_not_allowed'
