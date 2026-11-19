import json
import asyncio
from typing import List, Dict, Any, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger

from app.core.config import settings
from app.schemas.document_schema import ProjectMemoryStore, ContentBlock

# 完整对齐《二期字段_2.xlsx》的提取字段清单与梳理提示要求
PHASE2_FIELDS_SPEC: List[Tuple[str, str]] = [
    # --- 第一批次：基本电气参数与调压开关 (1 ~ 2.4) ---
    ("1.1 变压器的相数", "提取变压器的相数，如 3相 / 单相"),
    ("1.2 变压器的频率", "提取额定频率，如 50Hz / 60Hz"),
    ("1.3 各个电压等级对应的额定电压、绝缘水平、联结组别方式、容量，电压的调压范围", "梳理HV/MV/LV各侧额定电压、LI/AC绝缘水平、联结组别(如YNd11)、容量(MVA)及调压范围"),
    ("1.4 空负载是否有损耗或效率要求，空负载是否有损耗价格评估的要求", "梳理空载损耗、负载损耗保证值、效率要求及损耗惩罚/资本化评估公式"),
    ("1.5 温升的要求，顶层油的温升要求、绕组平均温升的要求、绕组最热点处的温升要求、铁芯的温升要求、油箱的温升要求等", "提取顶层油、绕组平均、绕组热点、铁芯及油箱温升限值(K)"),
    ("1.6 噪音的要求", "确认是声压级(Sound Pressure)还是声功率(Sound Power)噪音要求及dB(A)限值，如无明确要求输出“未提及”"),
    ("1.7 电流密度和磁通密度的要求", "提取绕组最大电流密度(A/mm²)和铁芯最大磁通密度(T)限值"),
    ("1.8 变压器的冷却型式", "如 ONAN, ONAF, OFAF, ODAF, KNAN, KNAF 等"),
    ("1.9 变压器需要满足的标准", "如 IEC 60076, IEEE C57, GB 1094 等"),
    ("1.10 变压器的过励磁和过负荷（过载）要求", "梳理过励磁能力(U/f曲线或百分比/时间)及应急过负荷要求"),
    ("2.1 调压开关型式", "如有载分接开关(OLTC)、无励磁分接开关(DETC)"),
    ("2.2 调压开关的厂家是否有要求", "提取分接开关指定或推荐品牌，如 MR (Reinhausen), ABB, 华明等"),
    ("2.3.1 分接开关额定电压", "分接开关额定电压"),
    ("2.3.2 分接开关额定电流", "分接开关额定通过电流"),
    ("2.3.3 分接开关调压范围与级数", "如 ±8×1.25% 或 ±10% 共17级等"),
    ("2.3.4 分接开关过渡阻抗类型与参数", "电阻式还是电抗式过渡，熄弧方式(真空/油浸)"),
    ("2.3.5 分接开关绝缘水平", "分接开关对地及级间绝缘水平"),
    ("2.3.6 分接开关机械寿命与电气寿命，免维护的使用次数", "机械切换次数、电气切换次数及免维护次数要求"),
    ("2.3.7 分接开关开关操作机构切换时间", "切换时间要求"),
    ("2.3.8 分接开关开关控制柜及驱动机构的要求", "电动机构型号、电源、防护要求"),
    ("2.3.9 分接开关操作方式", "本地手动、电动、远方自动等"),
    ("2.3.10 自动电压调整器(AVR)要求", "有没有AVR要求、通讯协议方式、品牌和型号要求"),
    ("2.3.11 是否需要远程控制柜RTCC", "是否要求提供RTCC远方调压控制柜"),
    ("2.3.12 有载开关的通讯要求", "IEC 61850, Modbus, DNP3 等"),
    ("2.3.13 有载开关的控制柜特殊要求", "是否要求控制柜材质、加热防凝露等功能要求"),
    ("2.3.14 是否有并联运行需求", "是否要求支持主从/环流法并联运行控制"),
    ("2.4 无载开关/无励磁分接开关DETC要求", "是否要求开关的额定电压、额定电流、调压范围、绝缘水平、触头压力、操作力矩、机械寿命、操作方式(手动/电动)、单开关控制调压要求"),

    # --- 第二批次：核心主材与组部件要求 (3 ~ 19) ---
    ("3.套管", "梳理设备最高电压Um(kV), 雷电冲击LI(kV), 操作冲击SI(kV), 工频耐压AC(kV), 套管电流(A), 额定相对地电压(kV), 短路电流(kA/s), 爬电距离, 套管类型(油纸/RIP/RIS), 绝缘材料, 颜色, 尺寸, 厂家偏好及型号, 是否需要电缆罩(enclosure)"),
    ("4.避雷器", "梳理厂家及制造商偏好及型号要求，各电压等级绝缘要求、持续运行电压MCOV/Ur，避雷器材料(瓷套/复合硅橡胶)，避雷器标准及放电电流等级"),
    ("5.硅钢片", "梳理厂家及制造商偏好及型号要求，硅钢片材料(取向硅钢/激光刻痕)，单位铁损(W/kg)，厚度要求(如0.23/0.27mm)，适用标准"),
    ("6.变压器绕组线圈电磁线", "梳理厂家偏好，材料要求(无氧铜等)，绕组短路电流要求，导线型式(换位导线CTC/组合导线)，外包绝缘材料(是否需热改性纸TUP及品牌型号、耐热等级)，内部油道要求，是否禁止使用内置避雷器(非线性元件)"),
    ("7.绝缘油", "绝缘油类型(矿物油/天然酯/合成酯)，厂家偏好及型号要求，理化电气性能(倾点、闪点、击穿电压、腐蚀性硫等)，是否有备用油比例要求，运输方式"),
    ("8.变压器冷却系统", "品牌及型号要求，片式散热器要求(是否需热镀锌、颜色、布置方式)，移除一组是否不影响温升(N-1冗余)，风扇要求(功率/风量/材料/噪音/品牌/重量/位置)，油泵要求，散热器/风扇/油泵数量要求"),
    ("9.电流互感器", "品牌及制造商偏好及型号要求，每个电压等级套管升高座中BCT电流互感器的电流变比、精度等级(如0.2/5P20)、容量负荷(VA)、数量要求"),
    ("10.变压器本体控制柜及风冷控制柜", "外壳材质及厚度要求，辅助电源电压及型式，是否带漏电保护，控制电缆是否要求低烟无卤阻燃，端子要求，外部布线方式(钢管或镀锌管/金属软管)，网络交换机要求"),
    ("11.油补偿系统", "品牌及型号要求(Inert-gas氮气密封还是Conservator储油柜系统)，油量要求，油补偿系统对本体和开关储油柜胶囊/隔膜的要求"),
    ("12.呼吸器", "品牌及制造商偏好或推荐及型号要求(如Qualitrol/MR)，硅胶免维护/自再生要求，是否有自加热除湿功能，通讯要求"),
    ("13.油位计", "品牌及制造商偏好及型号要求，远传触点与4-20mA通讯要求"),
    ("14.气体继电器", "品牌及制造商偏好及型号要求(如EMB)，地面取气装置及测试装置要求，抗震要求，是否需要双浮子(Double-float)，跳闸/报警接点与通讯要求"),
    ("15.油面温度计和绕组温度计", "品牌及型号要求，温度测量范围，是否要求波纹管技术或布尔登管技术，通讯要求(Pt100/4-20mA/Modbus)，油温计(OTI)和绕组温控器(WTI)的数量要求"),
    ("16.压力释放阀", "品牌及制造商偏好及型号要求，开启压力，数量要求，机械动作指示旗要求，报警/跳闸电气接点与通讯要求，是否带导油管定向喷油"),
    ("17.压力突发继电器", "品牌及制造商偏好及型号要求，通讯要求，是否有 2 out of 3 (三取二) 逻辑防误动要求"),
    ("18.第10条到第17条的IP防护与防腐要求", "上述组部件及控制柜是否有IP等级要求(如IP55/IP65/IP66)，是否有防腐等级要求(参照ISO 12944定义的C3、C4、C5或C5-M/H)"),
    ("19.变压器中阀门", "品牌及制造商偏好及型号要求，阀门材质要求(如不锈钢/黄铜/铸钢)，蝶阀/球阀及取样阀数量与带锁要求"),

    # --- 第三批次：运输、在线监测、油箱本体、特殊要求与商务 (20 ~ 30) ---
    ("20.运输要求，冲撞记录仪的要求", "冲撞记录仪要求(品牌/型号/数量/是否带GPS三维记录)，运输冲击加速度限值(g)，运输方式(带油/充氮)，尺寸及重量限制"),
    ("21.1 光纤测温装置/直接测量温度/预估寿命", "是否有绕组光纤测温装置要求、通道数及品牌要求"),
    ("21.2 气体在线监测装置/油色谱", "是否有DGA油中溶解气体在线监测装置(单氢或全组分油色谱)及品牌要求"),
    ("21.3 充氮灭火装置(是否需要防爆功能)", "是否要求配置排油注氮灭火装置及防爆要求"),
    ("21.4 套管在线监测装置", "是否有套管介损及电容量在线监测要求"),
    ("21.5 局放监测装置", "是否有局部放电(PD)在线监测装置或UHF传感器要求"),
    ("21.6 胶囊泄露监测", "是否有储油柜胶囊破裂/泄露监测传感器要求"),
    ("21.7 信号集中器", "是否有IED智能电子设备/信号集中器汇总上送要求"),
    ("21.8 铁心接地电流监测要求", "是否有铁芯及夹件接地电流在线监测要求"),
    ("21.9 SEL 品牌的组件", "标书中是否指定使用 SEL (Schweitzer Engineering Laboratories) 品牌的保护或测控组件"),
    ("21.10 变压器综合在线监测", "综合在线监测系统架构及通讯规约要求"),
    ("22.油箱本体", "梳理油箱正压/真空机械强度，防腐涂层规格，箱盖固定方式(螺栓/焊接)，焊缝无损探伤测试，紧固件材质，小车/滚轮，减震垫，箱盖防滑漆，油箱防爆要求，电缆罩，本体与开关储油柜，油箱接地CT需求，组件布置要求，油箱钢板材料要求，压力变形试验标准及变形量限值"),
    ("23.密封件", "垫圈与密封件材料(如丁腈橡胶NBR/氟橡胶Viton)，耐热等级及无石棉要求"),
    ("24.1 中性点接地装置要求", "中性点接地隔离开关/电流互感器等装置要求"),
    ("24.2 中性点接地电阻要求", "中性点接地电阻器(NGR)阻值、通流时间及温升要求"),
    ("24.3 防跌落系统要求", "变压器顶部高空作业防跌落安全栓系系统(Fall arrest system)要求"),
    ("24.4 热虹吸过滤器要求", "是否需要热虹吸净油器(Thermosiphon filter)"),
    ("24.5 火灾探测器要求", "感温/火焰火灾探测器要求"),
    ("24.6 在线干燥设备的要求", "在线微水净油/呼吸干燥器要求"),
    ("24.7 滤油装置的要求", "真空滤油装置接口或随附设备要求"),
    ("25.标书的特殊点", "是否需要抗震要求(AG2/AG5等)、抗震计算报告是否需第三方认证；变压器是否需第三方认证(如 CE, UL, CSA 等)"),
    ("26.变压器所处的环境条件", "海拔高度(m)，年平均/日平均/月平均温度，年最高温度与最低环境温度(℃)，污秽等级(如III/IV级)，地震烈度"),
    ("27.备品备件", "标书要求的强制性或推荐性备品备件清单(如备用套管、密封圈等)"),
    ("28.招标文件中有哪些试验要求", "梳理例行试验、型式试验、特殊试验及现场交接试验项目"),
    ("29.招标文件的交货方式、贸易术语及质保期", "交货期、贸易术语(Incoterms如DDP/CIF/FOB)及质保期(月/年)"),
    ("30.铁芯和绕组的绝缘有没有玻璃纤维的要求", "铁芯绑扎带或绕组绝缘中关于玻璃纤维(Fiberglass)的使用或禁用要求"),
]


class DeepSeekExtractionService:
    """基于 DeepSeek 的标书二期字段真实提取与 BBox 坐标映射服务"""

    @classmethod
    def _get_client(cls) -> ChatOpenAI:
        if not settings.DEEPSEEK_API_KEY:
            raise ValueError("未检测到 DEEPSEEK_API_KEY，请检查 .env 配置文件！")
        return ChatOpenAI(
            model=settings.DEEPSEEK_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=0.1,
            max_tokens=4096,
            # DeepSeek 兼容 OpenAI 的 JSON 输出模式，ChatOpenAI 通过 model_kwargs 透传
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    @classmethod
    def _build_indexed_context(cls, memory: ProjectMemoryStore, max_chars: int = 95000) -> Tuple[str, Dict[str, Tuple[str, ContentBlock]]]:
        """
        将内存中解析出的所有文档块组装为带简短唯一 ID (如 B0001) 的上下文文本，
        同时构建 block_lookup 字典，方便大模型返回 block_id 后瞬间查出真实 BBox 坐标。
        """
        lines = []
        block_lookup: Dict[str, Tuple[str, ContentBlock]] = {}
        counter = 1
        current_len = 0

        # 优先排列技术规范与参数表，其次商务标
        sorted_docs = sorted(
            memory.documents.values(),
            key=lambda d: 0 if d.category.value in ("boq_list", "technical_spec") else 1
        )

        for doc in sorted_docs:
            for block in doc.blocks:
                content_str = block.content.strip()
                if not content_str:
                    continue
                b_key = f"B{counter:04d}"
                block_lookup[b_key] = (doc.file_name, block)
                counter += 1

                entry = f"[{b_key} | File:{doc.file_name} | Page:{block.page_number}]\n{content_str}\n"
                if current_len + len(entry) > max_chars:
                    break
                lines.append(entry)
                current_len += len(entry)

        return "\n".join(lines), block_lookup

    @classmethod
    async def _extract_field_batch(
        cls,
        client: ChatOpenAI,
        context_text: str,
        field_batch: List[Tuple[str, str]],
        block_lookup: Dict[str, Tuple[str, ContentBlock]],
        default_file: str
    ) -> List[Dict[str, Any]]:
        """单批次调用 DeepSeek 提取指定字段集合"""
        fields_desc = "\n".join([f"- 字段名: \"{k}\" | 提取要求: {desc}" for k, desc in field_batch])

        system_prompt = (
            "你是一个资深的变压器制造总工程师与海外标书解析专家。\n"
            "请仔细阅读用户提供的招标文件解析块（每个块顶部标有 `[Bxxxx | File:文件名 | Page:页码]`），"
            "严格按照给定的《二期标准字段清单》提取对应的技术与商务参数。\n\n"
            "【核心纪律】\n"
            "1. 零幻觉原则：必须100%忠实于标书原文。若标书中确实未提及某项要求，请将 `param_value` 设为 \"未提及\"，`original_text` 设为 \"\"，`block_id` 设为 \"\"。\n"
            "2. 跨文档冲突检测：如果参数表(TDS)与技术规范正文对同一参数描述不一致（例如最高环境温度一处写45℃另一处写50℃），请在 `param_value` 中同时注明两个值，并将 `has_conflict` 设为 true。\n"
            "3. 溯源锚定：对于每一个提取出的参数，必须在 `block_id` 中填写其最核心依据所在的块编号（例如 \"B0015\"），并在 `original_text` 中摘录原句（不超过150字）。\n"
            "4. 必须严格输出合法的 JSON Object，格式如下：\n"
            "{\n"
            "  \"items\": [\n"
            "    {\n"
            "      \"param_key\": \"必须与输入的字段名完全一致\",\n"
            "      \"param_value\": \"提取出的具体数值或未提及\",\n"
            "      \"original_text\": \"原文依据原句摘录\",\n"
            "      \"block_id\": \"B0015\",\n"
            "      \"has_conflict\": false\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        user_prompt = (
            f"请从以下招标文件内容中，逐一提取这 {len(field_batch)} 个标准字段：\n"
            f"{fields_desc}\n\n"
            f"================ 招标文件解析块内容 ================\n"
            f"{context_text}"
        )

        response = await client.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        raw_json = response.content
        parsed_data = json.loads(raw_json)
        items_list = parsed_data.get("items", [])

        # 将模型输出映射为前端 Review.vue 所需的 MainParameterItem 结构，并回填精确 BBox
        extracted_Map = {item.get("param_key"): item for item in items_list if isinstance(item, dict)}
        formatted_results = []

        for field_key, _ in field_batch:
            ext_item = extracted_Map.get(field_key, {})
            val = ext_item.get("param_value") or "未提及"
            orig_text = ext_item.get("original_text") or ""
            b_id = str(ext_item.get("block_id", "")).strip()
            has_conflict = bool(ext_item.get("has_conflict", False))

            # 根据 block_id 查找真实的 PDF 文件名、页码与 PyMuPDF BBox 坐标
            if b_id in block_lookup:
                fname, blk = block_lookup[b_id]
                source_ref = {
                    "file_name": fname,
                    "page_number": blk.page_number,
                    "bbox": list(blk.bbox) if blk.bbox else None,
                    "original_text": orig_text or blk.content[:120]
                }
            else:
                # 兜底：若模型未返回有效 block_id 但返回了 original_text，在全文块中做子串检索定位 BBox
                matched_ref = None
                if orig_text and len(orig_text) >= 6:
                    snippet = orig_text[:30].lower()
                    for fname, blk in block_lookup.values():
                        if snippet in blk.content.lower():
                            matched_ref = {
                                "file_name": fname,
                                "page_number": blk.page_number,
                                "bbox": list(blk.bbox) if blk.bbox else None,
                                "original_text": orig_text
                            }
                            break
                source_ref = matched_ref or {
                    "file_name": default_file,
                    "page_number": 1,
                    "bbox": None,
                    "original_text": orig_text
                }

            formatted_results.append({
                "param_key": field_key,
                "param_value": str(val),
                "original_text": orig_text,
                "has_conflict": has_conflict,
                "source_ref": source_ref
            })

        return formatted_results

    @classmethod
    async def run_full_extraction(cls, memory: ProjectMemoryStore) -> ProjectMemoryStore:
        """并发执行《二期字段_2.xlsx》全量主参数与关键组部件提取"""
        client = cls._get_client()
        context_text, block_lookup = cls._build_indexed_context(memory)

        pdf_docs = [d for d in memory.documents.values() if d.file_ext == '.pdf']
        default_file = pdf_docs[0].file_name if pdf_docs else (
            list(memory.documents.values())[0].file_name if memory.documents else ""
        )

        # 将 68 个细化字段切分为 3 个批次并发请求 DeepSeek，兼顾速度与完整性
        batch_size = 23
        batches = [
            PHASE2_FIELDS_SPEC[i:i + batch_size]
            for i in range(0, len(PHASE2_FIELDS_SPEC), batch_size)
        ]

        logger.info(f"开始调用 DeepSeek ({settings.DEEPSEEK_MODEL}) 并发提取 {len(PHASE2_FIELDS_SPEC)} 项二期标准字段...")
        batch_tasks = [
            cls._extract_field_batch(client, context_text, batch, block_lookup, default_file)
            for batch in batches
        ]
        batch_results = await asyncio.gather(*batch_tasks)

        # 合并所有批次结果并存入内存
        all_main_params = []
        for res in batch_results:
            all_main_params.extend(res)

        memory.extracted_main_parameters = all_main_params

        # 同步将第 4, 7, 12, 13, 14, 15, 16 项组部件提取结果转化为右侧 Tab 2 的组部件卡片
        component_mapping = [
            ("4.避雷器", "Surge_Arrester (避雷器)"),
            ("7.绝缘油", "Transformer_Oil (变压器油)"),
            ("12.呼吸器", "Smart_Breather (智能呼吸器)"),
            ("13.油位计", "Oil_Level_Indicator (油位计)"),
            ("14.气体继电器", "Buchholz_Relay (瓦斯继电器)"),
            ("15.油面温度计和绕组温度计", "Temperature_Indicator (温度计)"),
            ("16.压力释放阀", "Pressure_Relief_Valve (压力释放阀)"),
        ]
        param_dict = {item["param_key"]: item for item in all_main_params}
        extracted_comps = []

        for idx, (field_key, comp_cat) in enumerate(component_mapping, start=1):
            p_item = param_dict.get(field_key)
            if p_item and p_item["param_value"] != "未提及":
                extracted_comps.append({
                    "req_id": f"req_comp_{idx}",
                    "Component_Category": comp_cat,
                    "Component_Name": field_key,
                    "Material_Requirement": "详见标书提取描述",
                    "Technical_Parameters": {"标书核心要求": p_item["param_value"][:120]},
                    "Specific_Requirements": [p_item["param_value"]],
                    "Quantity": "按标书配置",
                    "Source_Reference": p_item["source_ref"],
                    "matched_candidates": [],
                    "selected_comp_id": ""
                })

        memory.extracted_components = extracted_comps
        logger.info(f"DeepSeek 标书参数提取完成！共提取主参数 {len(all_main_params)} 项，组部件需求 {len(extracted_comps)} 项。")
        return memory