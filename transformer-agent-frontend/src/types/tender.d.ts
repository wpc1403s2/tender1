// 文档分类枚举
export type DocCategory = 'commercial_bid' | 'technical_spec' | 'boq_list' | 'component_catalog' | 'unknown';

// 原文溯源坐标与引用
export interface SourceReference {
  doc_id?: string;
  file_name: string;
  page_number: number;
  bbox: [number, number, number, number] | null; // [x0, y0, x1, y1] (PyMuPDF 72 DPI 坐标)
  original_text?: string;
  file_url?: string; // 支持供应商样册 PDF 二进制流地址
}

// 预处理后的文档摘要
export interface DocumentSummary {
  doc_id: string;
  file_name: string;
  category: DocCategory;
  total_pages: number;
  blocks_count: number;
  file_url?: string; // 供前端 PDF.js 加载的二进制流地址或 MinIO 链接
}

// 内部标准库匹配到的合格供应商组件
export interface MatchedCandidate {
  comp_id: string;
  manufacturer: string;     // 如: Siemens, EMB, Qualitrol, KunLun
  model_series: string;     // 如: 3EL2, YSF8-55/80, AKM345, KI 45X
  similarity_score: number; // 语义匹配度得分 (0~1)
  rule_passed?: boolean;
  match_status?: 'FULLY_MATCHED' | 'QUALIFIED' | 'PARTIAL_DEVIATION';
  match_highlights?: string[];
  deviation_notes?: string[];
  specs_summary: Record<string, any>;
  key_metrics?: Record<string, any>;
  catalog_bbox?: SourceReference; // 供应商样册的溯源坐标
}

// 提取出的组部件需求及匹配结果
export interface ExtractedComponentItem {
  req_id: string;
  Category_Code?: string;
  Component_Category: string;
  Component_Name: string;
  Material_Requirement: string;
  Technical_Parameters: Record<string, string>;
  Specific_Requirements: string[];
  Quantity: string;
  has_conflict?: boolean;       // 跨文档比对（如PDF规范与Excel清单不一致）冲突标记
  conflict_reason?: string;
  Source_Reference: SourceReference;
  matched_candidates: MatchedCandidate[]; // 全量召回的合格供应商列表（不预设排序）
  selected_comp_id?: string;              // 人工复核最终选定的供应商型号ID
}

// 变压器主参数项（对应《二期提示词字段》）
export interface MainParameterItem {
  param_key: string;        // 如: "1.2 变压器的频率", "最高温度(℃)"
  param_value: string;      // 提取值，如: "50Hz", "45"
  original_text: string;    // 原文描述
  has_conflict?: boolean;
  source_ref: SourceReference;
}

// 整个标书项目的审阅状态数据
export interface TenderReviewData {
  project_id: string;
  project_name: string;
  status: 'PARSING' | 'EXTRACTING' | 'MATCHED' | 'COMPLETED';
  documents: DocumentSummary[];
  main_parameters: MainParameterItem[];
  components: ExtractedComponentItem[];
}