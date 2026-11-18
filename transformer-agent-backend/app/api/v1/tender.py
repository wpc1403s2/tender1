import json
import uuid
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse

from app.core.config import BACKEND_ROOT
from app.services.parser_service import DocumentParserService
from app.services.extraction_service import JOBS, TASKS, start_extraction, annotate_table_warnings

router = APIRouter(prefix='/api/v1/tender', tags=['Tender'])


def result_path(project_id):
    DocumentParserService.get_uploaded_file_path(project_id, 'placeholder')
    return BACKEND_ROOT / 'data/extractions' / f'{project_id}.json'


async def project_memory(project_id):
    try:
        memory = await DocumentParserService.restore_project(project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if memory is None:
        raise HTTPException(404, '项目不存在，请先上传标书')
    return memory


def document_summaries(memory):
    return [dict(doc_id=d.doc_id, file_name=d.file_name, category=d.category.value,
                 total_pages=d.total_pages, blocks_count=len(d.blocks),
                 file_url=f'/api/v1/tender/{memory.project_id}/files/{quote(d.file_name)}')
            for d in memory.documents.values()]


@router.post('/upload', summary='上传并预处理标书')
async def upload_and_preprocess_tender(files: List[UploadFile] = File(...), project_id: str = Form(None)):
    project_id = project_id or f'proj_{uuid.uuid4().hex[:8]}'
    if project_id in TASKS:
        raise HTTPException(409, '项目正在提取，请完成后再上传')
    try:
        path = result_path(project_id)
        path.unlink(missing_ok=True)
        JOBS.pop(project_id, None)
        memory = await DocumentParserService.process_upload_Batch(
            project_id, [(file.filename, await file.read()) for file in files])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return dict(code=200, message='标书预处理完成', data=dict(
        project_id=project_id, documents_summary=document_summaries(memory)))


@router.get('/{project_id}/files/{file_name}', summary='读取原始文档')
async def get_uploaded_pdf_stream(project_id: str, file_name: str):
    try:
        path = DocumentParserService.get_uploaded_file_path(project_id, file_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not path.is_file():
        raise HTTPException(404, '文件未找到')
    return FileResponse(path, media_type='application/pdf' if path.suffix.lower() == '.pdf' else 'application/octet-stream', filename=file_name)


@router.post('/{project_id}/analyze', summary='启动 DeepSeek 参数提取')
async def analyze_project(project_id: str, force: bool = False):
    memory = await project_memory(project_id)
    path = result_path(project_id)
    if project_id not in TASKS and (force or not path.exists()):
        try:
            start_extraction(memory, path)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    return await get_project_review_data(project_id)


@router.get('/{project_id}/review', summary='读取文档、提取进度和真实参数')
async def get_project_review_data(project_id: str):
    memory = await project_memory(project_id)
    state = JOBS.get(project_id)
    path = result_path(project_id)
    if state is None:
        state = dict(status='READY', main_parameters=[], extraction_error=None)
        if path.exists():
            state.update(status='EXTRACTED', main_parameters=json.loads(path.read_text(encoding='utf-8')))
    annotate_table_warnings(state['main_parameters'], memory)
    return dict(code=200, data=dict(project_id=project_id,
        project_name=f'变压器招标解析项目 ({project_id})', documents=document_summaries(memory),
        components=[], **state))
