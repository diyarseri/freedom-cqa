from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .config import Settings
from .db import Store
from .errors import APIError
from .models import ImportRequest, SourceRecord
from .organizer import import_group


def create_app(settings=None, *, organizer_transport=None, provider_transport=None):
    settings = settings or Settings.from_env()
    store = Store(settings.database_path)

    @asynccontextmanager
    async def lifespan(app):
        yield

    app = FastAPI(title='Freedom Broker CQA', version='1.0.0', lifespan=lifespan)
    app.state.store = store
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=['GET', 'POST', 'PUT', 'DELETE'], allow_headers=['Content-Type'])

    @app.middleware('http')
    async def request_policy(request, call_next):
        request.state.request_id = 'req_' + uuid4().hex
        allowed = {
            '/api/v1/conversations': {'group_id', 'language'},
            '/api/v1/evaluations': {'conversation_id'},
            '/api/v1/appeals': {'status'},
        }.get(request.url.path, set())
        if request.method == 'DELETE' and request.url.path.startswith('/api/v1/checklists/'):
            allowed = {'expected_version'}
        if any(k not in allowed for k in request.query_params) or any(len(request.query_params.getlist(k)) > 1 for k in request.query_params):
            return error_response(request, APIError(422, 'validation_error', 'Unknown or repeated query parameter.'))
        try:
            return await call_next(request)
        except Exception:
            # Do not include URLs, transcripts, exception strings or secrets.
            return error_response(request, APIError(500, 'internal_error', 'Internal server error.'))

    def error_response(request, exc):
        return JSONResponse(status_code=exc.status, content=dict(error=dict(code=exc.code, message=exc.message, details=exc.details),
                            request_id=getattr(request.state, 'request_id', 'req_' + uuid4().hex)))

    @app.exception_handler(APIError)
    async def api_error(request, exc):
        return error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        details = [dict(path='.'.join(str(x) for x in e['loc']), message=e['msg']) for e in exc.errors()]
        return error_response(request, APIError(422, 'validation_error', 'Request validation failed.', details))

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        codes = {404: 'not_found', 405: 'method_not_allowed'}
        return error_response(request, APIError(exc.status_code, codes.get(exc.status_code, 'validation_error'),
                              {404: 'Resource not found.', 405: 'Method not allowed.'}.get(exc.status_code, 'Request rejected.')))

    @app.post('/api/v1/conversations', status_code=201)
    def upload(body: SourceRecord, response: Response):
        with store.transaction() as db:
            doc, created = store.normalize(db, body, 'upload')
        response.status_code = 201 if created else 200
        return doc

    @app.get('/api/v1/conversations')
    def conversations(group_id: str | None = None, language: Literal['RU', 'KZ', 'EN'] | None = None):
        with store.transaction() as db:
            import json
            docs = [json.loads(r['document']) for r in db.execute('SELECT document FROM conversations ORDER BY seq')]
        return {'items': [d for d in docs if (group_id is None or d['source']['group_id'] == group_id) and (language is None or d['language'] == language)]}

    @app.get('/api/v1/conversations/{id}')
    def conversation(id: str):
        with store.transaction() as db:
            return store.get(db, 'conversations', id)

    @app.post('/api/v1/dataset-imports', status_code=201)
    def dataset_import(body: ImportRequest):
        return import_group(store, settings, body.group_id, organizer_transport)

    return app
