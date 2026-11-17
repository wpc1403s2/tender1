# 招标系统 — 已完成模块清单

> 按后端 / 前端两大模块整理，标注文件路径与核心功能。

---

## 一、后端（transformer-agent-backend）

### 1. 内存状态与数据结构定义

**路径**：`app/schemas/document_schema.py`

定义统一的内存存储结构。无论是 PDF、Word 还是 Excel，最终都会转化为带有页码、坐标（BBox）或 Markdown 表格的标准数据块（Block），供下游 LangGraph 提取节点直接消费。

### 2. 核心多源文档解析服务

**路径**：`app/services/parser_service.py`

集成 `PyMuPDF`、`PaddleOCR (PP-Structure)`、`python-docx` 和 `pandas`，包含两大核心机制：

| 机制 | 说明 |
| --- | --- |
| **动静分离检测** | 解析 PDF 时，若单页有效字符少于 50 个且包含大图（如盖章扫描页），自动降级切换至 PP-Structure 进行版面分析与复杂嵌套表格还原 |
| **自动分类器** | 结合文件名与首页高频特征词（英文标书中的 `Specification`、`TDS`、`RFQ`，或中文的"技术规范"、"商务"）自动判定文档业务类型 |

### 3. FastAPI 路由接口层

**路径**：`app/api/v1/tender.py`

暴露给前端上传页面的接口，支持一次上传多个单文件，或直接拖入一个完整的项目 ZIP 压缩包。

---

## 二、前端（transformer-agent-frontend）

### 4. 依赖配置

**路径**：`package.json`

包含 Element Plus 组件库、Pinia 状态管理、Axios 网络请求，以及用于底层 Canvas 渲染和高亮定位的依赖。

### 5. TypeScript 核心类型声明

**路径**：`src/types/tender.d.ts`

严格对齐后端的 Pydantic Schema：

- `ProjectMemoryStore`
- 提取参数结构
- 组部件匹配候选列表

### 6. BBox 空间坐标转换工具

**路径**：`src/utils/bboxUtils.ts`

后端 PyMuPDF（fitz）提取的 bbox 基于 PDF 默认 **72 DPI 左上角原点坐标系** `[x0, y0, x1, y1]`。当 PDF 在前端 Canvas 缩放渲染时，必须通过缩放倍率进行动态映射。

### 7. API 接口层

**路径**：`src/api/tender.ts`

封装与后端 FastAPI 对接的接口：

- 上传预处理
- 获取提取匹配结果
- 提交人工修正
- 导出《初评表 / 偏离表》Excel

### 8. Pinia 全局状态管理

**路径**：`src/store/tenderStore.ts`

### 9. PDF 原文溯源与 BBox 高亮预览组件

**路径**：`src/components/pdf/PdfViewer.vue`

### 10. 核心页面一：标书上传与预处理看板

**路径**：`src/views/TenderAnalysis/Upload.vue`

对接后端 `/api/v1/tender/upload` 接口，展示多源文档自动分类（商务标、技术规范、清单 Excel）与切块统计结果。

### 11. 核心页面二：左右分屏人机协同审阅工作台

**路径**：`src/views/TenderAnalysis/Review.vue`

实现业务人员的核心交互：

| 区域 | 功能 |
| --- | --- |
| **左侧** | 渲染标书 PDF 原件，支持多文档切换，点击右侧参数自动跳转高亮 |
| **右侧 Tab 1**（变压器主参数） | 展示按《二期提示词字段》提取的参数，支持冲突高亮提醒与一键修改 |
| **右侧 Tab 2**（组部件智能匹配） | 展示提取出的组部件要求（避雷器、瓦斯继电器、压力释放阀、变压器油等），列出**硬规则过滤 + 向量语义召回**的所有合格内部供应商型号（不做主观排序，全量展示供工程师勾选） |
| **顶部** | 一键导出：确认后调用后端 openpyxl 服务生成填满数据的《新版初评表》Excel |

### 12. 路由与入口文件

**路径**：`src/router/index.ts` & `src/main.ts`
