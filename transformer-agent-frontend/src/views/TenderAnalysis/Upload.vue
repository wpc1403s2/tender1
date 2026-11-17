<template>
  <div class="upload-page">
    <el-card class="upload-card">
      <template #header>
        <div class="card-header">
          <h2>步骤一：变压器标书多源文档上传与预处理</h2>
          <el-tag type="primary">支持 PDF(原生/盖章扫描件) · Word · Excel · ZIP整包</el-tag>
        </div>
      </template>

      <el-upload
        drag
        multiple
        :auto-upload="false"
        :on-change="handleFileChange"
        :file-list="fileList"
        accept=".pdf,.doc,.docx,.xls,.xlsx,.zip"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          将标书文件（商务标、技术规范 PDF、参数清单 Excel 或 ZIP 包）拖到此处，或 <em>点击选择</em>
        </div>
      </el-upload>

      <div class="action-bar">
        <el-button
          type="primary"
          size="large"
          :loading="isUploading"
          :disabled="rawFiles.length === 0"
          @click="submitPreprocess"
        >
          {{ isUploading ? '正在执行版面分析与表格还原...' : '开始预处理并载入内存' }}
        </el-button>
      </div>

      <!-- 预处理结果摘要表 -->
      <div v-if="docSummaries.length > 0" class="summary-section">
        <h3>文档自动分类与空间锚定结果 (Project ID: {{ currentProjectId }})</h3>
        <el-table :data="docSummaries" border stripe style="width: 100%">
          <el-table-column prop="file_name" label="文件名" min-width="240" />
          <el-table-column prop="category" label="系统自动识别类型" width="180">
            <template #default="{ row }">
              <el-tag :type="getCategoryTagType(row.category)">
                {{ formatCategoryName(row.category) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="total_pages" label="总页数 / Sheet数" width="150" align="center" />
          <el-table-column prop="blocks_count" label="文本/表格锚定块数" width="160" align="center" />
        </el-table>

        <div class="next-step-bar">
          <el-button type="success" size="large" @click="goToReviewWorkspace">
            进入多智能体参数提取与组部件匹配工作台 →
          </el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { UploadFilled } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { tenderApi } from '../../api/tender';
import type { DocumentSummary, DocCategory } from '../../types/tender';

const router = useRouter();
const fileList = ref<any[]>([]);
const rawFiles = ref<File[]>([]);
const isUploading = ref(false);
const currentProjectId = ref('');
const docSummaries = ref<DocumentSummary[]>([]);

function handleFileChange(uploadFile: any, uploadFiles: any[]) {
  fileList.value = uploadFiles;
  rawFiles.value = uploadFiles.map((f) => f.raw);
}

async function submitPreprocess() {
  isUploading.value = true;
  try {
    const res = await tenderApi.uploadTenderFiles(rawFiles.value);
    currentProjectId.value = res.project_id;
    docSummaries.value = res.documents_summary;
    ElMessage.success('标书多源文档预处理完成，BBox坐标已锚定入库！');
  } catch (err: any) {
    ElMessage.error(err.message || '预处理失败');
  } finally {
    isUploading.value = false;
  }
}

function formatCategoryName(cat: DocCategory) {
  const map: Record<DocCategory, string> = {
    commercial_bid: '商务标书',
    technical_spec: '技术规范 (PDF/Word)',
    boq_list: '参数表/招标清单 (Excel)',
    component_catalog: '组部件标准规范',
    unknown: '待分类文档',
  };
  return map[cat] || cat;
}

function getCategoryTagType(cat: DocCategory) {
  if (cat === 'technical_spec') return 'primary';
  if (cat === 'boq_list') return 'success';
  if (cat === 'commercial_bid') return 'warning';
  return 'info';
}

function goToReviewWorkspace() {
  router.push({ name: 'TenderReview', params: { projectId: currentProjectId.value } });
}
</script>

<style scoped lang="scss">
.upload-page {
  max-width: 1080px;
  margin: 24px auto;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  h2 { margin: 0; font-size: 18px; }
}
.action-bar, .next-step-bar {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
.summary-section {
  margin-top: 28px;
  border-top: 1px solid #ebeef5;
  padding-top: 16px;
}
</style>