"""Local operator-only usage summary; deliberately not a new public API route."""
import argparse
import json
import sqlite3
from pathlib import Path


def summary(database, evaluation_id):
    db=sqlite3.connect(f'file:{Path(database).resolve()}?mode=ro',uri=True)
    try:
        calls=[json.loads(r[0]) for r in db.execute('SELECT document FROM provider_calls WHERE evaluation_id=? ORDER BY seq',(evaluation_id,))]
    finally:
        db.close()
    known=[c.get('estimated_cost_usd') for c in calls]
    return dict(evaluation_id=evaluation_id,calls=[{k:c.get(k) for k in (
        'attempt','kind','model_requested','model_returned','outcome','request_id','usage','estimated_cost_usd')} for c in calls],
        estimated_cost_usd=sum(known) if known and all(v is not None for v in known) else None,
        cost_complete=bool(known) and all(v is not None for v in known))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Private local model usage/cost summary; never prints transcripts or credentials.')
    parser.add_argument('evaluation_id')
    parser.add_argument('--database',default='backend/data/cqa.sqlite3')
    args=parser.parse_args()
    print(json.dumps(summary(args.database,args.evaluation_id),indent=2))
