# 变压器标书智能解析与匹配系统 - 核心技术架构与流程设计说明

## 一、 变压器油 (Transformer Oil) 专属提取数据字典 (JSON Schema)

变压器油与机械/电气组部件不同，其匹配核心在于**理化电气特性**是否满足招标文件中对极端环境（如极寒启动、散热、绝缘）的要求。

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TransformerOilExtraction",
  "description": "变压器油规范要求提取与匹配字典",
  "type": "object",
  "properties": {
    "Component_Type": {
      "type": "string",
      "const": "Transformer_Oil"
    },
    "Manufacturer_Info": {
      "type": "object",
      "properties": {
        "brand": { "type": "string", "description": "如: KunLun (PetroChina)" },
        "product_model": { "type": "string", "description": "如: KI 25X, KI 50X, Petro 45U" },
        "standards_met": { "type": "array", "items": {"type": "string"}, "description": "如: IEC 60296:2012, ASTM D3487-16, GB 2536-2011" }
      }
    },
    "Physical_Characteristics": {
      "type": "object",
      "description": "物理与环境适应性参数",
      "properties": {
        "LCSET": { "type": "string", "description": "最低冷态启动投运温度 (如: -30°C)" },
        "pour_point": { "type": "string", "description": "倾点 (如: -45°C)" },
        "kinetic_viscosity_40C": { "type": "string", "description": "40°C运动粘度，影响散热 (mm²/s)" },
        "flash_point": { "type": "string", "description": "闭口闪点 (如: ≥135°C)" }
      }
    },
    "Electrical_Properties": {
      "type": "object",
      "description": "电气绝缘性能",
      "properties": {
        "breakdown_voltage_treated": { "type": "string", "description": "处理后击穿电压 (如: >70 kV)" },
        "dielectric_loss_factor": { "type": "string", "description": "90°C 介质损耗因数 (如: <0.001)" },
        "water_content": { "type": "string", "description": "微水含量 (mg/kg)" }
      }
    },
    "Chemical_Properties": {
      "type": "object",
      "description": "化学及稳定性",
      "properties": {
        "corrosive_sulfur": { "type": "string", "description": "腐蚀性硫 (DIN 51353, ASTM D1275B)" },
        "antioxidant_content": { "type": "string", "description": "抗氧化剂含量 (%)" },
        "acid_number": { "type": "string", "description": "酸值 (mgKOH/g)" }
      }
    }
  }
}
```

---

## 二、 系统技术架构与处理流程说明

基于您的业务场景，本系统旨在通过**Agent（智能体）**将复杂的非结构化PDF/Word/Excel解析、提取、比对，并最终生成结构化的《偏离表/选型表》。以下是全栈技术架构设计：

### 1. 核心技术栈 (Tech Stack)
*   **前端交互层 (Frontend)**: `Vue 3` + `TypeScript` + `PDF.js`。提供左右分屏的沉浸式审核界面，支持文本级与表格单元格级的 BBox（边界框）高亮溯源。
*   **后端服务层 (Backend)**: `Python 3.10` + `FastAPI` (高并发异步处理) + `Celery` & `Redis` (由于大模型解析长标书耗时较长，采用异步任务队列)。
*   **Agent与大模型层 (AI Engine)**: 
    *   大模型基座：`DeepSeek-V3 / Coder`（支持 128k 长上下文与严格的 JSON 强制输出）。
    *   Agent 编排框架：`LangGraph`（构建文档解析、参数提取、供应商匹配的 DAG 工作流）。
*   **文档解析引擎 (Parser)**: `PyMuPDF` (提取原生文本与坐标) + `PaddleOCR PP-Structure` (解决30%盖章扫描件的版面分析及嵌套表格还原)。
*   **混合数据库 (Hybrid Data Storage)**:
    *   **关系型数据**：`PostgreSQL`（存储项目元数据、提取的历史参数表、人工复核结果）。
    *   **向量检索**：`Milvus`（存储组部件如西门子、Qualitrol、昆仑油等上百份PDF切片向量，采用 `bge-m3` 多语言嵌入模型）。
    *   **文件存储**：`MinIO`（存储原始标书、生成的Excel及高亮截图）。

### 2. 系统处理流程 (Workflow Pipeline)

**Step 1: 多源文档预处理 (Ingestion & Parsing)**
*   用户上传包含商务标、技术规范(PDF)和清单(Excel)的标书 ZIP 包。
*   系统自动识别文档类型，调用 `PaddleOCR` 和 `PyMuPDF` 提取文本。
*   **关键点**：为每一个句子和表格单元格打上 `(page_num, x0, y0, x1, y1)` 的空间坐标戳，随文本一起存入内存。

**Step 2: 多智能体信息提取 (Multi-Agent Extraction)**
*   **商务 Agent**：负责查阅商务部分，提取买方、项目地点、交货期、环境条件（如：环境最低温度 -10℃，防腐要求 C4/C5 等）。
*   **变压器主参 Agent**：依据《二期提示词字段.xlsx》的 Schema，提取变压器容量、电压等级(如 30/220kV)、联结组别等。
*   **组部件 Agent**：遍历规范中的“Accessories / Technical Requirement”章节，依据上述 JSON Schema，提取油位计、温度计、瓦斯继电器、避雷器、绝缘油的具体技术参数。

**Step 3: RAG 组部件智能匹配 (Knowledge-based Matching)**
针对提取出的需求，调用匹配引擎去内部产品库（西门子、EMB、Qualitrol、昆仑等）寻找匹配件：
*   **硬规则匹配 (Rule Engine)**：
    *   若标书要求最低环境温度 `-30℃`，规则引擎直接过滤掉 `Pour Point` (倾点) 高于 `-30℃` 的变压器油，匹配出 `KunLun KI 45X` 或 `Petro 45U`。
    *   若标书要求电压等级 `220kV` 且放电电流 `10kA`，则过滤西门子避雷器选型，锁定 `3EL2` 或 `3EQ1` 系列。
*   **语义模糊召回 (Semantic RAG)**：对于“Requires smart regeneration breather with MODBUS support”之类的非标描述，通过 Milvus 向量相似度检索，精准召回 `Qualitrol STB000 Smart Breather`。

**Step 4: 冲突校验与人机协同 (Human-in-the-Loop)**
*   Agent 对比清单 Excel 和 技术规范 PDF，如发现数量不一致或参数冲突，在系统中打上红色 `[Conflict]` 标签。
*   业务人员在 Web 端审核，点击提取出的参数（如：西门子避雷器爬电距离 31 mm/kV），左侧的原始标书 PDF 会**自动翻页并高亮**对应的要求段落，右侧会高亮西门子样册的对应说明，实现 100% 可信溯源。

**Step 5: 结构化输出 (Export)**
*   人工确认无误后，系统调用 `openpyxl`，一键生成用于投标的《组部件选型配置单》和《技术参数偏离表》Excel，供商务打包投标使用。

### 3. 数据库表结构设计 (Database Schema)

*   **`projects` (项目主表)**
    *   `project_id` (PK, UUID)
    *   `project_name` (String, 项目名称)
    *   `status` (Enum: PARSING, EXTRACTING, MATCHED, COMPLETED)
*   **`documents` (文档表)**
    *   `doc_id` (PK, UUID)
    *   `project_id` (FK -> projects)
    *   `doc_type` (Enum: TENDER_SPEC, BILL_OF_MATERIAL, COMPONENT_CATALOG)
    *   `file_path` (String, 存储路径)
*   **`tender_requirements` (标书需求提取结果表)**
    *   `req_id` (PK, UUID)
    *   `project_id` (FK -> projects)
    *   `component_category` (String, 组件大类)
    *   `extracted_json` (JSONB, LLM 提取的需求结构化数据)
    *   `source_bbox` (JSONB, 原文坐标数据)
*   **`component_library` (组部件标准品知识库)**
    *   `comp_id` (PK, UUID)
    *   `manufacturer` (String, 厂家名，如 Siemens)
    *   `model_series` (String, 产品系列，如 3EL2)
    *   `component_category` (String, 如 Surge_Arrester)
    *   `specs_json` (JSONB, LLM 提取的本字典参数数据)
    *   `vector_doc_id` (String, 关联 Milvus 中的向量 ID)
