from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field


# 覆盖《二期标准字段》的 15 大核心组部件分类标准字典
COMPONENT_CATEGORIES: List[Dict[str, str]] = [
    {"code": "OLTC", "label": "有载分接开关 (OLTC)", "field_prefix": "2.1"},
    {"code": "DETC", "label": "无励磁分接开关 (DETC)", "field_prefix": "2.4"},
    {"code": "Bushing", "label": "套管 (Bushing)", "field_prefix": "3.套管"},
    {"code": "Surge_Arrester", "label": "避雷器 (Surge Arrester)", "field_prefix": "4.避雷器"},
    {"code": "Silicon_Steel", "label": "硅钢片 (Silicon Steel)", "field_prefix": "5.硅钢片"},
    {"code": "Winding_Wire", "label": "电磁线 (Winding Wire)", "field_prefix": "6.变压器绕组线圈电磁线"},
    {"code": "Transformer_Oil", "label": "绝缘油 (Transformer Oil)", "field_prefix": "7.绝缘油"},
    {"code": "Cooling_System", "label": "冷却系统/风扇油泵 (Cooling System)", "field_prefix": "8.变压器冷却系统"},
    {"code": "BCT", "label": "套管电流互感器 (BCT)", "field_prefix": "9.电流互感器"},
    {"code": "Smart_Breather", "label": "呼吸器 (Breather)", "field_prefix": "12.呼吸器"},
    {"code": "Oil_Level_Indicator", "label": "油位计 (Oil Level Indicator)", "field_prefix": "13.油位计"},
    {"code": "Buchholz_Relay", "label": "气体继电器 (Buchholz Relay)", "field_prefix": "14.气体继电器"},
    {"code": "Temperature_Indicator", "label": "油面/绕组温控器 (OTI/WTI)", "field_prefix": "15.油面温度计和绕组温度计"},
    {"code": "Pressure_Relief_Valve", "label": "压力释放阀 (Pressure Relief Valve)", "field_prefix": "16.压力释放阀"},
    {"code": "Sudden_Pressure_Relay", "label": "压力突发继电器 (Sudden Pressure Relay)", "field_prefix": "17.压力突发继电器"},
    {"code": "Valve", "label": "变压器阀门 (Valve)", "field_prefix": "19.变压器中阀门"},
]

CATEGORY_LABEL_MAP: Dict[str, str] = {c["code"]: c["label"] for c in COMPONENT_CATEGORIES}


class CatalogSourceRef(BaseModel):
    file_name: str = ""
    page_number: int = 1
    bbox: Optional[List[float]] = None
    original_text: Optional[str] = ""
    file_url: Optional[str] = ""


class ComponentLibraryItemSchema(BaseModel):
    comp_id: str
    component_category: str = Field(..., description="组部件大类编码，如 Transformer_Oil, Surge_Arrester")
    category_label: str = Field(default="", description="组部件大类显示名")
    manufacturer: str = Field(..., description="品牌/厂家，如 Siemens, MR, EMB, Qualitrol, KunLun")
    model_series: str = Field(..., description="具体型号，如 KI 45X, 3EL2, VACUTAP VV")
    key_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="用于硬规则过滤的关键数值指标，如 max_voltage_kv, rated_current_a, pour_point_c"
    )
    specs_json: Dict[str, Any] = Field(default_factory=dict, description="完整结构化技术参数字典")
    summary_text: str = Field(default="", description="用于向量检索的综合描述")
    catalog_ref: Optional[CatalogSourceRef] = None
    created_at: Optional[str] = None


class ComponentUpdatePayload(BaseModel):
    component_category: Optional[str] = None
    manufacturer: Optional[str] = None
    model_series: Optional[str] = None
    key_metrics: Optional[Dict[str, Any]] = None
    specs_json: Optional[Dict[str, Any]] = None
    summary_text: Optional[str] = None


class MatchedCandidateSchema(BaseModel):
    comp_id: str
    manufacturer: str
    model_series: str
    similarity_score: float = Field(default=0.85, description="综合匹配度得分 (0~1)")
    rule_passed: bool = Field(default=True, description="是否通过硬规则过滤")
    match_status: str = Field(default="QUALIFIED", description="FULLY_MATCHED | QUALIFIED | PARTIAL_DEVIATION")
    match_highlights: List[str] = Field(default_factory=list, description="满足标书的核心亮点项")
    deviation_notes: List[str] = Field(default_factory=list, description="潜在偏离或选型注意事项")
    specs_summary: Dict[str, Any] = Field(default_factory=dict)
    key_metrics: Dict[str, Any] = Field(default_factory=dict)
    catalog_bbox: Optional[CatalogSourceRef] = None
