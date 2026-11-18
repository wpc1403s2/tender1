import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import SecretStr

from app.schemas.document_schema import ContentBlock, ParsedDocument, ProjectMemoryStore, DocCategory
from app.services import extraction_service as service


def sample_memory():
    doc = ParsedDocument(doc_id='doc1', file_name='spec.pdf', file_ext='.pdf',
        category=DocCategory.TECHNICAL_SPEC, total_pages=2,
        blocks=[ContentBlock(block_id='b1', page_number=2, content='Number of phases: 3', bbox=(10, 20, 30, 40))])
    return ProjectMemoryStore(project_id='test_project', documents={'doc1': doc})


class EvidenceTests(unittest.TestCase):
    def test_real_source_and_missing_fields(self):
        sources, _ = service.build_sources(sample_memory())
        evidence = service.Evidence(field_id='1.1', value='三相', source_id='s0', quote='Number of phases: 3')
        rows = service.assemble_rows([evidence], sources)
        row = next(row for row in rows if row['param_key'].startswith('1.1 '))
        self.assertEqual(row['param_value'], '三相')
        self.assertEqual(row['source_ref']['page_number'], 2)
        self.assertEqual(row['source_ref']['bbox'], (10, 20, 30, 40))
        self.assertEqual(len(rows), 84)
        missing = next(row for row in rows if row['param_key'].startswith('1.2 '))
        self.assertEqual(missing['param_value'], '未提及')
        self.assertIsNone(missing['source_ref'])

    def test_hallucinated_quote_and_source_rejected(self):
        sources, _ = service.build_sources(sample_memory())
        for source_id, quote in [('fake', 'Number of phases: 3'), ('s0', 'Voltage: 220 kV')]:
            with self.assertRaises(ValueError):
                service.assemble_rows([service.Evidence(field_id='1.1', value='3', source_id=source_id, quote=quote)], sources)

    def test_large_block_is_not_truncated(self):
        memory = sample_memory()
        memory.documents['doc1'].blocks[0].content = 'A' * 70000 + 'FINAL_REQUIREMENT'
        sources, chunks = service.build_sources(memory)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(''.join(source[2] for source in sources.values()), memory.documents['doc1'].blocks[0].content)

    def test_missing_value_from_one_chunk_does_not_override_evidence(self):
        sources, _ = service.build_sources(sample_memory())
        items = [service.Evidence(field_id='1.1', value=value, source_id='s0', quote='Number of phases: 3')
                 for value in ('3', '未提及')]
        row = next(r for r in service.assemble_rows(items, sources) if r['param_key'].startswith('1.1 '))
        self.assertEqual(row['param_value'], '3')

    def test_split_decimal_table_is_flagged(self):
        memory = sample_memory()
        block = memory.documents['doc1'].blocks[0]
        block.block_type = 'table'
        block.content = '| Temperature | 287 |\n| 温度 | . |'
        sources, _ = service.build_sources(memory)
        rows = service.assemble_rows([service.Evidence(field_id='26', value='287', source_id='s0', quote='| Temperature | 287 |')], sources)
        service.annotate_table_warnings(rows, memory)
        row = next(r for r in rows if r['param_key'].startswith('26.'))
        self.assertIn('小数点', row['evidence_warning'])
        self.assertEqual(row['param_value'], '287')


class JobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        key_patch = patch.object(service.settings, 'deepseek_api_key', SecretStr('test-only-key'))
        key_patch.start()
        self.addCleanup(key_patch.stop)

    async def asyncTearDown(self):
        service.JOBS.clear()
        service.TASKS.clear()

    async def test_success_persists_and_duplicate_start_reuses_task(self):
        memory = sample_memory()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'result.json'
            evidence = service.Evidence(field_id='1.1', value='3', source_id='s0', quote='Number of phases: 3')
            with patch.object(service, 'request_chunk', AsyncMock(return_value=[evidence])) as request:
                service.start_extraction(memory, path)
                task = service.TASKS[memory.project_id]
                service.start_extraction(memory, path)
                self.assertIs(service.TASKS[memory.project_id], task)
                await task
                request.assert_awaited_once()
            self.assertEqual(service.JOBS[memory.project_id]['status'], 'EXTRACTED')
            self.assertEqual(len(json.loads(path.read_text(encoding='utf-8'))), 84)

    async def test_network_failure_does_not_save_fake_results(self):
        memory = sample_memory()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'result.json'
            with patch.object(service, 'request_chunk', AsyncMock(side_effect=httpx.ConnectError('secret message'))):
                service.start_extraction(memory, path)
                await service.TASKS[memory.project_id]
            state = service.JOBS[memory.project_id]
            self.assertEqual(state['status'], 'FAILED')
            self.assertNotIn('secret', state['extraction_error'])
            self.assertFalse(path.exists())

    async def test_request_contract_and_truncated_output(self):
        def respond(request):
            body = json.loads(request.content)
            self.assertEqual(body['response_format'], {'type': 'json_object'})
            self.assertEqual(body['model'], service.settings.deepseek_model)
            return httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': '{'}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaisesRegex(ValueError, '未完整结束'):
                await service.request_chunk(client, [])

    async def test_missing_configuration_does_not_start_job(self):
        with patch.object(service.settings, 'deepseek_api_key', SecretStr('')):
            with self.assertRaisesRegex(ValueError, 'DEEPSEEK_API_KEY'):
                service.start_extraction(sample_memory(), Path('unused.json'))
        self.assertFalse(service.TASKS)

    async def test_unverified_quote_is_flagged_without_fake_bbox(self):
        memory = sample_memory()
        bad = service.Evidence(field_id='1.1', value='3', source_id='s0', quote='fabricated quote')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'result.json'
            with patch.object(service, 'request_chunk', AsyncMock(side_effect=[[bad], []])):
                service.start_extraction(memory, path)
                await service.TASKS[memory.project_id]
            row = next(r for r in service.JOBS[memory.project_id]['main_parameters'] if r['param_key'].startswith('1.1 '))
            self.assertEqual(row['param_value'], '待核验')
            self.assertIsNone(row['source_ref'])
            self.assertTrue(row['evidence_warning'])


if __name__ == '__main__':
    unittest.main()
