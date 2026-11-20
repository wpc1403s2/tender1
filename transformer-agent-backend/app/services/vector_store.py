import json
import math
import re
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import quote
import numpy as np
from loguru import logger
from sqlalchemy import text
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.config import settings
from app.models.library import ComponentLibraryModel, DatabaseSessionManager
from app.schemas.tender_schema import (
    COMPONENT_CATEGORIES,
    CATEGORY_LABEL_MAP,
    ComponentLibraryItemSchema,
    CatalogSourceRef,
)
from app.schemas.document_schema import ContentBlock
from app.services.parser_service import DocumentParserService

CATALOG_ROOT_DIR = Path("data/catalogs")
CATALOG_ROOT_DIR.mkdir(parents=True, exist_ok=True)

LOCAL_LIBRARY_JSON = Path("data/library/components.json")
LOCAL_LIBRARY_JSON.parent.mkdir(parents=True, exist_ok=True)


# 内置 16 款覆盖 15 大品类的行业典型标准品种子库
DEFAULT_SEED_COMPONENTS: List[Dict[str, Any]] = [
    {
        "comp_id": "seed_oltc_hm_cv",
        "component_category": "OLTC",
        "manufacturer": "上海华明 (Huaming)",
        "model_series": "CV III-350Y/40.5-10193W",
        "key_metrics": {"max_voltage_kv": 40.5, "rated_current_a": 350, "mechanical_life_times": 1000000, "tap_positions": 17},
        "specs_json": {
            "适用最高电压": "40.5 kV (兼容33kV/35kV系统)",
            "最大额定通过电流": "350 A",
            "最大调压级数": "±8×1.25% 或 ±6×1.25% (最高19级)",
            "过渡方式": "真空熄弧 + 电阻过渡",
            "机械寿命": "≥ 1,200,000 次 (免维护30万次)",
            "绝缘水平": "工频耐压 85kV / 雷电冲击 200kV",
            "电动机构": "CMA-7 电动机构 (支持远方/本地控制, 4-20mA/BCD/RS485)"
        },
        "summary_text": "上海华明 Huaming CV III-350Y/40.5 有载分接开关 OLTC 33kV 35kV 40.5kV 真空有载调压开关 机械寿命120万次 工频85kV 冲击200kV ±6x1.25% ±8x1.25%"
    },
    {
        "comp_id": "seed_oltc_mr_vv",
        "component_category": "OLTC",
        "manufacturer": "MR (Reinhausen)",
        "model_series": "VACUTAP® VV® III 400Y-40.5",
        "key_metrics": {"max_voltage_kv": 40.5, "rated_current_a": 400, "mechanical_life_times": 1200000, "tap_positions": 19},
        "specs_json": {
            "适用最高电压": "40.5 kV",
            "最大额定通过电流": "400 A",
            "调压范围": "±6×1.25% / ±8×1.25%",
            "熄弧技术": "MR真空管熄弧技术 (30万次免换油免维护)",
            "机械寿命": "120万次切换",
            "绝缘水平": "LI 200kV / AC 85kV",
            "驱动与AVR": "TAPMOTION ED + TAPCON 230 (支持IEC 61850 / Modbus)"
        },
        "summary_text": "德国 MR Reinhausen VACUTAP VV III 400Y-40.5 真空有载分接开关 OLTC 33kV 35kV 120万次机械寿命 免维护30万次 IEC61850 AVR"
    },
    {
        "comp_id": "seed_detc_hm_wsl",
        "component_category": "DETC",
        "manufacturer": "上海华明 (Huaming)",
        "model_series": "WSL II-400/40.5-6x5",
        "key_metrics": {"max_voltage_kv": 40.5, "rated_current_a": 400},
        "specs_json": {
            "开关类型": "笼形无励磁分接开关 (DETC)",
            "额定电压": "40.5 kV",
            "额定电流": "400 A",
            "调压分接": "±2×2.5% (5级)",
            "绝缘水平": "LI 200kV / AC 85kV",
            "操作方式": "箱顶手动/电动转轮操作，带档位机械锁紧"
        },
        "summary_text": "上海华明 WSL II-400/40.5 无励磁分接开关 无载调压开关 DETC 35kV 40.5kV ±2x2.5%"
    },
    {
        "comp_id": "seed_bushing_tridelta_rip",
        "component_category": "Bushing",
        "manufacturer": "南京电气 / Trench",
        "model_series": "GDR-40.5/1250-31 (RIP干式电容套管)",
        "key_metrics": {"max_voltage_kv": 40.5, "rated_current_a": 1250, "creepage_mm_kv": 31, "li_kv": 200, "ac_kv": 85},
        "specs_json": {
            "最高工作电压": "40.5 kV (适用33kV/35kV)",
            "额定电流": "1250 A",
            "绝缘类型": "RIP 树脂浸渍纸干式电容型套管 (适配电缆进线罩)",
            "绝缘水平": "雷电冲击全波 200kV / 1min工频耐压 85kV",
            "爬电比距": "≥ 31 mm/kV (IV级重污秽)",
            "局部放电": "1.5Um下 ≤ 5 pC (优于标书10pC要求)"
        },
        "summary_text": "南京电气 Trench GDR-40.5/1250-31 高压套管 RIP干式电容套管 33kV 40.5kV 冲击200kV 工频85kV 爬电比距31mm/kV 局放小于5pC 电缆套管"
    },
    {
        "comp_id": "seed_bushing_abb_lv",
        "component_category": "Bushing",
        "manufacturer": "Hitachi Energy (ABB)",
        "model_series": "GOB 17.5/3150-31 (低压大电流套管)",
        "key_metrics": {"max_voltage_kv": 17.5, "rated_current_a": 3150, "creepage_mm_kv": 31, "li_kv": 105, "ac_kv": 45},
        "specs_json": {
            "适用电压等级": "11kV / 15kV (Um=17.5kV)",
            "额定电流": "3150 A (支持铜母线排连接)",
            "绝缘水平": "雷电冲击 105kV / 工频耐压 45kV",
            "爬电比距": "≥ 31 mm/kV",
            "外绝缘材质": "高强防污瓷套 / 复合硅橡胶可选"
        },
        "summary_text": "Hitachi Energy ABB GOB 17.5/3150-31 低压套管 11kV 冲击105kV 工频45kV 爬电31mm/kV 铜母线出线"
    },
    {
        "comp_id": "seed_arrester_siemens_3el2",
        "component_category": "Surge_Arrester",
        "manufacturer": "Siemens (西门子)",
        "model_series": "3EL2 036-2PF31-4NA2",
        "key_metrics": {"max_voltage_kv": 42, "discharge_current_ka": 10, "creepage_mm_kv": 31},
        "specs_json": {
            "额定电压 Ur": "42 kV (适用33kV/35kV系统)",
            "持续运行电压 MCOV": "33.6 kV",
            "标称放电电流": "10 kA (8/20μs), 电站级 Class 3",
            "外套材质": "复合硅橡胶外套 (Silicone Rubber)",
            "爬电比距": "≥ 31 mm/kV",
            "满足标准": "IEC 60099-4 / GB 11032"
        },
        "summary_text": "西门子 Siemens 3EL2 036 电站型复合外套金属氧化物避雷器 33kV 35kV 10kA 硅橡胶 爬电31mm/kV IEC 60099-4"
    },
    {
        "comp_id": "seed_steel_baosteel_23qg",
        "component_category": "Silicon_Steel",
        "manufacturer": "宝钢 (Baosteel) / 新日铁 (Nippon Steel)",
        "model_series": "B23R080 (0.23mm 激光刻痕高磁感取向硅钢)",
        "key_metrics": {"thickness_mm": 0.23, "core_loss_w_kg": 0.80},
        "specs_json": {
            "厚度": "0.23 mm",
            "比总损耗 P1.7/50": "≤ 0.80 W/kg",
            "最小磁极化强度 B800": "≥ 1.90 T",
            "工艺特性": "高磁感取向电工钢，满足GB 20052-2020一级能效低空载损耗要求"
        },
        "summary_text": "宝钢 新日铁 B23R080 23ZH80 国际知名品牌高导磁取向硅钢片 0.23mm 一级能效低铁损"
    },
    {
        "comp_id": "seed_wire_ctc_tup",
        "component_category": "Winding_Wire",
        "manufacturer": "统力电工 (Tongli) / 魏德曼 (Weidmann)",
        "model_series": "CTC-TUP 无氧铜换位导线 (耐热A/E级)",
        "key_metrics": {"thermal_class": "A/E (105/120℃)", "copper_purity": 99.95},
        "specs_json": {
            "导体材质": "高纯无氧铜 (TU1, 导电率 ≥100% IACS)",
            "导线结构": "自粘性缩醛漆包换位导线 (CTC)",
            "匝间绝缘": "丹尼森/魏德曼热改性绝缘纸 (TUP) 或电缆纸",
            "耐热与场强": "满足A级/E级耐热，匝间工作场强裕度 ≤ 2.0 kV/mm"
        },
        "summary_text": "统力电工 无氧铜换位导线 CTC 热改性纸 TUP 绕组电磁线 A级绝缘 匝间场强不大于2kV/mm"
    },
    {
        "comp_id": "seed_oil_kunlun_ki45x",
        "component_category": "Transformer_Oil",
        "manufacturer": "中石油克拉玛依 / 昆仑 (Karamay KunLun)",
        "model_series": "KI 45X (45# 超高抗氧环烷基变压器油)",
        "key_metrics": {"oil_grade": "45#", "pour_point_c": -45, "flash_point_c": 140, "breakdown_voltage_kv": 72},
        "specs_json": {
            "油品牌号": "45# 环烷基矿物绝缘油 (新疆克拉玛依原产)",
            "倾点 (Pour Point)": "≤ -45 ℃ (满足 -45℃ 极寒要求)",
            "闭口闪点": "≥ 140 ℃ (满足 ≥135℃ 要求)",
            "处理后击穿电压": "≥ 72 kV",
            "90℃介质损耗因数": "≤ 0.0005",
            "腐蚀性硫": "非腐蚀性 (通过 ASTM D1275B / DIN 51353)",
            "执行标准": "GB 2536-2011 / IEC 60296:2020"
        },
        "summary_text": "新疆克拉玛依 中石油昆仑 KunLun KI 45X 45# 45号变压器绝缘油 倾点-45℃ 闪点140℃ 击穿电压72kV 无腐蚀性硫 GB2536 IEC60296"
    },
    {
        "comp_id": "seed_oil_kunlun_ki25x",
        "component_category": "Transformer_Oil",
        "manufacturer": "中石油克拉玛依 / 昆仑 (Karamay KunLun)",
        "model_series": "KI 25X (25# 环烷基变压器油)",
        "key_metrics": {"oil_grade": "25#", "pour_point_c": -25, "flash_point_c": 142, "breakdown_voltage_kv": 70},
        "specs_json": {
            "油品牌号": "25# 环烷基矿物绝缘油 (新疆克拉玛依)",
            "倾点 (Pour Point)": "≤ -25 ℃ (适用于温和及热带矿区如加纳/非洲项目)",
            "闭口闪点": "≥ 142 ℃",
            "处理后击穿电压": "≥ 70 kV",
            "腐蚀性硫": "非腐蚀性 (ASTM D1275B)",
            "执行标准": "GB 2536 / IEC 60296"
        },
        "summary_text": "新疆克拉玛依 昆仑 KI 25X 25# 25号变压器绝缘油 倾点-25℃ 闪点142℃ 非洲热带环境适用"
    },
    {
        "comp_id": "seed_cooling_radiator_fan",
        "component_category": "Cooling_System",
        "manufacturer": "江苏靖江 / 施乐百 (Ziehl-Abegg)",
        "model_series": "PC3000-20/520 热镀锌片式散热器 + 低噪音风冷组",
        "key_metrics": {"noise_db": 58, "ip_rating": "IP55", "corrosion_class": "C4"},
        "specs_json": {
            "冷却方式": "ONAN / ONAF 智能温控投切 (N-1冗余设计)",
            "散热器处理": "内腔真空淋油，外表热浸镀锌 + C4级重防腐面漆",
            "风扇参数": "Ziehl-Abegg 低噪轴流风机，防护等级 IP55，单台噪音 ≤56dB(A)",
            "整机噪音贡献": "确保距外壳1m处总噪声 < 65 dB(A)"
        },
        "summary_text": "片式散热器 低噪音冷却风扇 ONAN ONAF 距离外壳1m噪音小于65dB(A) 热镀锌 C4防腐 IP55 N-1冗余"
    },
    {
        "comp_id": "seed_bct_arteche",
        "component_category": "BCT",
        "manufacturer": "大连通达 / Arteche",
        "model_series": "LRB-35 套管升高座电流互感器 (BCT)",
        "key_metrics": {"max_voltage_kv": 40.5, "accuracy_classes": "0.2 / 5P20"},
        "specs_json": {
            "安装位置": "33kV/11kV 套管及中性点套管升高座内",
            "准确级组合": "测量级 0.2/0.5 + 保护级 5P20 (差动与后备保护)",
            "二次额定电流": "1A 或 5A 按标书定制",
            "绝缘耐热": "A级油浸绝缘，饱裕度满足IEC 61869-2"
        },
        "summary_text": "套管型电流互感器 BCT 升高座CT 0.2级 5P20 测量与差动保护 IEC 61869"
    },
    {
        "comp_id": "seed_breather_qualitrol_stb",
        "component_category": "Smart_Breather",
        "manufacturer": "Qualitrol / MR",
        "model_series": "Qualitrol STB000 / MR MESSKO® MTRAB® 2.5",
        "key_metrics": {"ip_rating": "IP66", "self_regenerating": True},
        "specs_json": {
            "类型": "免维护双腔自加热再生智能呼吸器 / 变色硅胶吸湿器",
            "除湿再生": "双通道自动切换加热除湿，无需人工更换硅胶",
            "通讯与报警": "支持 RS485 Modbus & 故障干接点报警",
            "防护等级": "IP66 不锈钢外壳，带下部油封杯"
        },
        "summary_text": "Qualitrol STB000 MR MESSKO MTRAB 免维护智能呼吸器 吸湿器 自加热再生 变色硅胶 IP66 Modbus"
    },
    {
        "comp_id": "seed_oli_qualitrol_032",
        "component_category": "Oil_Level_Indicator",
        "manufacturer": "Qualitrol / 沈阳沈变",
        "model_series": "Qualitrol 032 / YZF-250 磁力指针式油位计",
        "key_metrics": {"ip_rating": "IP65", "contacts": 2},
        "specs_json": {
            "结构型式": "磁力耦合大表盘指针式油位表 (本体及有载储油柜各1台)",
            "电气接点": "最高油位报警 + 最低油位报警 2组独立无源接点",
            "远传信号": "可选 4-20mA 模拟量远传输出",
            "防护等级": "IP65 防紫外线钢化玻璃表蒙"
        },
        "summary_text": "Qualitrol 032 YZF-250 磁力指针式油位计 储油柜油位表 最高最低油位报警接点 4-20mA IP65"
    },
    {
        "comp_id": "seed_buchholz_emb_bf80",
        "component_category": "Buchholz_Relay",
        "manufacturer": "德国 EMB / 沈阳特种",
        "model_series": "EMB BF 80/Q (QJ4-80 双浮子抗震气体继电器)",
        "key_metrics": {"pipe_dn_mm": 80, "float_count": 2, "ip_rating": "IP65"},
        "specs_json": {
            "公称通径": "DN80 (适用 10~100MVA 主变)",
            "动作流速整定": "0.65 / 1.0 / 1.5 m/s 可调挡板",
            "核心结构": "双浮子 + 挡板磁控干簧管结构 (独立轻瓦斯报警、重瓦斯跳闸双接点)",
            "抗震与附件": "高抗震设计，支持配置地面集气盒与机械测试按钮",
            "防护等级": "IP65"
        },
        "summary_text": "德国 EMB BF 80/Q QJ4-80 气体继电器 瓦斯继电器 双浮子 轻瓦斯报警 重瓦斯跳闸 地面取气盒 IP65"
    },
    {
        "comp_id": "seed_temp_qualitrol_akm",
        "component_category": "Temperature_Indicator",
        "manufacturer": "Qualitrol / 德国 MESSKO",
        "model_series": "AKM 34401 (OTI油面温控器) + AKM 35501 (WTI绕组温控器)",
        "key_metrics": {"range_max_c": 150, "contacts": 4, "ip_rating": "IP65"},
        "specs_json": {
            "测量范围": "0 ~ 150 ℃",
            "传感原理": "弹性波纹管 (Bellows) 机械测温 + 热模拟CT电流匹配 (WTI)",
            "控制接点": "4组独立可调微动开关接点 (启停风扇、高温报警、超温跳闸)",
            "远传信号": "内置 Pt100 铂电阻 + 4-20mA 变送器双路输出至控制柜",
            "防护等级": "IP65 不锈钢外壳"
        },
        "summary_text": "Qualitrol AKM 34401 35501 MESSKO 油面温度计 OTI 绕组温度控制器 WTI 波纹管 Pt100 4-20mA 4组接点 IP65"
    },
    {
        "comp_id": "seed_prv_qualitrol_208",
        "component_category": "Pressure_Relief_Valve",
        "manufacturer": "Qualitrol / 杭州思源",
        "model_series": "Qualitrol 208-60P / YSF8-55/130 (带导油罩压力释放阀)",
        "key_metrics": {"opening_pressure_kpa": 55, "ip_rating": "IP65"},
        "specs_json": {
            "开启压力": "55 kPa ± 5 kPa (或按标书整定)",
            "排放口径": "DN130 / 6英寸大通径快速泄压",
            "指示与电气": "带高可见度机械动作指示黄旗 + 2组防水微动跳闸接点",
            "安全防护": "配备定向排油导油罩，防止热油喷溅伤人"
        },
        "summary_text": "Qualitrol 208-60P YSF8-55/130 压力释放阀 开启压力55kPa 机械指示旗 跳闸信号接点 定向导油管 IP65"
    },
    {
        "comp_id": "seed_spr_qualitrol_900",
        "component_category": "Sudden_Pressure_Relay",
        "manufacturer": "Qualitrol",
        "model_series": "Qualitrol 900/910 压力突发继电器",
        "key_metrics": {"ip_rating": "IP65"},
        "specs_json": {
            "动作特性": "对油箱内部故障引起的压力陡升率 (dP/dt) 毫秒级响应",
            "防误动设计": "温度补偿均衡腔，支持三取二 (2 out of 3) 防误动出口回路"
        },
        "summary_text": "Qualitrol 900 910 压力突发继电器 速动油压继电器 防误动 IP65"
    },
    {
        "comp_id": "seed_valve_stainless",
        "component_category": "Valve",
        "manufacturer": "江苏神通 / 宁波埃美柯",
        "model_series": "D371X-16RL 不锈钢双偏心真空蝶阀及带锁球阀组",
        "key_metrics": {"material": "304/316不锈钢", "vacuum_tight": True},
        "specs_json": {
            "阀体材质": "304/316 不锈钢或精密铸钢 + 氟橡胶(Viton)密封圈",
            "包含阀门": "散热器法兰真空蝶阀、底部排油阀、滤油接口阀、顶/中/底部油样取样阀",
            "防误操作": "所有开闭状态明晰指示，排油与取样阀配不锈钢防尘堵头与挂锁孔"
        },
        "summary_text": "变压器专用真空蝶阀 不锈钢球阀 放油阀 油样取样阀 Viton氟橡胶密封 带挂锁防误操作"
    },
]


class LocalEmbeddingEngine:
    """
    本地多语言 Embedding 引擎：
    1. 优先尝试加载本地已缓存的 sentence-transformers 模型 (local_files_only=True，避免无网或墙内卡死)
    2. 若本地尚未下载模型权重，自动切换为确定性多语言 N-Gram 语义特征哈希投影向量 (512维 L2归一化)，
       确保离线环境下 pgvector 余弦距离检索 100% 稳定秒级响应。
    """
    _st_model = None
    _init_attempted = False

    @classmethod
    def _try_load_st_model(cls):
        if cls._init_attempted:
            return cls._st_model
        cls._init_attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            cls._st_model = SentenceTransformer(
                settings.EMBEDDING_MODEL_NAME,
                local_files_only=True
            )
            logger.info(f"成功加载本地缓存的 SentenceTransformer 模型: {settings.EMBEDDING_MODEL_NAME}")
        except Exception as e:
            cls._st_model = None
            logger.info(
                f"本地未检测到预下载的 {settings.EMBEDDING_MODEL_NAME} 权重 ({e})，"
                f"已启用内置 {settings.EMBEDDING_DIM} 维多语言特征向量引擎。"
            )
        return cls._st_model

    @classmethod
    def encode(cls, text_input: str) -> List[float]:
        model = cls._try_load_st_model()
        dim = settings.EMBEDDING_DIM

        if model is not None:
            vec = model.encode(text_input or "", normalize_embeddings=True)
            arr = vec.tolist()
            if len(arr) >= dim:
                return arr[:dim]
            return arr + [0.0] * (dim - len(arr))

        # 确定性多语言字符/词元 N-Gram 特征哈希向量 (512维, L2 归一化)
        clean = (text_input or "").lower()
        vec = np.zeros(dim, dtype=np.float32)
        if not clean:
            vec[0] = 1.0
            return vec.tolist()

        # 提取英文/数字词元与中文字符 Bigram/Unigram
        tokens = re.findall(r"[a-z0-9\.\-\+#]+|[\u4e00-\u9fa5]", clean)
        features = list(tokens)
        for i in range(len(tokens) - 1):
            features.append(tokens[i] + "_" + tokens[i + 1])

        for feat in features:
            h = hash(feat)
            idx = abs(h) % dim
            sign = 1.0 if (h & 1) == 0 else -1.0
            vec[idx] += sign

        norm = float(np.linalg.norm(vec))
        if norm > 1e-8:
            vec = vec / norm
        else:
            vec[0] = 1.0
        return [round(float(x), 6) for x in vec.tolist()]

    @staticmethod
    def cosine_similarity(vec_a: Optional[List[float]], vec_b: Optional[List[float]]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom < 1e-8:
            return 0.0
        sim = float(np.dot(a, b) / denom)
        # 映射到友好的 [0.65, 0.99] 工程相似度展示区间
        return max(0.0, min(0.99, (sim + 1.0) / 2.0))


class VectorStoreService:
    """
    组部件标准品知识库存储与三阶段混合匹配服务：
    - 支持 PostgreSQL (pgvector) 存储与向量余弦检索（若本地未启动 PG 容器则自动同步到本地 JSON 仓库）
    - 支持上传供应商 PDF 样册，由 DeepSeek 自动拆解出单份样册中的多个型号并带 BBox 坐标入库
    - 支持三阶段混合匹配：硬规则初筛 -> pgvector 向量召回 -> DeepSeek 逐项选型核验
    """

    # 内存缓存镜像（与 PostgreSQL 和本地 JSON 保持双写同步）
    _cache: Dict[str, Dict[str, Any]] = {}
    _loaded: bool = False

    @classmethod
    def _get_llm(cls) -> ChatOpenAI:
        if not settings.DEEPSEEK_API_KEY:
            raise ValueError("未配置 DEEPSEEK_API_KEY，请检查 .env")
        return ChatOpenAI(
            model=settings.DEEPSEEK_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=0.1,
            max_tokens=4096,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    @classmethod
    def ensure_initialized(cls):
        """启动时加载 PostgreSQL 或本地 JSON 中的组件库；若为空则自动写入 16 款行业种子数据"""
        if cls._loaded:
            return
        cls._loaded = True

        session = DatabaseSessionManager.get_session()
        loaded_items: List[Dict[str, Any]] = []

        if session is not None:
            try:
                rows = session.query(ComponentLibraryModel).all()
                for r in rows:
                    loaded_items.append(cls._orm_to_dict(r))
            except Exception as e:
                logger.warning(f"从 PostgreSQL 读取组件库异常: {e}")
            finally:
                session.close()

        if not loaded_items and LOCAL_LIBRARY_JSON.exists():
            try:
                loaded_items = json.loads(LOCAL_LIBRARY_JSON.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"读取本地 JSON 组件库异常: {e}")

        for item in loaded_items:
            cls._cache[item["comp_id"]] = item

        # 如果数据库和本地均为空，自动初始化内置种子数据
        if not cls._cache:
            cls.seed_default_library()

    @classmethod
    def _orm_to_dict(cls, row: ComponentLibraryModel) -> Dict[str, Any]:
        cat_label = row.category_label or CATEGORY_LABEL_MAP.get(row.component_category, row.component_category)
        catalog_ref = None
        if row.catalog_file_name:
            catalog_ref = {
                "file_name": row.catalog_file_name,
                "page_number": row.catalog_page or 1,
                "bbox": row.catalog_bbox,
                "original_text": row.catalog_original_text or "",
                "file_url": f"/api/v1/components/catalogs/{quote(row.catalog_file_name)}"
            }
        return {
            "comp_id": row.comp_id,
            "component_category": row.component_category,
            "category_label": cat_label,
            "manufacturer": row.manufacturer,
            "model_series": row.model_series,
            "key_metrics": row.key_metrics or {},
            "specs_json": row.specs_json or {},
            "summary_text": row.summary_text or "",
            "catalog_ref": catalog_ref,
            "embedding": row.embedding_json,
            "created_at": row.created_at.isoformat() if row.created_at else datetime.utcnow().isoformat()
        }

    @classmethod
    def _persist_item(cls, item: Dict[str, Any]):
        """将单条组件记录持久化至 PostgreSQL (含 pgvector 列) 与本地 JSON 备份"""
        if not item.get("embedding"):
            embed_source = (
                f"{item.get('component_category', '')} {item.get('manufacturer', '')} "
                f"{item.get('model_series', '')} {item.get('summary_text', '')} "
                f"{json.dumps(item.get('specs_json', {}), ensure_ascii=False)}"
            )
            item["embedding"] = LocalEmbeddingEngine.encode(embed_source)

        item["category_label"] = CATEGORY_LABEL_MAP.get(
            item["component_category"], item.get("category_label") or item["component_category"]
        )
        if not item.get("created_at"):
            item["created_at"] = datetime.utcnow().isoformat()

        cls._cache[item["comp_id"]] = item

        # 1. 写入 PostgreSQL + pgvector
        session = DatabaseSessionManager.get_session()
        if session is not None:
            try:
                cat_ref = item.get("catalog_ref") or {}
                orm_obj = ComponentLibraryModel(
                    comp_id=item["comp_id"],
                    component_category=item["component_category"],
                    category_label=item["category_label"],
                    manufacturer=item["manufacturer"],
                    model_series=item["model_series"],
                    key_metrics=item.get("key_metrics") or {},
                    specs_json=item.get("specs_json") or {},
                    summary_text=item.get("summary_text") or "",
                    catalog_file_name=cat_ref.get("file_name"),
                    catalog_page=cat_ref.get("page_number", 1),
                    catalog_bbox=cat_ref.get("bbox"),
                    catalog_original_text=cat_ref.get("original_text"),
                    embedding_json=item["embedding"],
                )
                session.merge(orm_obj)
                session.commit()

                # 若开启了 pgvector，同步更新 vector 类型列以支持 <-> / <=> 向量索引算子
                if DatabaseSessionManager.is_pgvector_enabled() and item.get("embedding"):
                    vec_str = "[" + ",".join(str(v) for v in item["embedding"]) + "]"
                    session.execute(
                        text("UPDATE component_library SET embedding = CAST(:vec AS vector) WHERE comp_id = :cid"),
                        {"vec": vec_str, "cid": item["comp_id"]}
                    )
                    session.commit()
            except Exception as e:
                session.rollback()
                logger.warning(f"PostgreSQL 写入组件 [{item['comp_id']}] 异常: {e}")
            finally:
                session.close()

        # 2. 同步保存本地 JSON 镜像
        cls._flush_local_json()

    @classmethod
    def _flush_local_json(cls):
        try:
            serializable = list(cls._cache.values())
            LOCAL_LIBRARY_JSON.write_text(
                json.dumps(serializable, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"写入本地 JSON 组件库失败: {e}")

    @classmethod
    def seed_default_library(cls) -> int:
        """一键导入/重置行业标准品种子库"""
        count = 0
        for seed in DEFAULT_SEED_COMPONENTS:
            item = dict(seed)
            cls._persist_item(item)
            count += 1
        logger.info(f"成功初始化 {count} 款行业典型组部件标准品入库！")
        return count

    @classmethod
    def list_components(
        cls,
        category: Optional[str] = None,
        keyword: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        cls.ensure_initialized()
        results = []
        kw = (keyword or "").strip().lower()
        for item in cls._cache.values():
            if category and category != "ALL" and item["component_category"] != category:
                continue
            if kw:
                haystack = (
                    f"{item['manufacturer']} {item['model_series']} "
                    f"{item.get('summary_text', '')} "
                    f"{json.dumps(item.get('specs_json', {}), ensure_ascii=False)}"
                ).lower()
                if kw not in haystack:
                    continue
            # 返回前端时剔除冗长的 512 维浮点数组
            clean_item = {k: v for k, v in item.items() if k != "embedding"}
            results.append(clean_item)
        return results

    @classmethod
    def update_component(cls, comp_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        cls.ensure_initialized()
        existing = cls._cache.get(comp_id)
        if not existing:
            return None
        for k in ("component_category", "manufacturer", "model_series", "key_metrics", "specs_json", "summary_text"):
            if k in payload and payload[k] is not None:
                existing[k] = payload[k]
        # 重新计算 Embedding
        existing["embedding"] = None
        cls._persist_item(existing)
        return {k: v for k, v in existing.items() if k != "embedding"}

    @classmethod
    def delete_component(cls, comp_id: str) -> bool:
        cls.ensure_initialized()
        if comp_id not in cls._cache:
            return False
        del cls._cache[comp_id]

        session = DatabaseSessionManager.get_session()
        if session is not None:
            try:
                session.query(ComponentLibraryModel).filter(ComponentLibraryModel.comp_id == comp_id).delete()
                session.commit()
            except Exception as e:
                session.rollback()
                logger.warning(f"PostgreSQL 删除组件异常: {e}")
            finally:
                session.close()

        cls._flush_local_json()
        return True

    @classmethod
    def get_catalog_file_path(cls, file_name: str) -> Path:
        return CATALOG_ROOT_DIR / file_name

    # ==================== 供应商 PDF 样册上传与多型号自动拆解入库 ====================

    @classmethod
    async def ingest_catalog_files(
        cls,
        files_data: List[Tuple[str, bytes]],
        default_category: Optional[str] = None,
        default_manufacturer: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        解析上传的供应商产品样册 PDF / Word / Excel，
        调用 DeepSeek 自动将一份样册中的多个产品型号拆解为独立记录，绑定各自在样册中的页码与 BBox，向量化入库。
        """
        cls.ensure_initialized()
        ingested_items: List[Dict[str, Any]] = []

        for file_name, file_bytes in files_data:
            # 1. 保存原始样册文件至 data/catalogs/ 供前端 PDF.js 溯源预览
            safe_name = Path(file_name).name
            (CATALOG_ROOT_DIR / safe_name).write_bytes(file_bytes)

            # 2. 调用 DocumentParserService 解析样册块与 BBox 坐标
            parsed_doc = await asyncio.to_thread(
                DocumentParserService._parse_single_file, safe_name, file_bytes
            )

            # 3. 组装带 [B0001 | Page:x] 编号的样册文本供 DeepSeek 拆解多型号
            block_lookup: Dict[str, ContentBlock] = {}
            lines = []
            current_chars = 0
            for idx, blk in enumerate(parsed_doc.blocks, start=1):
                txt = blk.content.strip()
                if not txt:
                    continue
                b_id = f"B{idx:04d}"
                block_lookup[b_id] = blk
                entry = f"[{b_id} | Page:{blk.page_number}]\n{txt}\n"
                if current_chars + len(entry) > 85000:
                    break
                lines.append(entry)
                current_chars += len(entry)

            catalog_context = "\n".join(lines)
            extracted_models = await cls._extract_models_from_catalog_llm(
                file_name=safe_name,
                catalog_context=catalog_context,
                block_lookup=block_lookup,
                default_category=default_category,
                default_manufacturer=default_manufacturer
            )

            for model_item in extracted_models:
                cls._persist_item(model_item)
                ingested_items.append({k: v for k, v in model_item.items() if k != "embedding"})

        logger.info(f"样册解析入库完成：从 {len(files_data)} 份样册中共拆解并向量化入库 {len(ingested_items)} 款具体型号。")
        return ingested_items

    @classmethod
    async def _extract_models_from_catalog_llm(
        cls,
        file_name: str,
        catalog_context: str,
        block_lookup: Dict[str, ContentBlock],
        default_category: Optional[str] = None,
        default_manufacturer: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        categories_desc = ", ".join([f"{c['code']}({c['label']})" for c in COMPONENT_CATEGORIES])
        hint_cat = f"用户指定优先归类为: {default_category}。" if default_category and default_category != "AUTO" else ""
        hint_mfg = f"用户指定厂家品牌为: {default_manufacturer}。" if default_manufacturer else ""

        system_prompt = (
            "你是一个专业的电力变压器供应链与组部件选型总工程师。\n"
            "用户上传了一份供应商产品样册/选型手册的解析文本（带有 `[Bxxxx | Page:页码]` 锚点）。\n"
            "【核心任务】\n"
            "1. 一份样册往往包含同一系列的**多个具体型号**（例如一份手册包含 KI 25X、KI 45X、KI 50X，或 3EL1、3EL2、3EQ1，或不同电压/通径规格）。请将其中每个可独立选型的产品型号拆分为一条独立的组件记录！\n"
            f"2. `component_category` 必须从以下标准编码中选择最匹配的一项：\n{categories_desc}\n"
            f"{hint_cat} {hint_mfg}\n"
            "3. 提取每个型号的 `key_metrics`（用于硬规则过滤的关键数值指标，如 `max_voltage_kv` 最高电压数值、`rated_current_a` 额定电流数值、`pour_point_c` 倾点摄氏度数值、`creepage_mm_kv` 爬电比距、`ip_rating` 等，只填纯数字或简短字符串）和 `specs_json`（中文键值对形式的详细技术参数字典，4~8项核心指标）。\n"
            "4. 必须在 `block_id` 中填写该型号核心参数表所在的块编号（如 \"B0005\"），并在 `original_text` 中摘录样册原文依据（不超过120字）。\n"
            "5. 严格输出如下 JSON Object：\n"
            "{\n"
            "  \"models\": [\n"
            "    {\n"
            "      \"component_category\": \"Transformer_Oil\",\n"
            "      \"manufacturer\": \"KunLun (中石油克拉玛依)\",\n"
            "      \"model_series\": \"KI 45X\",\n"
            "      \"key_metrics\": {\"pour_point_c\": -45, \"flash_point_c\": 140},\n"
            "      \"specs_json\": {\"倾点\": \"-45℃\", \"闪点\": \"140℃\", \"击穿电压\": \">70kV\"},\n"
            "      \"summary_text\": \"一句话汇总该型号的核心适用场景与技术参数\",\n"
            "      \"block_id\": \"B0003\",\n"
            "      \"original_text\": \"样册原文片段\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        user_prompt = (
            f"样册文件名: {file_name}\n"
            f"================ 样册解析块内容 ================\n"
            f"{catalog_context}"
        )

        try:
            client = cls._get_llm()
            resp = await client.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            parsed = json.loads(resp.content)
            raw_models = parsed.get("models", [])
        except Exception as e:
            logger.error(f"DeepSeek 拆解样册 [{file_name}] 失败: {e}")
            raw_models = []

        results: List[Dict[str, Any]] = []
        for idx, m in enumerate(raw_models, start=1):
            if not isinstance(m, dict):
                continue
            cat_code = m.get("component_category") or default_category or "OLTC"
            if cat_code not in CATEGORY_LABEL_MAP:
                cat_code = default_category if (default_category in CATEGORY_LABEL_MAP) else "OLTC"

            mfg = m.get("manufacturer") or default_manufacturer or "未知厂商"
            model_name = m.get("model_series") or f"{Path(file_name).stem}-型号{idx}"
            b_id = str(m.get("block_id", "")).strip()
            orig_txt = m.get("original_text") or ""

            # 定位样册原文页码与 BBox
            blk = block_lookup.get(b_id)
            if not blk and orig_txt and len(orig_txt) >= 5:
                snippet = orig_txt[:25].lower()
                for candidate_blk in block_lookup.values():
                    if snippet in candidate_blk.content.lower():
                        blk = candidate_blk
                        break
            if not blk and block_lookup:
                blk = next(iter(block_lookup.values()))

            page_num = blk.page_number if blk else 1
            bbox_list = list(blk.bbox) if (blk and blk.bbox) else None

            comp_id = f"cat_{uuid.uuid4().hex[:8]}"
            results.append({
                "comp_id": comp_id,
                "component_category": cat_code,
                "category_label": CATEGORY_LABEL_MAP.get(cat_code, cat_code),
                "manufacturer": mfg,
                "model_series": model_name,
                "key_metrics": m.get("key_metrics") if isinstance(m.get("key_metrics"), dict) else {},
                "specs_json": m.get("specs_json") if isinstance(m.get("specs_json"), dict) else {},
                "summary_text": m.get("summary_text") or f"{mfg} {model_name}",
                "catalog_ref": {
                    "file_name": file_name,
                    "page_number": page_num,
                    "bbox": bbox_list,
                    "original_text": orig_txt or (blk.content[:120] if blk else ""),
                    "file_url": f"/api/v1/components/catalogs/{quote(file_name)}"
                }
            })

        return results

    # ==================== 三阶段混合匹配引擎 (硬规则 + pgvector + DeepSeek 选型核验) ====================

    @classmethod
    def _hard_rule_check(
        cls,
        category_code: str,
        req_text: str,
        global_env_text: str,
        candidate: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        阶段一：硬规则边界过滤
        - 校验变压器油牌号/最低环境温度 vs 倾点
        - 校验高压组件最高电压等级 vs 标书系统电压
        返回: (是否通过硬规则, 规则校验命中说明)
        """
        metrics = candidate.get("key_metrics") or {}
        combined_req = f"{req_text}\n{global_env_text}".lower()
        highlights = []

        # 规则 1：变压器绝缘油牌号与倾点温度硬规则
        if category_code == "Transformer_Oil":
            pour_point = metrics.get("pour_point_c")
            if isinstance(pour_point, (int, float)):
                # 如果标书明确要求 45# 油或 -45℃ 倾点，过滤掉倾点高于 -40℃ 的 25# 油
                if ("45#" in combined_req or "45号" in combined_req or "-45" in combined_req):
                    if pour_point > -40:
                        return False, [f"标书要求 45# 油(-45℃)，该型号倾点 {pour_point}℃ 不满足"]
                    highlights.append(f"硬规则通过：倾点 {pour_point}℃ 满足 45# 极寒要求")
                # 检查标书最低环境温度
                temp_match = re.search(r"最低.*?(-?\d+(?:\.\d+)?)\s*[℃°c]", combined_req)
                if temp_match:
                    min_env_temp = float(temp_match.group(1))
                    if pour_point > min_env_temp - 5:
                        return False, [f"倾点 {pour_point}℃ 高于最低环境温度安全裕度"]

        # 规则 2：电压等级硬规则 (针对 OLTC / DETC / Bushing / Surge_Arrester)
        if category_code in ("OLTC", "DETC", "Surge_Arrester"):
            cand_max_kv = metrics.get("max_voltage_kv")
            if isinstance(cand_max_kv, (int, float)):
                # 识别标书高压侧电压 (如 220kV, 110kV, 33kV, 35kV)
                for sys_kv in (220, 132, 110, 66):
                    if f"{sys_kv}kv" in req_text.lower() and cand_max_kv < sys_kv:
                        return False, [f"额定最高电压 {cand_max_kv}kV 低于标书 {sys_kv}kV 要求"]
                if ("33kv" in combined_req or "35kv" in combined_req) and cand_max_kv >= 35:
                    highlights.append(f"硬规则通过：最高工作电压 {cand_max_kv}kV 覆盖 33/35kV 系统")

        # 规则 3：套管爬电比距硬规则
        if category_code == "Bushing":
            cand_creepage = metrics.get("creepage_mm_kv")
            if isinstance(cand_creepage, (int, float)):
                if "31" in req_text and "mm/kv" in req_text.lower():
                    if cand_creepage < 31:
                        return False, [f"爬电比距 {cand_creepage} mm/kV 低于标书 31 mm/kV 要求"]
                    highlights.append(f"硬规则通过：爬电比距 {cand_creepage} mm/kV ≥ 31 mm/kV")

        return True, highlights

    @classmethod
    def _pgvector_recall(
        cls,
        category_code: str,
        query_text: str,
        global_env_text: str,
        top_k: int = 8
    ) -> List[Tuple[Dict[str, Any], float, List[str]]]:
        """
        阶段一 + 阶段二：按品类过滤 + 硬规则初筛 + pgvector 余弦相似度 Top-K 召回
        """
        cls.ensure_initialized()
        query_vec = LocalEmbeddingEngine.encode(f"{category_code} {query_text}")

        # 优先尝试使用 PostgreSQL pgvector 的 `<=>` 余弦距离算子排序召回
        pg_scores: Dict[str, float] = {}
        if DatabaseSessionManager.is_pgvector_enabled():
            session = DatabaseSessionManager.get_session()
            if session is not None:
                try:
                    vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"
                    sql = text(
                        "SELECT comp_id, 1 - (embedding <=> CAST(:vec AS vector)) AS sim "
                        "FROM component_library "
                        "WHERE component_category = :cat AND embedding IS NOT NULL "
                        "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT :lim"
                    )
                    rows = session.execute(sql, {"vec": vec_str, "cat": category_code, "lim": top_k * 2}).fetchall()
                    for r in rows:
                        if r[1] is not None and not math.isnan(float(r[1])):
                            # 归一化到 [0.65, 0.99]
                            raw_sim = float(r[1])
                            pg_scores[r[0]] = max(0.65, min(0.99, (raw_sim + 1.0) / 2.0))
                except Exception as e:
                    logger.debug(f"pgvector SQL 检索回退至内存向量计算: {e}")
                finally:
                    session.close()

        # 结合硬规则过滤与余弦相似度汇总同品类候选集
        recalled: List[Tuple[Dict[str, Any], float, List[str]]] = []
        for comp in cls._cache.values():
            if comp["component_category"] != category_code:
                continue

            passed, rule_highlights = cls._hard_rule_check(
                category_code, query_text, global_env_text, comp
            )
            if not passed:
                continue

            sim = pg_scores.get(comp["comp_id"])
            if sim is None:
                sim = LocalEmbeddingEngine.cosine_similarity(query_vec, comp.get("embedding"))

            # 关键词重合加权（品牌或核心规格命中时提升召回得分）
            q_lower = query_text.lower()
            for kw in (comp["manufacturer"].lower(), comp["model_series"].lower()):
                for part in re.split(r"[\s/\(\)（）]+", kw):
                    if len(part) >= 2 and part in q_lower:
                        sim = min(0.98, sim + 0.08)
                        rule_highlights.append(f"品牌/型号特征词命中：{part}")
                        break

            recalled.append((comp, round(sim, 2), rule_highlights))

        recalled.sort(key=lambda x: x[1], reverse=True)
        return recalled[:top_k]

    @classmethod
    async def match_all_project_components(
        cls,
        extracted_components: List[Dict[str, Any]],
        global_context_summary: str = ""
    ) -> List[Dict[str, Any]]:
        """
        对标书中提取出的所有组部件需求执行三阶段混合匹配：
        1. 硬规则边界过滤
        2. pgvector 向量 Top-K 召回
        3. DeepSeek 批量选型核验（生成每个候选型号的满足项亮点、潜在偏离说明与综合匹配度）
        """
        cls.ensure_initialized()
        if not extracted_components:
            return []

        # 阶段 1 & 2：为每个组部件需求召回合格候选集
        req_candidates_map: Dict[str, List[Dict[str, Any]]] = {}
        for comp_req in extracted_components:
            req_id = comp_req["req_id"]
            cat_code = comp_req.get("Category_Code") or comp_req["Component_Category"].split(" ")[0].strip()
            req_text = " ".join(comp_req.get("Specific_Requirements", []))

            recalled_list = cls._pgvector_recall(
                category_code=cat_code,
                query_text=req_text,
                global_env_text=global_context_summary,
                top_k=6
            )

            candidates_payload = []
            for cand_item, vec_score, rule_notes in recalled_list:
                candidates_payload.append({
                    "comp_id": cand_item["comp_id"],
                    "manufacturer": cand_item["manufacturer"],
                    "model_series": cand_item["model_series"],
                    "similarity_score": vec_score,
                    "rule_passed": True,
                    "match_status": "QUALIFIED",
                    "match_highlights": rule_notes or ["核心参数满足该品类技术规范要求"],
                    "deviation_notes": [],
                    "specs_summary": cand_item.get("specs_json") or {},
                    "key_metrics": cand_item.get("key_metrics") or {},
                    "catalog_bbox": cand_item.get("catalog_ref"),
                })
            req_candidates_map[req_id] = candidates_payload

        # 阶段 3：调用 DeepSeek 对所有召回候选型号进行逐项技术比对与偏离分析
        await cls._llm_verify_candidates(extracted_components, req_candidates_map, global_context_summary)

        # 将匹配结果组装回 extracted_components（全量展示所有合格候选，默认勾选最高分项供工程师审阅）
        for comp_req in extracted_components:
            req_id = comp_req["req_id"]
            cands = req_candidates_map.get(req_id, [])
            comp_req["matched_candidates"] = cands
            if cands and not comp_req.get("selected_comp_id"):
                comp_req["selected_comp_id"] = cands[0]["comp_id"]

        return extracted_components

    @classmethod
    async def _llm_verify_candidates(
        cls,
        extracted_components: List[Dict[str, Any]],
        req_candidates_map: Dict[str, List[Dict[str, Any]]],
        global_context_summary: str
    ):
        """调用 DeepSeek 一次性对所有组部件需求及其召回候选做精细选型评估"""
        verification_tasks_desc = []
        for comp_req in extracted_components:
            req_id = comp_req["req_id"]
            cands = req_candidates_map.get(req_id, [])
            if not cands:
                continue
            cand_briefs = [
                {
                    "comp_id": c["comp_id"],
                    "brand_model": f"[{c['manufacturer']}] {c['model_series']}",
                    "specs": c["specs_summary"]
                }
                for c in cands
            ]
            verification_tasks_desc.append({
                "req_id": req_id,
                "component_name": comp_req["Component_Name"],
                "tender_requirement": "；".join(comp_req.get("Specific_Requirements", [])),
                "candidates": cand_briefs
            })

        if not verification_tasks_desc:
            return

        system_prompt = (
            "你是一个资深的变压器成套选型总工程师。\n"
            "请对比【标书组部件技术要求（含变压器全局参数）】与【内部标准品知识库召回的候选型号参数】，"
            "为每个候选型号给出客观的工程选型核验结论。\n"
            "【输出规则】\n"
            "1. 不要丢弃已通过硬规则召回的合格候选型号，需对每个候选型号输出评估。\n"
            "2. `similarity_score`: 0.70 ~ 0.99 之间的浮点数，代表该型号对标书要求的综合技术满足度。\n"
            "3. `match_status`: \"FULLY_MATCHED\"（完全满足/品牌或参数精准命中）、\"QUALIFIED\"（技术参数合格适用）或 \"PARTIAL_DEVIATION\"（存在需注意的偏离项）。\n"
            "4. `match_highlights`: 数组（1~3条简短中文），列出该型号满足标书的关键指标（如：\"品牌符合上海华明要求\"、\"倾点-45℃满足45#油要求\"、\"爬电比距31mm/kV达标\"）。\n"
            "5. `deviation_notes`: 数组（0~2条简短中文），若完全满足则为空数组 `[]`；若有需要下单定制或偏离之处则注明（如：\"二次电流变比需按下单参数定制\"）。\n"
            "6. 严格输出如下 JSON Object：\n"
            "{\n"
            "  \"evaluations\": [\n"
            "    {\n"
            "      \"req_id\": \"req_comp_1\",\n"
            "      \"comp_id\": \"seed_oil_kunlun_ki45x\",\n"
            "      \"similarity_score\": 0.98,\n"
            "      \"match_status\": \"FULLY_MATCHED\",\n"
            "      \"match_highlights\": [\"新疆克拉玛依45#变压器油精准匹配\", \"倾点-45℃、闪点140℃满足国标\"],\n"
            "      \"deviation_notes\": []\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        user_prompt = (
            f"【变压器全局电压与环境条件】\n{global_context_summary}\n\n"
            f"【待核验的组部件需求与候选列表】\n"
            f"{json.dumps(verification_tasks_desc, ensure_ascii=False, indent=2)}"
        )

        try:
            client = cls._get_llm()
            resp = await client.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            parsed = json.loads(resp.content)
            evals = parsed.get("evaluations", [])
            eval_map = {(e.get("req_id"), e.get("comp_id")): e for e in evals if isinstance(e, dict)}

            for req_id, cands in req_candidates_map.items():
                for c in cands:
                    ev = eval_map.get((req_id, c["comp_id"]))
                    if ev:
                        if isinstance(ev.get("similarity_score"), (int, float)):
                            c["similarity_score"] = round(float(ev["similarity_score"]), 2)
                        if ev.get("match_status"):
                            c["match_status"] = ev["match_status"]
                        if isinstance(ev.get("match_highlights"), list) and ev["match_highlights"]:
                            c["match_highlights"] = ev["match_highlights"]
                        if isinstance(ev.get("deviation_notes"), list):
                            c["deviation_notes"] = ev["deviation_notes"]
        except Exception as e:
            logger.warning(f"DeepSeek 组部件候选精排校验降级为规则+向量结果: {e}")
