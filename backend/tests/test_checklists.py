import copy
from conftest import fixture


def config():
    seed=fixture('checklist')
    return {k:seed[k] for k in ('name','sections','criteria')}


def test_exact_seed_and_immutable_versions(client):
    assert client.get('/api/v1/checklists/checklist_seed/versions/1').json()==fixture('checklist')
    new=config()
    original=copy.deepcopy(new)
    created=client.post('/api/v1/checklists',json=new)
    assert created.status_code==201
    id=created.json()['checklist_id']
    new['criteria'][0]['wording']='Replacement wording'
    result=client.put('/api/v1/checklists/'+id,json={'expected_version':1,'configuration':new})
    assert result.status_code==201 and result.json()['version']==2
    assert client.get(f'/api/v1/checklists/{id}/versions/1').json()['criteria']==original['criteria']
    assert client.put('/api/v1/checklists/'+id,json={'expected_version':1,'configuration':new}).status_code==409
    assert len(client.get(f'/api/v1/checklists/{id}/versions').json()['items'])==2
    assert client.delete(f'/api/v1/checklists/{id}?expected_version=2').status_code==204
    assert client.get(f'/api/v1/checklists/{id}/versions/1').status_code==200
    assert id not in [x['checklist_id'] for x in client.get('/api/v1/checklists').json()['items']]
    assert client.put('/api/v1/checklists/'+id,json={'expected_version':2,'configuration':new}).json()['error']['code']=='checklist_archived'


def test_invalid_configuration(client):
    for mutate in [
        lambda c:c['criteria'][0].update(weight=-1),
        lambda c:c['criteria'][0].update(section_id='missing'),
        lambda c:c['criteria'][0].update(na_allowed=True),
        lambda c:c['criteria'][3].update(maximum=25),
        lambda c:c['criteria'][5].update(allowed_numeric_values=[0,4,7,10,10]),
        lambda c:c['criteria'][7].update(weight=10),
        lambda c:c['criteria'].append(copy.deepcopy(c['criteria'][0])),
    ]:
        c=config();mutate(c)
        assert client.post('/api/v1/checklists',json=c).status_code==422


def test_replacement_criterion_configuration_needs_no_code_edit(client):
    new=config()
    new['criteria'][0].update(criterion_id='replaced_contact',answer_type='numeric',allowed_numeric_values=[0,1,3],maximum=3,
                             scale=[{'value':v,'wording':f'Configuration anchor {v}'} for v in [0,1,3]])
    r=client.put('/api/v1/checklists/checklist_seed',json=dict(expected_version=1,configuration=new))
    assert r.status_code==201 and r.json()['criteria'][0]['criterion_id']=='replaced_contact'
    assert r.json()['criteria'][0]['allowed_numeric_values']==[0,1,3]
    assert client.get('/api/v1/checklists/checklist_seed/versions/1').json()['criteria'][0]['criterion_id']=='c01'
