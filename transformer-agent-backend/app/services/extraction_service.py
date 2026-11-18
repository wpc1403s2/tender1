"""Background extraction for the current single-process deployment."""
import asyncio
import json
import re
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from app.agents.prompts import EXTRACTION_PROMPT
from app.core.config import settings

FIELDS = json.loads((Path(__file__).parents[1] / 'schemas/extraction_fields.json').read_text(encoding='utf-8'))
JOBS: dict[str, dict] = {}
TASKS: dict[str, asyncio.Task] = {}


class Evidence(BaseModel):
    field_id: str
    value: str
    source_id: str
    quote: str


class ExtractionResponse(BaseModel):
    items: list[Evidence] = Field(default_factory=list)


def normalize(text):
    return re.sub(r'\s+', '', text).casefold()


def build_sources(memory, limit=30000):
    sources, chunks, current, size = {}, [], [], 0
    for doc in memory.documents.values():
        for block in doc.blocks:
            # Split oversized tables without silently dropping the document tail.
            for start in range(0, len(block.content), limit - 1000):
                content = block.content[start:start + limit - 1000]
                if not content.strip():
                    continue
                sid = f's{len(sources)}'
                sources[sid] = (doc, block, content)
                entry = {'source_id': sid, 'file': doc.file_name, 'text': content}
                length = len(json.dumps(entry, ensure_ascii=False))
                if current and size + length > limit:
                    chunks.append(current)
                    current, size = [], 0
                current.append(entry)
                size += length
    if current:
        chunks.append(current)
    return sources, chunks


def assemble_rows(items, sources):
    grouped = {field['id']: [] for field in FIELDS}
    for item in items:
        if normalize(item.value).strip('。.;；') in {'未提及', '未明确', '未说明', '未找到', 'n/a', 'notmentioned', 'notspecified'}:
            continue
        if item.field_id not in grouped or item.source_id not in sources:
            raise ValueError('模型返回了未知字段或原文标识，请重试')
        doc, block, content = sources[item.source_id]
        if not item.value.strip() or not item.quote.strip() or normalize(item.quote) not in normalize(content):
            raise ValueError('模型返回的引用未通过原文校验，请重试')
        grouped[item.field_id].append((item, doc, block))
    rows = []
    for field in FIELDS:
        matches = grouped[field['id']]
        refs, values = [], []
        for item, doc, block in matches:
            if item.value not in values:
                values.append(item.value)
            ref = dict(doc_id=doc.doc_id, file_name=doc.file_name, page_number=block.page_number,
                       bbox=block.bbox, original_text=item.quote)
            if ref not in refs:
                refs.append(ref)
        rows.append(dict(param_key=field['label'], param_value='；\n'.join(values) if values else '未提及',
                         original_text='\n'.join(r['original_text'] for r in refs),
                         source_ref=refs[0] if refs else None, source_refs=refs))
    return rows


def annotate_table_warnings(rows, memory):
    """Expose known parser ambiguity; never silently repair numeric source data."""
    ambiguous = set()
    for doc in memory.documents.values():
        for block in doc.blocks:
            if block.block_type == 'table' and re.search(r'\|\s*[.。]\s*\|', block.content):
                ambiguous.add((doc.doc_id, block.page_number, tuple(block.bbox or ())))
    for row in rows:
        for ref in row.get('source_refs', []):
            if (ref.get('doc_id'), ref['page_number'], tuple(ref.get('bbox') or ())) in ambiguous:
                row['evidence_warning'] = '原文表格存在独立小数点单元格，请对照 PDF 核验数值'
                break


async def request_chunk(client, chunk, correction=None):
    response = await client.post(settings.deepseek_base_url.rstrip('/') + '/chat/completions',
        headers={'Authorization': 'Bearer ' + settings.deepseek_api_key.get_secret_value()},
        json={'model': settings.deepseek_model, 'stream': False, 'max_tokens': 8192,
              'thinking': {'type': 'disabled'},
              'response_format': {'type': 'json_object'},
              'messages': [{'role': 'system', 'content': EXTRACTION_PROMPT},
                           {'role': 'user', 'content': json.dumps({'fields': FIELDS, 'sources': chunk,
                             'correction': correction}, ensure_ascii=False)}]})
    response.raise_for_status()
    choice = response.json()['choices'][0]
    if choice.get('finish_reason') != 'stop':
        raise ValueError('模型输出未完整结束，请重试或使用更小的文档')
    return ExtractionResponse.model_validate_json(choice['message']['content']).items


async def run_extraction(memory, result_path):
    job = JOBS[memory.project_id]
    try:
        sources, chunks = build_sources(memory)
        if not chunks:
            raise ValueError('文档没有可提取文本；扫描件请先配置 OCR 后重新上传')
        job['total_chunks'] = len(chunks)
        items = []
        unverified = set()
        async with httpx.AsyncClient(timeout=httpx.Timeout(240, connect=20)) as client:
            for index, chunk in enumerate(chunks):
                batch = await request_chunk(client, chunk)
                chunk_sources = {entry['source_id']: sources[entry['source_id']] for entry in chunk}
                invalid = []
                for item in batch:
                    try:
                        assemble_rows([item], chunk_sources)
                        items.append(item)
                    except ValueError:
                        invalid.append(item)
                if invalid:
                    repaired = await request_chunk(client, chunk, {
                        'instruction': '仅修复以下条目的引用，引用必须是一个 source_id 对应文本中的连续原文。无法找到依据的不要输出。不要重复其他已提取字段。',
                        'invalid_items': [item.model_dump() for item in invalid],
                    })
                    repaired_fields = set()
                    for item in repaired:
                        try:
                            assemble_rows([item], chunk_sources)
                            if normalize(item.value) != '未提及':
                                items.append(item)
                                repaired_fields.add(item.field_id)
                        except ValueError:
                            pass
                    unverified.update(item.field_id for item in invalid if item.field_id not in repaired_fields)
                job['completed_chunks'] = index + 1
        rows = assemble_rows(items, sources)
        for field, row in zip(FIELDS, rows):
            if field['id'] in unverified:
                row['evidence_warning'] = '部分模型引用未通过原文校验，请人工核验此字段'
                if row['source_ref'] is None:
                    row['param_value'] = '待核验'
        annotate_table_warnings(rows, memory)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = result_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        temporary.replace(result_path)
        job.update(status='EXTRACTED', main_parameters=rows, extraction_error=None)
    except httpx.HTTPStatusError as exc:
        job.update(status='FAILED', extraction_error=f'DeepSeek 请求失败（HTTP {exc.response.status_code}），请检查模型、密钥、额度和服务地址')
    except httpx.RequestError:
        job.update(status='FAILED', extraction_error='DeepSeek 连接失败或超时，请检查网络后重试')
    except ValueError as exc:
        # Pydantic errors may contain raw model output, so do not expose them.
        message = str(exc) if type(exc) is ValueError else '模型返回的数据格式不正确，请重试'
        job.update(status='FAILED', extraction_error=message)
    except Exception:
        job.update(status='FAILED', extraction_error='提取失败，请检查服务配置或重试')
    finally:
        TASKS.pop(memory.project_id, None)


def start_extraction(memory, result_path):
    if memory.project_id in TASKS:
        return
    if not settings.deepseek_api_key.get_secret_value():
        raise ValueError('请在后端 .env 中配置 DEEPSEEK_API_KEY')
    JOBS[memory.project_id] = dict(status='EXTRACTING', main_parameters=[], extraction_error=None,
                                  completed_chunks=0, total_chunks=0)
    TASKS[memory.project_id] = asyncio.create_task(run_extraction(memory, result_path))
