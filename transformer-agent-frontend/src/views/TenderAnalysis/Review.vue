<template>
  <div class="review-workspace">
    <!-- 顶部项目导航栏 -->
    <header class="workspace-header">
      <div class="left-title">
        <el-tag effect="dark" type="primary">项目审阅台</el-tag>
        <h2>{{ reviewData.project_name }}</h2>
      </div>
      <div class="right-actions">
        <el-button type="success" :icon="Download" @click="handleExportExcel">
          确认审核并导出《投标初评表》Excel
        </el-button>
      </div>
    </header>

    <!-- 全宽主体区域（已移除左侧 PDF 面板） -->
    <main class="full-container">
      <section class="form-pane">
        <el-tabs v-model="activeTab" type="border-card" class="review-tabs">

          <!-- Tab 1: 商务与变压器主参数（对应二期提示词字段） -->
          <el-tab-pane label="1. 变压器主参数与商务要求" name="mainParams">
            <el-table :data="reviewData.main_parameters" border stripe>
              <el-table-column prop="param_key" label="二期标准字段" width="260" />
              <el-table-column label="Agent 提取值 (可直接修改)" min-width="220">
                <template #default="{ row }">
                  <div class="editable-cell">
                    <el-input v-model="row.param_value" size="small" />
                    <el-tag v-if="row.has_conflict" type="danger" size="small" effect="dark">
                      跨文档冲突
                    </el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="original_text" label="原文依据片段" min-width="280" show-overflow-tooltip />
              <el-table-column label="来源文件与页码" width="280">
                <template #default="{ row }">
                  <span>{{ row.source_ref?.file_name }} (P.{{ row.source_ref?.page_number }})</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- Tab 2: 组部件需求提取与内部规范库匹配 -->
          <el-tab-pane label="2. 组部件智能匹配推荐 (RAG)" name="components">
            <div
              v-for="comp in reviewData.components"
              :key="comp.req_id"
              class="component-card"
            >
              <div class="comp-card-header">
                <div>
                  <el-tag type="warning" effect="dark">{{ comp.Component_Category }}</el-tag>
                  <strong class="comp-title">{{ comp.Component_Name }}</strong>
                  <span class="comp-qty">需求数量: {{ comp.Quantity }}</span>
                </div>
                <el-tag size="small" type="info">
                  来源: {{ comp.Source_Reference.file_name }} (第 {{ comp.Source_Reference.page_number }} 页)
                </el-tag>
              </div>

              <!-- 标书提取出的组部件技术要求 -->
              <div class="comp-requirements">
                <p><strong>材质要求：</strong>{{ comp.Material_Requirement || '未明确指定' }}</p>
                <div class="tech-tags">
                  <el-tag
                    v-for="(val, key) in comp.Technical_Parameters"
                    :key="key"
                    size="small"
                    effect="plain"
                  >
                    {{ key }}: {{ val }}
                  </el-tag>
                </div>
                <ul class="spec-req-list">
                  <li v-for="(reqText, idx) in comp.Specific_Requirements" :key="idx">{{ reqText }}</li>
                </ul>
              </div>

              <!-- 双路召回（硬规则过滤 + 向量语义检索）的多供应商候选列表 -->
              <div class="matching-section">
                <div class="matching-title">
                  <span>内部标准规范库匹配推荐（共召回 {{ comp.matched_candidates.length }} 款合规组件，全量展示）：</span>
                </div>
                <el-radio-group v-model="comp.selected_comp_id" class="candidate-group">
                  <el-radio
                    v-for="cand in comp.matched_candidates"
                    :key="cand.comp_id"
                    :value="cand.comp_id"
                    border
                    class="candidate-radio"
                  >
                    <div class="cand-info">
                      <span class="cand-brand">[{{ cand.manufacturer }}] {{ cand.model_series }}</span>
                      <el-tag size="small" type="success">
                        语义匹配度 {{ (cand.similarity_score * 100).toFixed(0) }}%
                      </el-tag>
                    </div>
                  </el-radio>
                </el-radio-group>
              </div>
            </div>
          </el-tab-pane>

        </el-tabs>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { Download } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { tenderApi } from '../../api/tender';
import type { TenderReviewData } from '../../types/tender';

const route = useRoute();
const activeTab = ref('mainParams');

// 预置演示数据（已去除 bbox 坐标依赖）
const reviewData = reactive<TenderReviewData>({
  project_id: (route.params.projectId as string) || 'proj_guillena_001',
  project_name: 'SPAIN - GUILLENA PV PLANT (30/220 kV Step-Up Transformer)',
  status: 'MATCHED',
  documents: [],
  main_parameters: [
    {
      param_key: '1.1 变压器的相数',
      param_value: '3',
      original_text: 'Number of phases: 3',
      source_ref: {
        file_name: '680502BEGA00026_CDFE00_06 General TDS.pdf',
        page_number: 4,
        bbox: null,
      },
    },
    {
      param_key: '1.2 变压器的频率',
      param_value: '50 Hz',
      original_text: 'Rated frequency: 50 Hz',
      source_ref: {
        file_name: '680502BEGA00026_CDFE00_06 General TDS.pdf',
        page_number: 4,
        bbox: null,
      },
    },
    {
      param_key: '最高温度(℃)',
      param_value: '50 °C (TDS参数表为48 °C)',
      original_text: 'Temperature: 0°C to 50°C',
      has_conflict: true,
      source_ref: {
        file_name: '680500BEST00025_CDFE00_60 Power transformer general specification.pdf',
        page_number: 13,
        bbox: null,
      },
    },
    {
      param_key: '联结组别',
      param_value: 'YNd11',
      original_text: 'Connection and phase displacement symbol (vector group): YNd11',
      source_ref: {
        file_name: '680502BEGA00026_CDFE00_06 General TDS.pdf',
        page_number: 4,
        bbox: null,
      },
    },
    {
      param_key: '冷却方式',
      param_value: 'ONAN/ONAF',
      original_text: 'Type of cooling: ONAN/ONAF',
      source_ref: {
        file_name: '680502BEGA00026_CDFE00_06 General TDS.pdf',
        page_number: 5,
        bbox: null,
      },
    },
  ],
  components: [
    {
      req_id: 'req_arrester_01',
      Component_Category: 'Surge_Arrester (避雷器)',
      Component_Name: 'HV Station Class Surge Arrester',
      Material_Requirement: 'Silicone rubber / Porcelain housing, pollution level IV (Very Heavy)',
      Technical_Parameters: {
        highest_voltage: '245 kV (System 220kV)',
        arrester_class: 'Station class',
        impulse_withstand: '1050 kV',
      },
      Specific_Requirements: [
        'Surge arrester requirement: Yes, Station class',
        'Pollution level shall be IV - Very Heavy (requires high creepage distance)',
      ],
      Quantity: '3 sets',
      Source_Reference: {
        file_name: '680502BEGA00026_CDFE00_06 General TDS.pdf',
        page_number: 6,
        bbox: null,
      },
      matched_candidates: [
        {
          comp_id: 'siemens_3el2_192',
          manufacturer: 'Siemens',
          model_series: '3EL2 192-2PJ31 (Silicone Cage Design, Ur=192kV, LD Class 3)',
          similarity_score: 0.95,
          specs_summary: { Us: '245kV', In: '10kA', housing: 'Silicone rubber' },
        },
        {
          comp_id: 'siemens_3ep6_192',
          manufacturer: 'Siemens',
          model_series: '3EP6 192-2PF31 (Porcelain Housing, Ur=192kV, LD Class 3)',
          similarity_score: 0.91,
          specs_summary: { Us: '245kV', In: '10kA', housing: 'Porcelain' },
        },
      ],
      selected_comp_id: 'siemens_3el2_192',
    },
    {
      req_id: 'req_buchholz_02',
      Component_Category: 'Buchholz_Relay (瓦斯继电器)',
      Component_Name: 'Buchholz gas relay',
      Material_Requirement: 'Corrosion resistant, anti-seismic',
      Technical_Parameters: {
        alarm_contacts: '1 alarm contact',
        trip_contacts: '2 trip contacts',
        pipe_diameter: 'DN80',
      },
      Specific_Requirements: [
        'Provided with two electrically independent alarm and trip contacts',
        'Fitted between two on-off butterfly valves and with a bypass valve',
      ],
      Quantity: '2 sets (Tank + OLTC)',
      Source_Reference: {
        file_name: '680500BEST00025_CDFE00_60 Power transformer general specification.pdf',
        page_number: 28,
        bbox: null,
      },
      matched_candidates: [
        {
          comp_id: 'emb_double_dn80',
          manufacturer: 'EMB GmbH',
          model_series: 'Double-float Buchholz Relay DN80 (Code 17A / Harting Connector)',
          similarity_score: 0.96,
          specs_summary: { DN: '80mm', float: 'Double-float', voltage: 'AC/DC 5-250V' },
        },
      ],
      selected_comp_id: 'emb_double_dn80',
    },
  ],
});

async function handleExportExcel() {
  try {
    await tenderApi.confirmAndExportExcel(reviewData.project_id, reviewData);
    ElMessage.success('已成功将数据写入《新版初评表》模板并触发下载！');
  } catch {
    ElMessage.info('演示模式：已打包修改后的主参数与选定供应商组部件，调用后端 openpyxl 填表接口。');
  }
}

onMounted(async () => {
  if (route.params.projectId) {
    try {
      const serverData = await tenderApi.getReviewData(route.params.projectId as string);
      Object.assign(reviewData, serverData);
    } catch {
      // 后端未连接时使用本地演示数据
    }
  }
});
</script>

<style scoped lang="scss">
.review-workspace {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f7fa;
}

.workspace-header {
  height: 58px;
  background: #fff;
  border-bottom: 1px solid #dcdfe6;
  padding: 0 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;

  .left-title {
    display: flex;
    align-items: center;
    gap: 12px;
    h2 { margin: 0; font-size: 16px; color: #303133; }
  }
}

.full-container {
  flex: 1;
  overflow: hidden;
  padding: 16px 24px;
  max-width: 1440px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;

  .form-pane {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;

    .review-tabs {
      height: 100%;
      display: flex;
      flex-direction: column;
      :deep(.el-tabs__content) {
        flex: 1;
        overflow-y: auto;
      }
    }
  }
}

.editable-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.component-card {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 14px;
  background: #fff;

  .comp-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    .comp-title { margin-left: 10px; font-size: 15px; }
    .comp-qty { margin-left: 12px; font-size: 13px; color: #606266; }
  }

  .comp-requirements {
    font-size: 13px;
    color: #606266;
    background: #fafafa;
    padding: 10px;
    border-radius: 4px;
    .tech-tags { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
    .spec-req-list { margin: 4px 0 0 18px; padding: 0; }
  }

  .matching-section {
    margin-top: 12px;
    .matching-title { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: #303133; }
    .candidate-group {
      display: flex;
      flex-direction: column;
      gap: 8px;
      align-items: stretch;
    }
    .candidate-radio {
      margin-right: 0;
      width: 100%;
      height: auto;
      padding: 8px 12px;
      .cand-info {
        display: inline-flex;
        justify-content: space-between;
        align-items: center;
        width: 100%;
        gap: 12px;
      }
    }
  }
}
</style>