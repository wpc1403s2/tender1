<template>
  <div class="review-workspace">
    <header class="workspace-header">
      <div class="left-title">
        <el-tag effect="dark" type="primary">项目审阅台</el-tag>
        <h2>{{ reviewData.project_name }}</h2>
        <el-select v-model="currentPdfFile" size="small" style="width: 320px; margin-left: 16px">
          <el-option
            v-for="doc in reviewData.documents"
            :key="doc.doc_id"
            :label="doc.file_name"
            :value="doc.file_name"
          />
        </el-select>
      </div>
      <div class="right-actions">
        <el-button type="primary" :loading="isExtracting || isLoading" @click="startExtraction(true)">
          {{ isExtracting ? '正在提取参数…' : '重新提取参数' }}
        </el-button>
        <el-button type="success" :icon="Download" @click="handleExportExcel">
          确认审核并导出《投标初评表》Excel
        </el-button>
      </div>
    </header>

    <main class="split-container">
      <!-- 左侧：PDF.js 原文渲染与 BBox 溯源高亮 -->
      <section class="left-pdf-pane">
        <PdfViewer :pdf-url="currentPdfUrl" :file-name="currentPdfFile" />
      </section>

      <!-- 右侧：结构化提取表单与 RAG 组部件匹配面板 -->
      <section class="right-form-pane">
        <el-tabs v-model="activeTab" type="border-card" class="review-tabs">
          <el-tab-pane label="1. 变压器主参数与商务要求" name="mainParams">
            <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />
            <el-alert v-if="isExtracting" :title="`正在读取标书并提取参数，已完成 ${reviewData.completed_chunks || 0} / ${reviewData.total_chunks || 0} 批。可在左侧查看原文。`" type="info" :closable="false" />
            <el-alert
              title="点击任意参数行，左侧 PDF 将自动翻页并高亮原文提取位置（BBox 溯源）"
              type="info"
              show-icon
              :closable="false"
              style="margin-bottom: 12px"
            />
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
                    <el-input v-model="row.param_value" type="textarea" :autosize="{ minRows: 1, maxRows: 8 }" size="small" />
                    <el-tag v-if="row.evidence_warning" type="warning" :title="row.evidence_warning" size="small">待核验</el-tag>
                    <el-tag v-if="row.has_conflict" type="danger" size="small" effect="dark">
                      跨文档冲突
                    </el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="original_text" label="原文依据片段" min-width="220" show-overflow-tooltip />
              <el-table-column label="页码" width="70" align="center">
                <template #default="{ row }">
                  <template v-if="row.source_ref">
                    <el-button v-for="(source, index) in (row.source_refs || [row.source_ref])" :key="index"
                      link type="primary" :title="source.file_name + '\n' + source.original_text"
                      @click.stop="traceSource(source)">P.{{ source.page_number }}</el-button>
                  </template>
                  <span v-else>—</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="2. 组部件智能匹配推荐 (RAG)" name="components">
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
                  <span class="comp-qty">需求数量: {{ comp.Quantity }}</span>
                </div>
                <el-tag size="small" type="info">
                  溯源: {{ comp.Source_Reference.file_name }} (第 {{ comp.Source_Reference.page_number }} 页)
                </el-tag>
              </div>

              <div class="comp-requirements">
                <p><strong>材质要求：</strong>{{ comp.Material_Requirement || '未明确指定' }}</p>
                <div class="tech-tags">
                  <el-tag v-for="(val, key) in comp.Technical_Parameters" :key="key" size="small" effect="plain">
                    {{ key }}: {{ val }}
                  </el-tag>
                </div>
                <ul class="spec-req-list">
                  <li v-for="(reqText, idx) in comp.Specific_Requirements" :key="idx">{{ reqText }}</li>
                </ul>
              </div>

              <div class="matching-section">
                <div class="matching-title">
                  <span>内部标准规范库匹配推荐（共召回 {{ comp.matched_candidates.length }} 款合规组件）：</span>
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
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { Download } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PdfViewer from '../../components/pdf/PdfViewer.vue';
import { useTenderStore } from '../../store/tenderStore';
import { tenderApi } from '../../api/tender';
import type { TenderReviewData, MainParameterItem, ExtractedComponentItem, SourceReference } from '../../types/tender';

const route = useRoute();
const tenderStore = useTenderStore();
const activeTab = ref('mainParams');
const activeReqId = ref('');
const currentPdfFile = ref('');
const errorMessage = ref('');
const isLoading = ref(false);
const reviewData = reactive<TenderReviewData>({
  project_id: (route.params.projectId as string) || '',
  project_name: '正在加载标书数据...', status: 'PARSING',
  documents: [], main_parameters: [], components: [],
});
const isExtracting = computed(() => reviewData.status === 'EXTRACTING');
const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const currentPdfUrl = computed(() => {
  const doc = reviewData.documents.find(d => d.file_name === currentPdfFile.value);
  if (!doc?.file_name.toLowerCase().endsWith('.pdf')) return '';
  return doc.file_url?.startsWith('http') ? doc.file_url : `${baseUrl}${doc.file_url}`;
});
let pollTimer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
function errorText(err: any) {
  return err?.response?.data?.detail || err?.message || '请求失败，请重试';
}
function applyData(data: TenderReviewData) {
  Object.assign(reviewData, data);
  errorMessage.value = data.extraction_error || '';
  if (!currentPdfFile.value) {
    currentPdfFile.value = data.documents.find(d => d.file_name.toLowerCase().endsWith('.pdf'))?.file_name || '';
  }
}
function schedulePoll() {
  clearTimeout(pollTimer);
  if (disposed || !isExtracting.value) return;
  pollTimer = setTimeout(async () => {
    try {
      const data = await tenderApi.getReviewData(reviewData.project_id);
      if (disposed) return;
      applyData(data);
    } catch (err) {
      if (!disposed) errorMessage.value = `${errorText(err)}；正在重试获取进度`;
    }
    schedulePoll();
  }, 2500);
}
async function startExtraction(force = false) {
  if (!reviewData.project_id || isExtracting.value || isLoading.value) return;
  if (force && reviewData.main_parameters.length) {
    try {
      await ElMessageBox.confirm('重新提取将替换当前表格及尚未保存的修改，是否继续？', '重新提取参数');
    } catch { return; }
  }
  isLoading.value = true;
  errorMessage.value = '';
  try {
    const data = await tenderApi.startAgentExtraction(reviewData.project_id, force);
    if (disposed) return;
    tenderStore.clearHighlight();
    applyData(data);
    schedulePoll();
  } catch (err) {
    if (!disposed) errorMessage.value = errorText(err);
  } finally { isLoading.value = false; }
}
onMounted(async () => {
  if (!reviewData.project_id) {
    errorMessage.value = '请先上传标书后进入审阅台';
    return;
  }
  isLoading.value = true;
  try {
    const data = await tenderApi.getReviewData(reviewData.project_id);
    if (disposed) return;
    applyData(data);
  } catch (err) {
    errorMessage.value = errorText(err);
  } finally { isLoading.value = false; }
  if (disposed) return;
  if (reviewData.status === 'READY') await startExtraction();
  else schedulePoll();
});
onBeforeUnmount(() => { disposed = true; clearTimeout(pollTimer); });
function traceSource(source: SourceReference) {
  if (!source.file_name.toLowerCase().endsWith('.pdf')) {
    ElMessage.info(`原文位于 ${source.file_name}，当前预览仅支持 PDF`);
    return;
  }
  currentPdfFile.value = source.file_name;
  tenderStore.triggerTraceHighlight(source);
}
function handleMainParamClick(row: MainParameterItem) {
  if (row.source_ref) traceSource(row.source_ref);
  else tenderStore.clearHighlight();
}
function handleComponentClick(comp: ExtractedComponentItem) {
  activeReqId.value = comp.req_id;
  traceSource(comp.Source_Reference);
}
async function handleExportExcel() {
  try {
    await tenderApi.confirmAndExportExcel(reviewData.project_id, reviewData);
    ElMessage.success('Excel 已生成');
  } catch (err) { ElMessage.error(`导出失败：${errorText(err)}`); }
}
</script>

<style scoped lang="scss">
.review-workspace { display: flex; flex-direction: column; height: 100vh; background: #f5f7fa; }
.workspace-header {
  height: 58px; background: #fff; border-bottom: 1px solid #dcdfe6; padding: 0 20px;
  display: flex; justify-content: space-between; align-items: center;
  .left-title { display: flex; align-items: center; gap: 12px; h2 { margin: 0; font-size: 16px; color: #303133; } }
}
.split-container {
  flex: 1; display: flex; overflow: hidden; padding: 12px; gap: 12px;
  .left-pdf-pane { width: 48%; height: 100%; }
  .right-form-pane {
    width: 52%; height: 100%; display: flex; flex-direction: column;
    .review-tabs {
      height: 100%; display: flex; flex-direction: column;
      :deep(.el-tabs__content) { flex: 1; overflow-y: auto; }
    }
  }
}
.editable-cell { display: flex; align-items: center; gap: 8px; }
.component-card {
  border: 1px solid #e4e7ed; border-radius: 6px; padding: 14px; margin-bottom: 14px;
  background: #fff; cursor: pointer; transition: all 0.2s;
  &:hover, &.is-active { border-color: #409eff; box-shadow: 0 2px 12px rgba(64, 158, 255, 0.15); }
  .comp-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; .comp-title { margin-left: 10px; font-size: 15px; } .comp-qty { margin-left: 12px; font-size: 13px; color: #606266; } }
  .comp-requirements { font-size: 13px; color: #606266; background: #fafafa; padding: 10px; border-radius: 4px; .tech-tags { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; } .spec-req-list { margin: 4px 0 0 18px; padding: 0; } }
  .matching-section {
    margin-top: 12px; .matching-title { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: #303133; }
    .candidate-group { display: flex; flex-direction: column; gap: 8px; align-items: stretch; }
    .candidate-radio { margin-right: 0; width: 100%; height: auto; padding: 8px 12px; .cand-info { display: inline-flex; justify-content: space-between; align-items: center; width: 100%; gap: 12px; } }
  }
}
</style>
