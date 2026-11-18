from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from typing import List
from urllib.parse import quote
import uuid

from app.services.parser_service import DocumentParserService
from app.schemas.document_schema import ProjectMemoryStore

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


@router.get("/{project_id}/review", summary="获取项目文档列表及提取匹配结果")
async def get_project_review_data(project_id: str):
    memory = DocumentParserService.get_project_memory(project_id)
    if not memory:
        raise HTTPException(status_code=404, detail="未找到该项目的内存数据，请先上传标书")

    # 1. 组装真实上传的文档列表（仅把 PDF 或全部文档放入下拉列表，带真实 file_url）
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

    # 默认取第一个上传的 PDF 文档及其中真实提取出的第一个带坐标 Block 作为演示锚点
    pdf_docs = [d for d in memory.documents.values() if d.file_ext == '.pdf']
    first_pdf_name = pdf_docs[0].file_name if pdf_docs else (documents[0]["file_name"] if documents else "")
    sample_block = next((b for d in pdf_docs for b in d.blocks if b.bbox), None)

    return {
        "code": 200,
        "data": {
            "project_id": project_id,
            "project_name": f"变压器招标解析项目 ({project_id})",
            "status": "MATCHED",
            "documents": documents,
            "main_parameters": [
                {
                    "param_key": "1.1 变压器的相数",
                    "param_value": "3",
                    "original_text": sample_block.content[:80] if sample_block else "Number of phases: 3",
                    "source_ref": {
                        "file_name": first_pdf_name,
                        "page_number": sample_block.page_number if sample_block else 1,
                        "bbox": list(sample_block.bbox) if sample_block and sample_block.bbox else [72.0, 200.0, 480.0, 240.0]
                    }
                }
            ],
            "components": []
        }
    }