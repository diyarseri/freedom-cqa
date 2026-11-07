"""Server-only GET adapter. Never log the signed upstream URL or response."""
import asyncio
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from pydantic import ValidationError

from .errors import APIError
from .models import SourceRecord


def dataset_url(url, group_id):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise APIError(503, 'organizer_not_configured', 'Configure a valid HTTPS organizer URL server-side.')
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != 'group_id']
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query + [('group_id', group_id)]), ''))


async def import_group(store, settings, group_id, transport=None):
    if not settings.organizer_url:
        raise APIError(503, 'organizer_not_configured', 'Configure ORGANIZER_DATASET_URL server-side.')
    url = dataset_url(settings.organizer_url, group_id)
    try:
        # No automatic retries or redirects: do not replay or disclose signed URLs.
        async with asyncio.timeout(settings.organizer_timeout):
            async with httpx.AsyncClient(timeout=settings.organizer_timeout, transport=transport, follow_redirects=False) as client:
                response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('isSuccess') is not True:
            raise ValueError('Unsuccessful response')
        data = payload['data']
        if not isinstance(data, dict) or data['dataset_group_id'] != group_id:
            raise ValueError('Group mismatch')
        if type(data['total_records']) is not int or not isinstance(data['records'], list) or data['total_records'] != len(data['records']):
            raise ValueError('Count mismatch')
        records = [SourceRecord.model_validate(r) for r in data['records']]
        if len({r.conversation_id for r in records}) != len(records):
            raise ValueError('Duplicate source IDs')
    except (TimeoutError, httpx.TimeoutException):
        raise APIError(504, 'organizer_timeout', 'Organizer request timed out.') from None
    except (httpx.HTTPError, ValueError, KeyError, TypeError, ValidationError):
        raise APIError(502, 'organizer_failure', 'Organizer response failed validation or was unavailable.') from None
    with store.transaction() as db:
        normalized = [store.normalize(db, r, 'dataset', group_id) for r in records]
    return dict(group_id=group_id, imported=sum(created for _, created in normalized),
                unchanged=sum(not created for _, created in normalized),
                conversation_ids=[d['conversation_id'] for d, _ in normalized])
