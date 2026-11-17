from enum import Enum
from typing import List, Optional, Tuple, Dict
from pydantic import BaseModel, Field

class DocCategory(str, Enum):
    COMMERCIAL_BID = "commercial_bid"      # 商务标
    TECHNICAL_SPEC = "technical_spec"      # 技术规范
    BILL_OF_QUANTITIES = "boq_list"        # 招标清单/参数表 (Excel)
    COMPONENT_CATALOG = "component_catalog"# 组部件标准规范
    UNKNOWN = "unknown"

class ContentBlock(BaseModel):
    block_id: str = Field(..., description="唯一块ID，用于溯源索引")
    page_number: int = Field(default=1, description="所在页码（Excel为Sheet序号）")
    block_type: str = Field(default="text", description="类型: text | table")
    content: str = Field(..., description="文本内容或还原后的 Markdown/HTML 表格")
    bbox: Optional[Tuple[float, float, float, float]] = Field(
        default=None, description="原文空间坐标 (x0, y0, x1, y1)，用于前端 PDF.js 高亮"
    )
    is_ocr: bool = Field(default=False, description="是否由扫描件 OCR 生成")

class ParsedDocument(BaseModel):
    doc_id: str
    file_name: str
    file_ext: str
    category: DocCategory
    total_pages: int
    blocks: List[ContentBlock] = Field(default_factory=list)
    full_markdown: str = Field(default="", description="拼接后的完整上下文，带有坐标锚点标记")

class ProjectMemoryStore(BaseModel):
    """项目级内存上下文，可直接映射为 LangGraph 的初始 State"""
    project_id: str
    documents: Dict[str, ParsedDocument] = Field(default_factory=dict)