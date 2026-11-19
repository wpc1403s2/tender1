from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from typing import List
from urllib.parse import quote
import uuid

from app.services.parser_service import DocumentParserService
from app.schemas.document_schema import ProjectMemoryStore
from app.services.extraction_service import DeepSeekExtractionService

router = APIRouter(prefix="/api/v1/tender", tags=["Tender Preprocessing"])

@router.post("/upload", summary="上传标书文件包并执行预处理入库")
async def upload_and_preprocess_tender(
    project_id: str = None,
    files: List[UploadFile] = File(...)
):
    if not project_id:
        project_id = f"proj_{uuid.uuid4().hex[:8]}"

    files_data = []
    for file in files:
        content = await file.read()
        files_data.append((file.filename, content))

    memory_store: ProjectMemoryStore = await DocumentParserService.process_upload_Batch(
        project_id=project_id,
        files_data=files_data
    )

    summary = [
        {
            "doc_id": doc.doc_id,
            "file_name": doc.file_name,
            "category": doc.category.value,
            "total_pages": doc.total_pages,
            "blocks_count": len(doc.blocks),
            # 动态拼装后端 PDF 文件流 URL
            "file_url": f"/api/v1/tender/{project_id}/files/{quote(doc.file_name)}"
        }
        for doc in memory_store.documents.values()
    ]

    return {
        "code": 200,
        "message": "标书多源文档预处理完成",
        "data": {
            "project_id": project_id,
            "documents_summary": summary
        }
    }


@router.get("/{project_id}/files/{file_name}", summary="获取已上传的原始 PDF 文件流供前端预览")
async def get_uploaded_pdf_stream(project_id: str, file_name: str):
    file_path = DocumentParserService.get_uploaded_file_path(project_id, file_name)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件未找到: {file_name}")

    media_type = "application/pdf" if file_name.lower().endswith(".pdf") else "application/octet-stream"
    return FileResponse(path=file_path, media_type=media_type, filename=file_name)


# 在 app/api/v1/tender.py 顶部新增导入：

# 将 @router.get("/{project_id}/review") 接口替换为以下代码：
@router.get("/{project_id}/review", summary="获取项目文档列表及 DeepSeek 真实提取结果")
async def get_project_review_data(project_id: str, force_refresh: bool = False):
    memory = DocumentParserService.get_project_memory(project_id)
    if not memory:
        raise HTTPException(status_code=404, detail="未找到该项目的内存数据，请先上传标书")

    # 如果尚未执行过 DeepSeek 提取（或前端传入 force_refresh=true），则调用 DeepSeek 实时提取
    if not memory.extracted_main_parameters or force_refresh:
        try:
            await DeepSeekExtractionService.run_full_extraction(memory)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DeepSeek 参数提取失败: {str(e)}")

    documents = [
        {
            "doc_id": doc.doc_id,
            "file_name": doc.file_name,
            "category": doc.category.value,
            "total_pages": doc.total_pages,
            "blocks_count": len(doc.blocks),
            "file_url": f"/api/v1/tender/{project_id}/files/{quote(doc.file_name)}"
        }
        for doc in memory.documents.values()
    ]

    return {
        "code": 200,
        "data": {
            "project_id": project_id,
            "project_name": f"变压器招标解析项目 ({project_id})",
            "status": "MATCHED",
            "documents": documents,
            "main_parameters": memory.extracted_main_parameters,
            "components": memory.extracted_components
        }
    }