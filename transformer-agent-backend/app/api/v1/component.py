from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from typing import List, Optional

from app.schemas.tender_schema import COMPONENT_CATEGORIES, ComponentUpdatePayload
from app.services.vector_store import VectorStoreService
from app.models.library import DatabaseSessionManager

router = APIRouter(prefix="/api/v1/components", tags=["Component Library & Vector Store"])


@router.get("/categories", summary="获取支持的16大组部件分类字典")
async def get_component_categories():
    return {
        "code": 200,
        "data": COMPONENT_CATEGORIES
    }


@router.get("/", summary="查询组部件标准品列表（支持按品类与关键词筛选）")
async def list_library_components(
    category: Optional[str] = None,
    keyword: Optional[str] = None
):
    items = VectorStoreService.list_components(category=category, keyword=keyword)
    return {
        "code": 200,
        "data": {
            "total": len(items),
            "pgvector_enabled": DatabaseSessionManager.is_pgvector_enabled(),
            "items": items
        }
    }


@router.post("/upload-catalog", summary="上传供应商样册PDF/Word/Excel，由DeepSeek自动拆解多型号并向量化入库")
async def upload_and_parse_catalog(
    files: List[UploadFile] = File(...),
    default_category: Optional[str] = Form(None),
    default_manufacturer: Optional[str] = Form(None)
):
    files_data = []
    for f in files:
        content = await f.read()
        files_data.append((f.filename, content))

    ingested = await VectorStoreService.ingest_catalog_files(
        files_data=files_data,
        default_category=default_category,
        default_manufacturer=default_manufacturer
    )
    return {
        "code": 200,
        "message": f"成功从 {len(files)} 份供应商样册中拆解并入库 {len(ingested)} 款组部件型号",
        "data": {
            "ingested_count": len(ingested),
            "items": ingested
        }
    }


@router.post("/seed", summary="一键导入/重置行业典型组部件标准品种子库")
async def seed_default_components():
    count = VectorStoreService.seed_default_library()
    items = VectorStoreService.list_components()
    return {
        "code": 200,
        "message": f"已成功导入 {count} 款行业典型组部件标准品（含向量化索引）",
        "data": {
            "seeded_count": count,
            "items": items
        }
    }


@router.put("/{comp_id}", summary="手动修订某个标准组件的参数并重新向量化")
async def update_component_item(comp_id: str, payload: ComponentUpdatePayload):
    updated = VectorStoreService.update_component(
        comp_id=comp_id,
        payload=payload.model_dump(exclude_none=True)
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"未找到组件: {comp_id}")
    return {
        "code": 200,
        "message": "组件参数已更新并重新生成 Embedding 向量",
        "data": updated
    }


@router.delete("/{comp_id}", summary="删除指定的组部件标准品")
async def delete_component_item(comp_id: str):
    ok = VectorStoreService.delete_component(comp_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"未找到组件: {comp_id}")
    return {
        "code": 200,
        "message": "组件已从标准库中移除"
    }


@router.get("/catalogs/{file_name}", summary="获取供应商样册原始 PDF 文件流供前端溯源高亮预览")
async def get_catalog_pdf_stream(file_name: str):
    file_path = VectorStoreService.get_catalog_file_path(file_name)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"未找到供应商样册文件: {file_name}")
    media_type = "application/pdf" if file_name.lower().endswith(".pdf") else "application/octet-stream"
    return FileResponse(path=file_path, media_type=media_type, filename=file_name)
