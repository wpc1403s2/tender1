from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List
import uuid

from app.services.parser_service import DocumentParserService
from app.schemas.document_schema import ProjectMemoryStore

router = APIRouter(prefix="/api/v1/tender", tags=["Tender Preprocessing"])

@router.post("/upload", summary="上传标书文件包并执行预处理入库")
async def upload_and_preprocess_tender(
    project_id: str = None,
    files: List[UploadFile] = File(..., description="支持上传 PDF, Word, Excel 或 ZIP 压缩包")
):
    if not project_id:
        project_id = f"proj_{uuid.uuid4().hex[:8]}"

    files_data = []
    for file in files:
        content = await file.read()
        files_data.append((file.filename, content))

    try:
        # 执行异步解析并存入内存
        memory_store: ProjectMemoryStore = await DocumentParserService.process_upload_Batch(
            project_id=project_id,
            files_data=files_data
        )
        
        # 统计分类情况返回给前端看板
        summary = [
            {
                "doc_id": doc.doc_id,
                "file_name": doc.file_name,
                "category": doc.category.value,
                "total_pages": doc.total_pages,
                "blocks_count": len(doc.blocks)
            }
            for doc in memory_store.documents.values()
        ]

        return {
            "code": 200,
            "message": "标书多源文档预处理完成，已载入内存",
            "data": {
                "project_id": project_id,
                "documents_summary": summary
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档预处理失败: {str(e)}")


@router.get("/{project_id}/memory", summary="查看内存中的文档解析结果与BBox坐标")
async def get_project_memory_data(project_id: str):
    memory = DocumentParserService.get_project_memory(project_id)
    if not memory:
        raise HTTPException(status_code=404, detail="未找到该项目的内存数据")
    return {
        "code": 200,
        "data": memory.model_dump()
    }