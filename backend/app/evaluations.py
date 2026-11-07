import asyncio
import copy
import json

from . import checklists
from .db import dump, new_id
from .errors import APIError
from .provider import OpenAIProvider, ProviderFailure, now
from .scoring import calculate


class Evaluator:
    """Single-process prototype queue; persisted attempts survive restarts."""
    def __init__(self, store, settings, transport=None):
        self.store, self.settings = store, settings
        self.provider = OpenAIProvider(settings, transport)
        self.queue = asyncio.Queue()
        self.workers = []

    def interrupt_incomplete(self):
        # Interrupted work fails visibly; never replay a possibly billed call automatically.
        with self.store.transaction() as db:
            for row in db.execute('SELECT document FROM evaluations').fetchall():
                doc = json.loads(row['document'])
                if doc['status'] in ('queued','running'):
                    doc.update(status='failed', completed_at=now())
                    doc['provider']['error'] = dict(code='provider_unavailable', message='Evaluation interrupted by server restart; submit a new attempt.', retryable=True)
                    self.store.save(db,'evaluations',doc,'evaluation_id')

    async def start(self):
        self.interrupt_incomplete()
        self.workers = [asyncio.create_task(self.worker()) for _ in range(2)]

    async def stop(self):
        for w in self.workers:
            w.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.interrupt_incomplete()

    def create(self, request):
        with self.store.transaction() as db:
            self.store.get(db,'conversations',request.conversation_id)
            checklists.head(db,request.checklist_id,active=True)
            checklists.version(db,request.checklist_id,request.checklist_version)
            doc = dict(evaluation_id=new_id('eval'),conversation_id=request.conversation_id,
                       checklist_id=request.checklist_id,checklist_version=request.checklist_version,
                       status='queued',provider=dict(name=self.provider.name,model=self.settings.provider_model,error=None),
                       created_at=now(),completed_at=None,revision=1,original_ai_result=None,appeals=[],final_result=None)
            db.execute('INSERT INTO evaluations(id,conversation_id,checklist_id,checklist_version,document) VALUES(?,?,?,?,?)',
                       (doc['evaluation_id'],request.conversation_id,request.checklist_id,request.checklist_version,dump(doc)))
        self.queue.put_nowait(doc['evaluation_id'])
        return doc

    async def worker(self):
        while True:
            id = await self.queue.get()
            try:
                await self.run(id)
            finally:
                self.queue.task_done()

    async def run(self, id):
        with self.store.transaction() as db:
            doc = self.store.get(db,'evaluations',id)
            conversation = self.store.get(db,'conversations',doc['conversation_id'])
            checklist = checklists.version(db,doc['checklist_id'],doc['checklist_version'])
            doc['status'] = 'running'
            self.store.save(db,'evaluations',doc,'evaluation_id')

        def audit(record):
            with self.store.transaction() as db:
                db.execute('INSERT INTO provider_calls(evaluation_id,document) VALUES(?,?)', (id,dump(record)))
        try:
            judgments = await self.provider.evaluate(checklist, conversation, audit)
            result = calculate(checklist,judgments,conversation)
            doc.update(status='succeeded',original_ai_result=result,final_result=copy.deepcopy(result))
        except ProviderFailure as exc:
            doc['status'] = 'failed'
            doc['provider']['error'] = exc.error
        except asyncio.CancelledError:
            doc['status'] = 'failed'
            doc['provider']['error'] = dict(code='provider_unavailable',message='Evaluation interrupted; submit a new attempt.',retryable=True)
            raise
        except Exception:
            doc['status'] = 'failed'
            doc['provider']['error'] = dict(code='provider_invalid_output',message='Evaluation could not be validated or calculated.',retryable=False)
        finally:
            doc['completed_at'] = now()
            with self.store.transaction() as db:
                self.store.save(db,'evaluations',doc,'evaluation_id')
