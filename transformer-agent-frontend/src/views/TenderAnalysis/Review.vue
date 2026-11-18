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
                    <el-input v-model="row.param_value" size="small" />
                    <el-tag v-if="row.has_conflict" type="danger" size="small" effect="dark">
                      跨文档冲突
                    </el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="original_text" label="原文依据片段" min-width="220" show-overflow-tooltip />
              <el-table-column label="页码" width="70" align="center">
                <template #default="{ row }">
                  <el-tag size="small">P.{{ row.source_ref.page_number }}</el-tag>
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
import { ref, reactive, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { Download } from '@element-plus/icons-vue';
import {ElLoading, ElMessage} from 'element-plus';
import PdfViewer from '../../components/pdf/PdfViewer.vue';
import { useTenderStore } from '../../store/tenderStore';
import { tenderApi } from '../../api/tender';
import type { TenderReviewData, MainParameterItem, ExtractedComponentItem } from '../../types/tender';

const route = useRoute();
const tenderStore = useTenderStore();
const activeTab = ref('mainParams');
const activeReqId = ref('');
const currentPdfFile = ref('680500BEST00025_CDFE00_60 Power transformer general specification.pdf');

// 修改后的 reviewData 初始状态（清空硬编码假数据，等待后端动态加载）
const reviewData = reactive<TenderReviewData>({
  project_id: (route.params.projectId as string) || '',
  project_name: '正在加载标书数据...',
  status: 'PARSING',
  documents: [],          // 初始化为空数组，由后端动态填充
  main_parameters: [],    // 初始化为空数组，由 Agent 提取结果填充
  components: [],         // 初始化为空数组，由 RAG 匹配结果填充
});

// 替换 Review.vue 中的 currentPdfUrl 计算属性：
const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const currentPdfUrl = computed(() => {
  if (!currentPdfFile.value) return '';
  const doc = reviewData.documents.find((d) => d.file_name === currentPdfFile.value);

  // 1. 优先使用后端返回的真实文件流地址
  if (doc?.file_url) {
    return doc.file_url.startsWith('http') ? doc.file_url : `${baseUrl}${doc.file_url}`;
  }

  // 2. 如果切换到了某行参数引用的文件名，直接按后端流式接口规则拼接 URL
  if (reviewData.project_id && !reviewData.project_id.startsWith('proj_guillena')) {
    return `${baseUrl}/api/v1/tender/${reviewData.project_id}/files/${encodeURIComponent(currentPdfFile.value)}`;
  }

  // 3. 仅在未上传任何文件的纯前端离线演示模式下，才回退到 public/sample.pdf
  return '/sample.pdf';
});

// 替换 Review.vue 中的 onMounted 钩子，自动选中第一个上传的真实 PDF：
onMounted(async () => {
  const loadingInstance = ElLoading.service({
    lock: true,
    text: '正在加载多智能体解析与组部件匹配结果...',
    background: 'rgba(0, 0, 0, 0.7)',
  });
  const pid = route.params.projectId as string;
  if (pid) {
    try {
      const serverData = await tenderApi.getReviewData(pid);
      Object.assign(reviewData, serverData);
      // 默认选中用户上传的第一个 PDF 文件进行渲染
      const firstPdf = reviewData.documents.find((d) => d.file_name.toLowerCase().endsWith('.pdf'));
      if (firstPdf) {
        currentPdfFile.value = firstPdf.file_name;
      } else if (reviewData.documents.length > 0) {
        currentPdfFile.value = reviewData.documents[0].file_name;
      }
    } catch (err) {
      console.warn('未获取到后端项目数据，使用本地演示数据:', err);
    }finally {
      loadingInstance.close();
    }
  }




});

function handleMainParamClick(row: MainParameterItem) {
  currentPdfFile.value = row.source_ref.file_name;
  tenderStore.triggerTraceHighlight(row.source_ref);
}

function handleComponentClick(comp: ExtractedComponentItem) {
  activeReqId.value = comp.req_id;
  currentPdfFile.value = comp.Source_Reference.file_name;
  tenderStore.triggerTraceHighlight(comp.Source_Reference);
}

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
      // 保持本地演示数据
    }
  }
});
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