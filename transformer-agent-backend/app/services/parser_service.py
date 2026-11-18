import io
import os
import uuid
import zipfile
import asyncio
import numpy as np
import pandas as pd
import fitz  # PyMuPDF
from docx import Document as DocxDocument
from loguru import logger
from typing import List, Dict, Optional, Tuple

from app.schemas.document_schema import (
    DocCategory, ContentBlock, ParsedDocument, ProjectMemoryStore
)
# 在 app/services/parser_service.py 顶部新增导入与目录常量：
from pathlib import Path

UPLOAD_ROOT_DIR = Path("data/uploads")
UPLOAD_ROOT_DIR.mkdir(parents=True, exist_ok=True)
# 延迟加载或全局单例初始化 PaddleOCR PP-Structure (避免每次请求重复加载模型)
try:
    from paddleocr import PPStructure
    # layout=True 开启版面分析，table=True 开启嵌套表格还原
    ocr_engine = PPStructure(show_log=False, layout=True, table=True, ocr=True)
except ImportError:
    ocr_engine = None
    logger.warning("PaddleOCR 未安装或初始化失败，扫描件 OCR 功能将受限。")


class DocumentParserService:
    """多源异构文档预处理与内存管理服务"""

    # 内存缓存池 (生产环境可无缝替换为 Redis 序列化存储)
    _memory_store: Dict[str, ProjectMemoryStore] = {}

    @classmethod
    def get_project_memory(cls, project_id: str) -> Optional[ProjectMemoryStore]:
        return cls._memory_store.get(project_id)

    @staticmethod
    def classify_document(file_name: str, sample_text: str) -> DocCategory:
        """基于文件名与前500字文本特征，自动识别标书文档类型"""
        name_lower = file_name.lower()
        text_lower = sample_text[:1000].lower()

        # 1. Excel 或明确带有参数表/清单字样的归为清单 (BOQ / TDS)
        if name_lower.endswith(('.xlsx', '.xls', '.csv')):
            return DocCategory.BILL_OF_QUANTITIES
        if any(k in name_lower for k in ['tds', '参数表', '清单', 'hojas de datos']):
            return DocCategory.BILL_OF_QUANTITIES

        # 2. 技术规范识别
        tech_keywords = ['specification', 'technical', '技术规范', '技术要求', 'especificación']
        if any(k in name_lower or k in text_lower for k in tech_keywords):
            return DocCategory.TECHNICAL_SPEC

        # 3. 商务标识别
        comm_keywords = ['commercial', 'rfq', 'itt', '商务', '投标须知', '报价', 'contract']
        if any(k in name_lower or k in text_lower for k in comm_keywords):
            return DocCategory.COMMERCIAL_BID

        return DocCategory.UNKNOWN

    @classmethod
    def get_uploaded_file_path(cls, project_id: str, file_name: str) -> Path:
        """获取某项目下已上传原始文件的本地存储路径"""
        return UPLOAD_ROOT_DIR / project_id / file_name

    @classmethod
    async def process_upload_Batch(cls, project_id: str, files_data: List[Tuple[str, bytes]]) -> ProjectMemoryStore:
        if project_id not in cls._memory_store:
            cls._memory_store[project_id] = ProjectMemoryStore(project_id=project_id)

        # 创建当前项目的专属文件存放目录
        project_dir = UPLOAD_ROOT_DIR / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        expanded_files: List[Tuple[str, bytes]] = []

        # 1. 自动拆解 ZIP 包或单文件
        for filename, file_bytes in files_data:
            if filename.lower().endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                    for member in zf.infolist():
                        if not member.is_dir() and not member.filename.startswith('__MACOSX'):
                            real_name = os.path.basename(member.filename)
                            if real_name:
                                raw_bytes = zf.read(member)
                                expanded_files.append((real_name, raw_bytes))
                                # 保存解压后的原文件到磁盘
                                (project_dir / real_name).write_bytes(raw_bytes)
            else:
                expanded_files.append((filename, file_bytes))
                # 保存上传的原文件到磁盘
                (project_dir / filename).write_bytes(file_bytes)

        # 2. 并发执行文档解析
        tasks = [
            asyncio.to_thread(cls._parse_single_file, fname, fbytes)
            for fname, fbytes in expanded_files
        ]
        parsed_docs: List[ParsedDocument] = await asyncio.gather(*tasks)

        # 3. 存入内存上下文
        for doc in parsed_docs:
            cls._memory_store[project_id].documents[doc.doc_id] = doc
            logger.info(f"文档 [{doc.file_name}] 已保存并解析完成 | 页数: {doc.total_pages}")

        return cls._memory_store[project_id]

    @classmethod
    def _parse_single_file(cls, file_name: str, file_bytes: bytes) -> ParsedDocument:
        """路由分发至对应的底层解析器"""
        doc_id = str(uuid.uuid4())
        ext = os.path.splitext(file_name)[-1].lower()

        if ext == '.pdf':
            blocks, total_pages = cls._parse_pdf(file_bytes)
        elif ext in ['.docx', '.doc']:
            blocks, total_pages = cls._parse_docx(file_bytes)
        elif ext in ['.xlsx', '.xls']:
            blocks, total_pages = cls._parse_excel(file_bytes)
        else:
            blocks, total_pages = [], 0
            logger.warning(f"不支持的文件格式: {file_name}")

        # 组装带有页码与 BBox 锚点的完整文本，方便大模型直接阅读并输出溯源坐标
        full_md_lines = []
        sample_text = ""
        for b in blocks:
            if len(sample_text) < 1000:
                sample_text += b.content + "\n"
            bbox_str = f"{b.bbox[0]:.1f},{b.bbox[1]:.1f},{b.bbox[2]:.1f},{b.bbox[3]:.1f}" if b.bbox else "N/A"
            full_md_lines.append(f"<!-- Page:{b.page_number} | BBox:[{bbox_str}] | Type:{b.block_type} -->\n{b.content}")

        category = cls.classify_document(file_name, sample_text)

        return ParsedDocument(
            doc_id=doc_id,
            file_name=file_name,
            file_ext=ext,
            category=category,
            total_pages=total_pages,
            blocks=blocks,
            full_markdown="\n\n".join(full_md_lines)
        )

    @classmethod
    def _parse_pdf(cls, file_bytes: bytes) -> Tuple[List[ContentBlock], int]:
        """混合解析 PDF：70%原生文本提取 + 30%盖章扫描件 OCR 与嵌套表格还原"""
        blocks: List[ContentBlock] = []
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        total_pages = len(pdf_doc)

        for page_index in range(total_pages):
            page = pdf_doc[page_index]
            page_num = page_index + 1
            raw_text = page.get_text("text").strip()

            # 判断是否为扫描页（文字极少，或存在全页扫描图像）
            is_scanned_page = len(raw_text) < 50 and len(page.get_images()) > 0

            if not is_scanned_page:
                # --- 分支 A: 原生 PDF 解析 ---
                # 1. 优先使用 PyMuPDF 内置的表格检测器提取原生表格
                tables = page.find_tables()
                table_bboxes = []
                for tab in tables:
                    table_bboxes.append(tab.bbox)
                    df = tab.to_pandas()
                    md_table = df.to_markdown(index=False)
                    blocks.append(ContentBlock(
                        block_id=str(uuid.uuid4())[:8],
                        page_number=page_num,
                        block_type="table",
                        content=md_table,
                        bbox=(tab.bbox[0], tab.bbox[1], tab.bbox[2], tab.bbox[3]),
                        is_ocr=False
                    ))

                # 2. 提取普通文本段落（过滤掉已作为表格提取的区域，避免重复）
                text_blocks = page.get_text("blocks") # 返回 (x0, y0, x1, y1, "text", block_no, block_type)
                for tb in text_blocks:
                    if tb[6] == 0:  # 0 代表文本块
                        bx0, by0, bx1, by1, text_content = tb[0], tb[1], tb[2], tb[3], tb[4].strip()
                        if not text_content:
                            continue
                        # 检查是否落在已提取的表格坐标内部
                        in_table = any(
                            bx0 >= t_box[0]-5 and by0 >= t_box[1]-5 and bx1 <= t_box[2]+5 and by1 <= t_box[3]+5
                            for t_box in table_bboxes
                        )
                        if not in_table:
                            blocks.append(ContentBlock(
                                block_id=str(uuid.uuid4())[:8],
                                page_number=page_num,
                                block_type="text",
                                content=text_content,
                                bbox=(bx0, by0, bx1, by1),
                                is_ocr=False
                            ))
            else:
                # --- 分支 B: 盖章扫描页 PP-Structure 版面分析与表格还原 ---
                if ocr_engine is not None:
                    # 将 PDF 页面渲染为高清图像供 OCR 识别
                    pix = page.get_pixmap(dpi=200)
                    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                    if pix.n == 4: # RGBA 转 RGB
                        import cv2
                        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)

                    result = ocr_engine(img_array)
                    # 计算图像坐标回退到 PDF 原始尺寸的缩放比例
                    scale_x = page.rect.width / pix.width
                    scale_y = page.rect.height / pix.height

                    for region in result:
                        r_type = region.get('type', 'text').lower()
                        bbox_px = region.get('bbox', [0, 0, 0, 0])
                        pdf_bbox = (
                            bbox_px[0] * scale_x, bbox_px[1] * scale_y,
                            bbox_px[2] * scale_x, bbox_px[3] * scale_y
                        )
                        if r_type == 'table':
                            # PP-Structure 会将复杂合并单元格表格还原为 HTML，直接提取供 LLM 阅读
                            html_table = region.get('res', {}).get('html', '')
                            blocks.append(ContentBlock(
                                block_id=str(uuid.uuid4())[:8],
                                page_number=page_num,
                                block_type="table",
                                content=html_table,
                                bbox=pdf_bbox,
                                is_ocr=True
                            ))
                        else:
                            res_list = region.get('res', [])
                            if isinstance(res_list, list):
                                text_lines = [item.get('text', '') for item in res_list if isinstance(item, dict)]
                                joined_text = "\n".join(text_lines).strip()
                                if joined_text:
                                    blocks.append(ContentBlock(
                                        block_id=str(uuid.uuid4())[:8],
                                        page_number=page_num,
                                        block_type="text",
                                        content=joined_text,
                                        bbox=pdf_bbox,
                                        is_ocr=True
                                    ))

        pdf_doc.close()
        return blocks, total_pages

    @classmethod
    def _parse_docx(cls, file_bytes: bytes) -> Tuple[List[ContentBlock], int]:
        """解析 Word 文档（提取段落与嵌套表格）"""
        blocks: List[ContentBlock] = []
        doc = DocxDocument(io.BytesIO(file_bytes))

        # 1. 提取段落
        for idx, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if text:
                blocks.append(ContentBlock(
                    block_id=f"docx_p_{idx}",
                    page_number=1,
                    block_type="text",
                    content=text
                ))

        # 2. 提取表格并转化为 Markdown
        for t_idx, table in enumerate(doc.tables):
            table_data = []
            for row in table.rows:
                row_Data = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                table_data.append(row_Data)
            if table_data:
                df = pd.DataFrame(table_data[1:], columns=table_data[0] if len(table_data) > 1 else None)
                blocks.append(ContentBlock(
                    block_id=f"docx_t_{t_idx}",
                    page_number=1,
                    block_type="table",
                    content=df.to_markdown(index=False)
                ))

        return blocks, 1

    @classmethod
    def _parse_excel(cls, file_bytes: bytes) -> Tuple[List[ContentBlock], int]:
        """解析招标清单 Excel（按 Sheet 拆解并清理空行，转化为结构化 Markdown）"""
        blocks: List[ContentBlock] = []
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        sheet_names = xls.sheet_names

        for s_idx, sheet_name in enumerate(sheet_names):
            df = pd.read_excel(xls, sheet_name=sheet_name)
            # 清理全空行和全空列
            df.dropna(how='all', inplace=True)
            df.dropna(how='all', axis=1, inplace=True)
            df.fillna("", inplace=True)

            if not df.empty:
                md_content = f"### Sheet: {sheet_name}\n" + df.to_markdown(index=False)
                blocks.append(ContentBlock(
                    block_id=f"xls_s_{s_idx}",
                    page_number=s_idx + 1,
                    block_type="table",
                    content=md_content
                ))

        return blocks, len(sheet_names)