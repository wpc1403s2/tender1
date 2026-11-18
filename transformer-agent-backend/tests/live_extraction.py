"""Manual integration check: python -m tests.live_extraction PROJECT_ID.

Calls the configured DeepSeek service and caches the resulting real parameters.
"""
import asyncio
import sys
import httpx

from app.main import app
from app.services.extraction_service import TASKS, JOBS
from app.services.parser_service import DocumentParserService


async def main(project_id):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post(f'/api/v1/tender/{project_id}/analyze', params={'force': '--force' in sys.argv})
        response.raise_for_status()
        task = TASKS.get(project_id)
        if task:
            await task
        response = await client.get(f'/api/v1/tender/{project_id}/review')
        response.raise_for_status()
        data = response.json()['data']
        if data['status'] == 'EXTRACTED':
            JOBS.clear()
            DocumentParserService._memory_store.clear()
            recovered = await client.get(f'/api/v1/tender/{project_id}/review')
            recovered.raise_for_status()
            assert recovered.json()['data']['main_parameters'] == data['main_parameters']
            print('HTTP endpoints and disk recovery: OK')
    print('status:', data['status'])
    if data.get('extraction_error'):
        print(data['extraction_error'])
        raise SystemExit(1)
    rows = data['main_parameters']
    print('fields:', len(rows), 'with_evidence:', sum(bool(row['source_ref']) for row in rows))
    print('needs_review:', sum(bool(row.get('evidence_warning')) for row in rows))
    for prefix in ('1.1 ', '1.2 ', '1.3 ', '1.8 '):
        row = next(r for r in rows if r['param_key'].startswith(prefix))
        print(row['param_key'], ':', row['param_value'], 'page:', (row['source_ref'] or {}).get('page_number'))


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1]))
