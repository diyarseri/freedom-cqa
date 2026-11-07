"""Exercise a running backend with synthetic data and a REAL provider call.

Run from repo root: backend/.venv/bin/python backend/scripts/smoke.py
No mock mode. Nonzero exit on provider failure. A successful run consumes tokens.
"""
import argparse
import copy
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx


def run(base_url, new_criterion=False):
    fixtures=Path(__file__).resolve().parents[2]/'fixtures'
    with httpx.Client(base_url=base_url.rstrip('/'),timeout=20) as client:
        def request(method,path,body=None):
            response=client.request(method,path,json=body)
            if response.status_code>=400:
                raise RuntimeError(f'Backend HTTP {response.status_code}; inspect normalized error in local API docs.')
            return response.json()
        seed=request('GET','/api/v1/checklists/checklist_seed/versions/1')
        selected=seed
        if new_criterion:
            config={k:copy.deepcopy(seed[k]) for k in ('name','sections','criteria')}
            extra=copy.deepcopy(config['criteria'][0])
            extra.update(criterion_id='smoke_new_'+uuid4().hex,wording='The operator does not ask for private credentials when giving general tariff navigation.',weight=5)
            config['criteria'].append(extra)
            selected=request('POST','/api/v1/checklists',config)
        upload=json.loads((fixtures/'upload-request.json').read_text(encoding='utf-8'))
        upload['conversation_id']='live-smoke-'+uuid4().hex
        conv=request('POST','/api/v1/conversations',upload)
        ev=request('POST','/api/v1/evaluations',dict(conversation_id=conv['conversation_id'],checklist_id=selected['checklist_id'],checklist_version=selected['version']))
        deadline=time.monotonic()+150
        while ev['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(.25)
            ev=request('GET','/api/v1/evaluations/'+ev['evaluation_id'])
        if ev['status']!='succeeded':
            code=(ev['provider']['error'] or {}).get('code','poll_deadline')
            raise RuntimeError(f'Evaluation {ev["evaluation_id"]} did not succeed: {code}. No score accepted.')
        assert ev['original_ai_result']==ev['final_result']
        assert {j['criterion_id'] for j in ev['final_result']['judgments']}=={c['criterion_id'] for c in selected['criteria']}
        appeal=request('POST','/api/v1/evaluations/'+ev['evaluation_id']+'/appeals',dict(expected_revision=1,criterion_id=selected['criteria'][0]['criterion_id'],comment='Synthetic smoke-test review: verify preservation and confirmation.'))
        pending=request('GET','/api/v1/evaluations/'+ev['evaluation_id'])
        assert pending['final_result']==ev['final_result']
        final=request('POST','/api/v1/appeals/'+appeal['appeal_id']+'/decision',dict(expected_revision=2,action='confirm',reason='Smoke-test confirmation of original judgment; no score change requested.',replacement=None))
        assert final['original_ai_result']==ev['original_ai_result'] and final['final_result']==ev['final_result']
        return dict(evaluation_id=ev['evaluation_id'],status=final['status'],model=ev['provider']['model'],checklist_version=ev['checklist_version'],
                    criteria=len(ev['final_result']['judgments']),total=final['final_result']['total'],review_revision=final['revision'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--new-criterion',action='store_true')
    args=parser.parse_args()
    try:
        print(json.dumps(run(args.base_url,args.new_criterion),indent=2))
    except (RuntimeError,httpx.HTTPError,AssertionError) as exc:
        # Connection exception strings can contain URLs. Print only our safe status text.
        print(str(exc) if isinstance(exc,RuntimeError) else 'Smoke test failed: connection or invariant error.')
        raise SystemExit(1)
