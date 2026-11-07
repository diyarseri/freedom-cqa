"""Opt-in real-provider verification; regular tests make no external paid calls."""
import os
from dataclasses import replace

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from pathlib import Path

from app.config import Settings
from app.main import create_app
from test_evaluations import submit


@pytest.mark.skipif(os.getenv('RUN_LIVE_MODEL_TEST')!='1',reason='Set RUN_LIVE_MODEL_TEST=1 to spend tokens on a real provider call')
def test_live_provider(tmp_path):
    load_dotenv(Path(__file__).resolve().parents[1]/'.env',override=False)
    settings=replace(Settings.from_env(),database_path=str(tmp_path/'live.sqlite3'))
    assert settings.provider_api_key,'Configure OPENAI_API_KEY server-side; no mock fallback'
    # Live calls have a longer poll budget than zero-latency deterministic transports.
    from conftest import fixture
    import time
    with TestClient(create_app(settings)) as c:
        conv=c.post('/api/v1/conversations',json=fixture('upload-request')).json()
        ev=c.post('/api/v1/evaluations',json=dict(conversation_id=conv['conversation_id'],checklist_id='checklist_seed',checklist_version=1)).json()
        deadline=time.monotonic()+140
        while ev['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(.25)
            ev=c.get('/api/v1/evaluations/'+ev['evaluation_id']).json()
        assert ev['status']=='succeeded',ev['provider']['error']
        assert len(ev['final_result']['judgments'])==8
