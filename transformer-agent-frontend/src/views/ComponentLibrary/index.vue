<template>
  <div class="library-page">
    <!-- 顶部栏 -->
    <header class="lib-header">
      <div class="left-info">
        <el-button size="small" @click="router.push('/upload')">← 返回标书上传</el-button>
        <h2>内部组部件标准品知识库 (PostgreSQL + pgvector)</h2>
        <el-tag :type="pgvectorEnabled ? 'success' : 'warning'" size="small" effect="dark">
          {{ pgvectorEnabled ? 'pgvector 向量引擎在线' : '本地持久化向量引擎在线' }}
        </el-tag>
        <el-tag type="info" size="small">共 {{ componentList.length }} 款标准型号</el-tag>
      </div>
      <div class="right-btns">
        <el-button type="warning" plain :loading="seeding" @click="handleSeedDefault">
          一键初始化/重置 16 款行业典型标准品种子库
        </el-button>
        <el-button type="primary" @click="showUploadDialog = true">
          + 上传供应商样册 PDF 自动拆解多型号入库
        </el-button>
      </div>
    </header>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select
        v-model="selectedCategory"
        placeholder="按16大组部件品类筛选"
        clearable
        style="width: 260px"
        @change="loadLibrary"
      >
        <el-option label="全部品类 (All Categories)" value="ALL" />
        <el-option
          v-for="cat in categories"
          :key="cat.code"
          :label="cat.label"
          :value="cat.code"
        />
      </el-select>

      <el-input
        v-model="searchKeyword"
        placeholder="搜索品牌 (如 Siemens, 华明, 昆仑, EMB, Qualitrol) 或型号 / 参数..."
        clearable
        style="width: 380px"
        @clear="loadLibrary"
        @keyup.enter="loadLibrary"
      />
      <el-button type="primary" plain @click="loadLibrary">查询</el-button>
    </div>

    <!-- 组部件列表表格 -->
    <div class="table-container">
      <el-table :data="componentList" v-loading="loading" border stripe height="calc(100vh - 190px)">
        <el-table-column prop="category_label" label="组部件大类" width="210">
          <template #default="{ row }">
            <el-tag type="primary" effect="light">{{ row.category_label }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="manufacturer" label="供应商 / 品牌" width="190" />
        <el-table-column prop="model_series" label="具体产品型号" width="230">
          <template #default="{ row }">
            <strong>{{ row.model_series }}</strong>
          </template>
        </el-table-column>

        <el-table-column label="硬规则过滤指标 (key_metrics)" width="230">
          <template #default="{ row }">
            <div class="tag-wrap">
              <el-tag
                v-for="(val, key) in row.key_metrics"
                :key="key"
                size="small"
                type="warning"
                effect="plain"
              >
                {{ key }}: {{ val }}
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="详细技术规范参数 (specs_json)" min-width="320">
          <template #default="{ row }">
            <div class="specs-list">
              <div v-for="(val, key) in row.specs_json" :key="key" class="spec-line">
                <span class="spec-k">{{ key }}：</span>
                <span class="spec-v">{{ val }}</span>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="来源样册溯源" width="160" align="center">
          <template #default="{ row }">
            <template v-if="row.catalog_ref && row.catalog_ref.file_name">
              <el-button
                type="primary"
                link
                size="small"
                @click="openPreviewAndEdit(row, true)"
              >
                📄 {{ row.catalog_ref.file_name }} (P.{{ row.catalog_ref.page_number }})
              </el-button>
            </template>
            <el-tag v-else size="small" type="info">内置标准品库</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openPreviewAndEdit(row, false)">
              编辑参数
            </el-button>
            <el-popconfirm
              title="确定从标准品知识库中删除该型号吗？"
              @confirm="handleDelete(row.comp_id)"
            >
              <template #reference>
                <el-button size="small" type="danger" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 弹窗 1：批量上传供应商样册 PDF -->
    <el-dialog
      v-model="showUploadDialog"
      title="上传供应商产品样册 PDF（DeepSeek 自动拆解多型号 + BBox 锚定 + 向量化入库）"
      width="640px"
    >
      <el-form label-width="140px">
        <el-form-item label="预设组部件品类">
          <el-select v-model="uploadForm.category" placeholder="由大模型自动识别品类" clearable style="width: 100%">
            <el-option label="由 DeepSeek 自动识别品类" value="AUTO" />
            <el-option
              v-for="cat in categories"
              :key="cat.code"
              :label="cat.label"
              :value="cat.code"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="供应商/品牌名称">
          <el-input
            v-model="uploadForm.manufacturer"
            placeholder="可选，如 Siemens / Qualitrol / 昆仑 (留空则由大模型从样册提取)"
          />
        </el-form-item>

        <el-form-item label="样册文件 (PDF等)">
          <el-upload
            drag
            multiple
            :auto-upload="false"
            :on-change="handleCatalogFileChange"
            :file-list="catalogFileList"
            accept=".pdf,.doc,.docx,.xls,.xlsx"
            style="width: 100%"
          >
            <div class="el-upload__text">
              将供应商产品样册 PDF 拖到此处，或 <em>点击选择</em><br />
              <small style="color: #909399">支持单份 PDF 含多个系列型号，系统将自动拆分为多条标准品并绑定原文坐标</small>
            </div>
          </el-upload>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="uploadingCatalog"
          :disabled="rawCatalogFiles.length === 0"
          @click="submitCatalogUpload"
        >
          {{ uploadingCatalog ? '正在解析样册并拆解型号入库...' : '开始解析并向量化入库' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 弹窗 2：编辑组件 JSON 参数 & 预览样册 PDF 原文 BBox -->
    <el-dialog
      v-model="showEditDialog"
      :title="`组件参数编辑与样册溯源 — [${editForm.manufacturer}] ${editForm.model_series}`"
      width="1100px"
      top="5vh"
    >
      <div class="edit-dialog-body">
        <!-- 左侧：如果有样册 PDF，直接渲染 PdfViewer 并高亮 BBox -->
        <div v-if="previewPdfUrl" class="catalog-pdf-pane">
          <PdfViewer :pdf-url="previewPdfUrl" :file-name="editForm.catalog_ref?.file_name || ''" />
        </div>

        <!-- 右侧：结构化参数编辑表单 -->
        <div class="edit-form-pane">
          <el-form label-width="115px" size="small">
            <el-form-item label="组部件品类">
              <el-select v-model="editForm.component_category" style="width: 100%">
                <el-option
                  v-for="cat in categories"
                  :key="cat.code"
                  :label="cat.label"
                  :value="cat.code"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="制造商品牌">
              <el-input v-model="editForm.manufacturer" />
            </el-form-item>
            <el-form-item label="具体产品型号">
              <el-input v-model="editForm.model_series" />
            </el-form-item>
            <el-form-item label="向量检索摘要">
              <el-input v-model="editForm.summary_text" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item label="硬规则指标 JSON">
              <el-input v-model="editKeyMetricsStr" type="textarea" :rows="4" />
            </el-form-item>
            <el-form-item label="技术参数 JSON">
              <el-input v-model="editSpecsJsonStr" type="textarea" :rows="9" />
            </el-form-item>
          </el-form>
        </div>
      </div>
      <template #footer>
        <el-button @click="showEditDialog = false">关闭</el-button>
        <el-button type="primary" :loading="savingEdit" @click="saveComponentEdit">
          保存修改并重新生成向量
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { libraryApi } from '../../api/library';
import { useTenderStore } from '../../store/tenderStore';
import PdfViewer from '../../components/pdf/PdfViewer.vue';
import type { ComponentCategoryOption, ComponentLibraryItem } from '../../types/component';

const router = useRouter();
const tenderStore = useTenderStore();
const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const categories = ref<ComponentCategoryOption[]>([]);
const componentList = ref<ComponentLibraryItem[]>([]);
const pgvectorEnabled = ref(false);
const loading = ref(false);
const seeding = ref(false);

const selectedCategory = ref('ALL');
const searchKeyword = ref('');

// 上传样册状态
const showUploadDialog = ref(false);
const uploadingCatalog = ref(false);
const catalogFileList = ref<any[]>([]);
const rawCatalogFiles = ref<File[]>([]);
const uploadForm = reactive({
  category: 'AUTO',
  manufacturer: '',
});

// 编辑与样册预览状态
const showEditDialog = ref(false);
const savingEdit = ref(false);
const editForm = reactive<ComponentLibraryItem>({
  comp_id: '',
  component_category: '',
  category_label: '',
  manufacturer: '',
  model_series: '',
  key_metrics: {},
  specs_json: {},
  summary_text: '',
  catalog_ref: null,
});
const editKeyMetricsStr = ref('{}');
const editSpecsJsonStr = ref('{}');

const previewPdfUrl = computed(() => {
  const refObj = editForm.catalog_ref;
  if (!refObj || !refObj.file_name) return '';
  if (refObj.file_url) {
    return refObj.file_url.startsWith('http') ? refObj.file_url : `${baseUrl}${refObj.file_url}`;
  }
  return `${baseUrl}/api/v1/components/catalogs/${encodeURIComponent(refObj.file_name)}`;
});

async function loadLibrary() {
  loading.value = true;
  try {
    const res = await libraryApi.listComponents(
      selectedCategory.value === 'ALL' ? undefined : selectedCategory.value,
      searchKeyword.value
    );
    componentList.value = res.items;
    pgvectorEnabled.value = res.pgvector_enabled;
  } catch (err: any) {
    ElMessage.error(err.message || '加载组部件标准库失败');
  } finally {
    loading.value = false;
  }
}

async function handleSeedDefault() {
  seeding.value = true;
  try {
    const res = await libraryApi.seedDefaultLibrary();
    ElMessage.success(res.message || '种子库初始化成功');
    await loadLibrary();
  } catch (err: any) {
    ElMessage.error(err.message || '初始化种子库失败');
  } finally {
    seeding.value = false;
  }
}

function handleCatalogFileChange(_file: any, uploadFiles: any[]) {
  catalogFileList.value = uploadFiles;
  rawCatalogFiles.value = uploadFiles.map((f) => f.raw);
}

async function submitCatalogUpload() {
  uploadingCatalog.value = true;
  try {
    const res = await libraryApi.uploadCatalogFiles(
      rawCatalogFiles.value,
      uploadForm.category,
      uploadForm.manufacturer
    );
    ElMessage.success(res.message || '样册解析入库完成！');
    showUploadDialog.value = false;
    catalogFileList.value = [];
    rawCatalogFiles.value = [];
    await loadLibrary();
  } catch (err: any) {
    ElMessage.error(err.message || '样册上传解析失败');
  } finally {
    uploadingCatalog.value = false;
  }
}

function openPreviewAndEdit(row: ComponentLibraryItem, focusPdf: boolean) {
  Object.assign(editForm, JSON.parse(JSON.stringify(row)));
  editKeyMetricsStr.value = JSON.stringify(row.key_metrics || {}, null, 2);
  editSpecsJsonStr.value = JSON.stringify(row.specs_json || {}, null, 2);
  showEditDialog.value = true;

  if (row.catalog_ref && (focusPdf || row.catalog_ref.file_name)) {
    tenderStore.triggerTraceHighlight(row.catalog_ref);
  }
}

async function saveComponentEdit() {
  let parsedMetrics = {};
  let parsedSpecs = {};
  try {
    parsedMetrics = JSON.parse(editKeyMetricsStr.value || '{}');
    parsedSpecs = JSON.parse(editSpecsJsonStr.value || '{}');
  } catch {
    ElMessage.error('JSON 格式不合法，请检查大括号与引号！');
    return;
  }

  savingEdit.value = true;
  try {
    await libraryApi.updateComponent(editForm.comp_id, {
      component_category: editForm.component_category,
      manufacturer: editForm.manufacturer,
      model_series: editForm.model_series,
      summary_text: editForm.summary_text,
      key_metrics: parsedMetrics,
      specs_json: parsedSpecs,
    });
    ElMessage.success('组件参数已更新并重新向量化！');
    showEditDialog.value = false;
    await loadLibrary();
  } catch (err: any) {
    ElMessage.error(err.message || '保存失败');
  } finally {
    savingEdit.value = false;
  }
}

async function handleDelete(compId: string) {
  try {
    await libraryApi.deleteComponent(compId);
    ElMessage.success('已删除该组件');
    await loadLibrary();
  } catch (err: any) {
    ElMessage.error(err.message || '删除失败');
  }
}

onMounted(async () => {
  try {
    categories.value = await libraryApi.getCategories();
  } catch {
    // ignore
  }
  await loadLibrary();
});
</script>

<style scoped lang="scss">
.library-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f7fa;
}
.lib-header {
  height: 60px;
  background: #fff;
  border-bottom: 1px solid #dcdfe6;
  padding: 0 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  .left-info {
    display: flex;
    align-items: center;
    gap: 12px;
    h2 {
      margin: 0;
      font-size: 17px;
      color: #303133;
    }
  }
  .right-btns {
    display: flex;
    gap: 10px;
  }
}
.filter-bar {
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  gap: 12px;
  align-items: center;
}
.table-container {
  flex: 1;
  padding: 12px 20px;
  overflow: hidden;
}
.tag-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.specs-list {
  font-size: 12px;
  line-height: 1.5;
  .spec-line {
    margin-bottom: 2px;
    .spec-k {
      font-weight: 600;
      color: #606266;
    }
    .spec-v {
      color: #303133;
    }
  }
}
.edit-dialog-body {
  display: flex;
  gap: 16px;
  height: 540px;
  .catalog-pdf-pane {
    width: 52%;
    height: 100%;
  }
  .edit-form-pane {
    flex: 1;
    overflow-y: auto;
  }
}
</style>
