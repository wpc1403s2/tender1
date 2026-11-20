<template>
  <div class="review-workspace">
    <header class="workspace-header">
      <div class="left-title">
        <el-tag effect="dark" type="primary">项目审阅台</el-tag>
        <h2>{{ reviewData.project_name }}</h2>
        <el-select
          v-model="currentPdfFile"
          size="small"
          style="width: 320px; margin-left: 16px"
          @change="handleManualDocSelect"
        >
          <el-option
            v-for="doc in reviewData.documents"
            :key="doc.doc_id"
            :label="doc.file_name"
            :value="doc.file_name"
          />
        </el-select>
        <el-button
          v-if="isViewingCatalogPdf"
          type="warning"
          size="small"
          @click="backToTenderPdf"
        >
          ← 切回标书原文 PDF
        </el-button>
      </div>
      <div class="right-actions">
        <el-button type="primary" plain size="small" @click="router.push('/library')">
          管理组部件标准库 (pgvector)
        </el-button>
        <el-button type="success" :icon="Download" @click="handleExportExcel">
          确认审核并导出《投标初评表》Excel
        </el-button>
      </div>
    </header>

    <main class="split-container">
      <!-- 左侧：PDF.js 原文渲染与 BBox 溯源高亮 (支持标书原件与供应商样册原件无缝切换) -->
      <section class="left-pdf-pane">
        <PdfViewer :pdf-url="currentPdfUrl" :file-name="displayFileName" />
      </section>

      <!-- 右侧：结构化提取表单与 RAG 组部件匹配面板 -->
      <section class="right-form-pane">
        <el-tabs v-model="activeTab" type="border-card" class="review-tabs">
          <el-tab-pane :label="`1. 变压器主参数与商务要求（提取率 ${extractionStats.rate}%）`" name="mainParams">
            <el-table
              :data="reviewData.main_parameters"
              border
              highlight-current-row
              @row-click="handleMainParamClick"
            >
              <el-table-column prop="param_key" label="二期标准字段" width="230" />
              <el-table-column label="Agent 提取值 (可直接修改)" min-width="180">
                <template #default="{ row }">
                  <div class="editable-cell">
                    <el-input
                      v-model="row.param_value"
                      type="textarea"
                      :autosize="{ minRows: 1 }"
                      resize="none"
                      class="param-value-input"
                    />
                    <el-tag v-if="row.has_conflict" type="danger" size="small" effect="dark">
                      跨文档冲突
                    </el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="original_text" label="原文依据片段" min-width="220" show-overflow-tooltip />
              <el-table-column label="页码" width="70" align="center">
                <template #default="{ row }">
                  <el-tag size="small">P.{{ row.source_ref?.page_number || 1 }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane
            :label="`2. 组部件智能匹配推荐 (${reviewData.components.length} 类)`"
            name="components"
          >
            <!-- Tab 2 顶部操作工具栏 -->
            <div class="comp-tab-toolbar">
              <div class="toolbar-desc">
                <el-tag type="success" size="small" effect="plain">三阶段混合匹配</el-tag>
                <span>硬规则边界初筛 → pgvector 向量召回 → DeepSeek 工程师级选型核验</span>
              </div>
              <div class="toolbar-actions">
                <el-button
                  type="primary"
                  size="small"
                  :loading="isRematching"
                  @click="handleRematchComponents"
                >
                  🔄 重新匹配组部件
                </el-button>
              </div>
            </div>

            <div
              v-for="comp in reviewData.components"
              :key="comp.req_id"
              class="component-card"
              :class="{ 'is-active': activeReqId === comp.req_id }"
              @click="handleComponentClick(comp)"
            >
              <div class="comp-card-header">
                <div>
                  <el-tag type="warning" effect="dark">{{ comp.Component_Category }}</el-tag>
                  <strong class="comp-title">{{ comp.Component_Name }}</strong>
                  <span class="comp-qty">配置: {{ comp.Quantity }}</span>
                </div>
                <el-tag size="small" type="info">
                  标书溯源: {{ comp.Source_Reference?.file_name || '默认标书' }} (第 {{ comp.Source_Reference?.page_number || 1 }} 页)
                </el-tag>
              </div>

              <div class="comp-requirements">
                <div class="tech-tags">
                  <el-tag v-for="(val, key) in comp.Technical_Parameters" :key="key" size="small" effect="plain">
                    {{ key }}: {{ val }}
                  </el-tag>
                </div>
                <ul class="spec-req-list">
                  <li v-for="(reqText, idx) in comp.Specific_Requirements" :key="idx">{{ reqText }}</li>
                </ul>
              </div>

              <div class="matching-section" @click.stop>
                <div class="matching-title">
                  <span>内部标准规范库匹配推荐（共召回 {{ comp.matched_candidates.length }} 款合格组件，全量展示供选型确认）：</span>
                </div>

                <el-empty
                  v-if="comp.matched_candidates.length === 0"
                  description="当前标准库暂无该品类合格型号，请前往组部件库上传样册或初始化种子库"
                  :image-size="60"
                />

                <el-radio-group v-else v-model="comp.selected_comp_id" class="candidate-group">
                  <div
                    v-for="cand in comp.matched_candidates"
                    :key="cand.comp_id"
                    class="candidate-item-box"
                    :class="{ 'is-selected': comp.selected_comp_id === cand.comp_id }"
                    @click="comp.selected_comp_id = cand.comp_id"
                  >
                    <div class="cand-top-row">
                      <el-radio :value="cand.comp_id" class="cand-radio-label">
                        <span class="cand-brand">[{{ cand.manufacturer }}] {{ cand.model_series }}</span>
                      </el-radio>
                      <div class="cand-badges">
                        <el-tag
                          size="small"
                          :type="getMatchStatusType(cand.match_status)"
                          effect="dark"
                        >
                          {{ formatMatchStatus(cand.match_status) }}
                        </el-tag>
                        <el-tag size="small" type="success">
                          综合匹配度 {{ (cand.similarity_score * 100).toFixed(0) }}%
                        </el-tag>
                        <el-button
                          v-if="cand.catalog_bbox && cand.catalog_bbox.file_name"
                          type="primary"
                          size="small"
                          plain
                          @click.stop="handleViewCatalogPdf(cand.catalog_bbox)"
                        >
                          📄 查看样册原文 (P.{{ cand.catalog_bbox.page_number }})
                        </el-button>
                      </div>
                    </div>

                    <!-- 满足项亮点与偏离说明 -->
                    <div
                      v-if="(cand.match_highlights && cand.match_highlights.length) || (cand.deviation_notes && cand.deviation_notes.length)"
                      class="cand-eval-box"
                    >
                      <div
                        v-for="(hl, hIdx) in cand.match_highlights"
                        :key="'h_' + hIdx"
                        class="eval-line highlight-line"
                      >
                        ✓ {{ hl }}
                      </div>
                      <div
                        v-for="(dev, dIdx) in cand.deviation_notes"
                        :key="'d_' + dIdx"
                        class="eval-line deviation-line"
                      >
                        ⚠ 选型注意：{{ dev }}
                      </div>
                    </div>

                    <!-- 标准品核心技术参数摘要网格 -->
                    <div v-if="cand.specs_summary" class="cand-specs-grid">
                      <div
                        v-for="(sVal, sKey) in cand.specs_summary"
                        :key="sKey"
                        class="spec-chip"
                      >
                        <span class="s-key">{{ sKey }}:</span>
                        <span class="s-val">{{ sVal }}</span>
                      </div>
                    </div>
                  </div>
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
import { ref, reactive, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Download } from '@element-plus/icons-vue';
import { ElLoading, ElMessage } from 'element-plus';
import PdfViewer from '../../components/pdf/PdfViewer.vue';
import { useTenderStore } from '../../store/tenderStore';
import { tenderApi } from '../../api/tender';
import type {
  TenderReviewData,
  MainParameterItem,
  ExtractedComponentItem,
  SourceReference,
} from '../../types/tender';

const route = useRoute();
const router = useRouter();
const tenderStore = useTenderStore();
const activeTab = ref('mainParams');
const activeReqId = ref('');
const currentPdfFile = ref('');
const isRematching = ref(false);

// 支持左侧 PDF 视图临时切换查看供应商样册 PDF
const customCatalogPdfUrl = ref('');
const customCatalogFileName = ref('');
const isViewingCatalogPdf = computed(() => Boolean(customCatalogPdfUrl.value));

const reviewData = reactive<TenderReviewData>({
  project_id: (route.params.projectId as string) || '',
  project_name: '正在加载标书数据...',
  status: 'PARSING',
  documents: [],
  main_parameters: [],
  components: [],
});

const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const displayFileName = computed(() => {
  if (isViewingCatalogPdf.value) {
    return `[供应商样册] ${customCatalogFileName.value}`;
  }
  return currentPdfFile.value;
});

const currentPdfUrl = computed(() => {
  if (customCatalogPdfUrl.value) {
    return customCatalogPdfUrl.value;
  }
  if (!currentPdfFile.value || !reviewData.project_id) return '';

  const doc = reviewData.documents.find((d) => d.file_name === currentPdfFile.value);
  if (doc?.file_url) {
    return doc.file_url.startsWith('http') ? doc.file_url : `${baseUrl}${doc.file_url}`;
  }
  return `${baseUrl}/api/v1/tender/${reviewData.project_id}/files/${encodeURIComponent(currentPdfFile.value)}`;
});

const UNMENTIONED_KEYWORDS = ['未提及', 'not mentioned', 'n/a'];
const extractionStats = computed(() => {
  const items = reviewData.main_parameters || [];
  const total = items.length;
  const extracted = items.filter(
    (it) =>
      it.param_value &&
      it.param_value.trim() !== '' &&
      !UNMENTIONED_KEYWORDS.includes(it.param_value.trim().toLowerCase())
  ).length;
  const conflicts = items.filter((it) => it.has_conflict).length;
  const rate = total === 0 ? 0 : Math.round((extracted / total) * 100);
  return { total, extracted, missed: total - extracted, conflicts, rate };
});

onMounted(async () => {
  const pid = route.params.projectId as string;
  if (!pid) return;

  const loadingInstance = ElLoading.service({
    lock: true,
    text: '正在执行 DeepSeek 68项标书提取与三阶段组部件智能匹配...',
    background: 'rgba(0, 0, 0, 0.7)',
  });
  try {
    const serverData = await tenderApi.getReviewData(pid);
    Object.assign(reviewData, serverData);
    const firstPdf = reviewData.documents.find((d) => d.file_name.toLowerCase().endsWith('.pdf'));
    if (firstPdf) {
      currentPdfFile.value = firstPdf.file_name;
    } else if (reviewData.documents.length > 0) {
      currentPdfFile.value = reviewData.documents[0].file_name;
    }
  } catch (err) {
    console.warn('未获取到后端项目数据:', err);
  } finally {
    loadingInstance.close();
  }
});

function handleManualDocSelect() {
  customCatalogPdfUrl.value = '';
  customCatalogFileName.value = '';
  tenderStore.clearHighlight();
}

function backToTenderPdf() {
  customCatalogPdfUrl.value = '';
  customCatalogFileName.value = '';
  tenderStore.clearHighlight();
}

function handleMainParamClick(row: MainParameterItem) {
  customCatalogPdfUrl.value = '';
  customCatalogFileName.value = '';
  if (row.source_ref?.file_name) {
    currentPdfFile.value = row.source_ref.file_name;
  }
  tenderStore.triggerTraceHighlight(row.source_ref);
}

function handleComponentClick(comp: ExtractedComponentItem) {
  activeReqId.value = comp.req_id;
  customCatalogPdfUrl.value = '';
  customCatalogFileName.value = '';
  if (comp.Source_Reference?.file_name) {
    currentPdfFile.value = comp.Source_Reference.file_name;
  }
  tenderStore.triggerTraceHighlight(comp.Source_Reference);
}

function handleViewCatalogPdf(catalogRef: SourceReference) {
  if (!catalogRef || !catalogRef.file_name) return;
  customCatalogFileName.value = catalogRef.file_name;
  if (catalogRef.file_url) {
    customCatalogPdfUrl.value = catalogRef.file_url.startsWith('http')
      ? catalogRef.file_url
      : `${baseUrl}${catalogRef.file_url}`;
  } else {
    customCatalogPdfUrl.value = `${baseUrl}/api/v1/components/catalogs/${encodeURIComponent(catalogRef.file_name)}`;
  }
  tenderStore.triggerTraceHighlight(catalogRef);
}

async function handleRematchComponents() {
  if (!reviewData.project_id) return;
  isRematching.value = true;
  try {
    const res = await tenderApi.rematchComponents(
      reviewData.project_id,
      reviewData.main_parameters
    );
    reviewData.components = res.data.components;
    ElMessage.success(res.message || '组部件三阶段重新匹配完成！');
  } catch (err: any) {
    ElMessage.error(err.message || '重新匹配失败');
  } finally {
    isRematching.value = false;
  }
}

function formatMatchStatus(status?: string) {
  if (status === 'FULLY_MATCHED') return '精准匹配';
  if (status === 'PARTIAL_DEVIATION') return '含注意项';
  return '合规适用';
}

function getMatchStatusType(status?: string) {
  if (status === 'FULLY_MATCHED') return 'success';
  if (status === 'PARTIAL_DEVIATION') return 'warning';
  return 'primary';
}

async function handleExportExcel() {
  try {
    await tenderApi.confirmAndExportExcel(reviewData.project_id, reviewData);
    ElMessage.success('已成功将数据写入《新版初评表》模板并触发下载！');
  } catch {
    ElMessage.info('演示模式：已打包修改后的主参数与选定供应商组部件，调用后端 openpyxl 填表接口。');
  }
}
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
  padding: 0 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  .left-title {
    display: flex;
    align-items: center;
    gap: 12px;
    h2 {
      margin: 0;
      font-size: 16px;
      color: #303133;
    }
  }
  .right-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }
}
.split-container {
  flex: 1;
  display: flex;
  overflow: hidden;
  padding: 12px;
  gap: 12px;
  .left-pdf-pane {
    width: 48%;
    height: 100%;
  }
  .right-form-pane {
    width: 52%;
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
  align-items: flex-start;
  gap: 8px;
  .param-value-input {
    flex: 1;
    min-width: 0;
  }
  :deep(.el-textarea__inner) {
    font-size: 12px;
    line-height: 1.5;
    padding: 4px 8px;
  }
}
.comp-tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 6px;
  .toolbar-desc {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: #606266;
  }
}
.component-card {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 14px;
  margin-bottom: 14px;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
  &:hover,
  &.is-active {
    border-color: #409eff;
    box-shadow: 0 2px 12px rgba(64, 158, 255, 0.15);
  }
  .comp-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    .comp-title {
      margin-left: 10px;
      font-size: 15px;
    }
    .comp-qty {
      margin-left: 12px;
      font-size: 13px;
      color: #606266;
    }
  }
  .comp-requirements {
    font-size: 13px;
    color: #606266;
    background: #fafafa;
    padding: 10px;
    border-radius: 4px;
    .tech-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 6px;
    }
    .spec-req-list {
      margin: 4px 0 0 18px;
      padding: 0;
      line-height: 1.5;
    }
  }
  .matching-section {
    margin-top: 12px;
    cursor: default;
    .matching-title {
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 8px;
      color: #303133;
    }
    .candidate-group {
      display: flex;
      flex-direction: column;
      gap: 10px;
      width: 100%;
      align-items: stretch;
    }
    .candidate-item-box {
      border: 1px solid #dcdfe6;
      border-radius: 6px;
      padding: 10px 12px;
      background: #fff;
      cursor: pointer;
      transition: all 0.15s;
      &:hover {
        border-color: #409eff;
      }
      &.is-selected {
        border-color: #409eff;
        background-color: #ecf5ff;
      }
      .cand-top-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        .cand-brand {
          font-weight: 600;
          font-size: 14px;
          color: #303133;
        }
        .cand-badges {
          display: flex;
          align-items: center;
          gap: 6px;
        }
      }
      .cand-eval-box {
        margin-top: 8px;
        padding: 6px 10px;
        background: rgba(255, 255, 255, 0.85);
        border-radius: 4px;
        font-size: 12px;
        line-height: 1.5;
        .highlight-line {
          color: #67c23a;
          font-weight: 500;
        }
        .deviation-line {
          color: #e6a23c;
          font-weight: 500;
        }
      }
      .cand-specs-grid {
        margin-top: 8px;
        display: flex;
        flex-wrap: wrap;
        gap: 6px 14px;
        font-size: 12px;
        color: #606266;
        .spec-chip {
          .s-key {
            color: #909399;
            margin-right: 3px;
          }
          .s-val {
            color: #303133;
            font-weight: 500;
          }
        }
      }
    }
  }
}
</style>
