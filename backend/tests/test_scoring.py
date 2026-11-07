import copy
import pytest
from app.scoring import calculate, InvalidJudgment
from conftest import fixture


def inputs():
    return fixture('checklist'), fixture('evaluation-original')['original_ai_result']['judgments'], fixture('conversation')


def test_seed_score_na_and_gross_error_separate():
    c,j,conv=inputs()
    result=calculate(c,j,conv)
    assert result['total']==92.31 and result['applicable_weight']==65
    assert result['scores'][1]['points'] is None
    j[-1]['answer']='yes'
    gross=calculate(c,j,conv)
    assert gross['gross_error'] is True and gross['total']==result['total']
    assert gross['scores'][-1]['points'] is None
    assert sum(s['maximum'] or 0 for s in result['sections'])==pytest.approx(100)


def test_zero_denominator_and_zero_is_not_null():
    c,j,conv=inputs()
    for criterion in c['criteria']:
        criterion['weight']=0
    assert calculate(c,j,conv)['total'] is None
    c['criteria'][0]['weight']=10
    j[0]['answer']='no'
    assert calculate(c,j,conv)['total']==0


@pytest.mark.parametrize('change',[
    lambda j:j[0].update(criterion_id='unknown'),
    lambda j:j.append(copy.deepcopy(j[0])),
    lambda j:j.pop(),
    lambda j:j[0].update(answer='na'),
    lambda j:j[3].update(numeric_value=17),
    lambda j:j[3].update(answer='yes',numeric_value=None),
    lambda j:j[0]['evidence'].update(message_ids=['unknown']),
    lambda j:j[0]['evidence'].update(message_ids=[],inspected_ranges=[]),
    lambda j:j[6]['evidence']['inspected_ranges'][0].update(start_message_id='msg_demo_4',end_message_id='msg_demo_1'),
    lambda j:j[0].update(numeric_value=True),
])
def test_invalid_judgments_and_evidence(change):
    c,j,conv=inputs();change(j)
    with pytest.raises(InvalidJudgment):calculate(c,j,conv)


def test_new_criterion_and_half_up():
    c,j,conv=inputs()
    c['criteria']=c['criteria'][:1]
    c['criteria'][0]['weight']=100
    # Any new saved criterion is handled without special cases by ID.
    new=copy.deepcopy(c['criteria'][0]);new.update(criterion_id='brand_new',weight=100)
    c['criteria'].append(new)
    j=j[:1]
    new_j=copy.deepcopy(j[0]);new_j.update(criterion_id='brand_new',answer='no');j.append(new_j)
    assert calculate(c,j,conv)['total']==50
    c['criteria'][0]['weight']=1
    c['criteria'][1]['weight']=31
    assert calculate(c,j,conv)['total']==3.13 # 3.125 must round half up


def test_all_na_no_applicable_weight_and_no_gross_criterion():
    c,j,conv=inputs()
    c['criteria']=[c['criteria'][1]]
    j=[j[1]]
    result=calculate(c,j,conv)
    assert result['total'] is None and result['total_unavailable_reason']=='no_applicable_weight'
    assert result['gross_error'] is None and all(s['points'] is None for s in result['sections'])
