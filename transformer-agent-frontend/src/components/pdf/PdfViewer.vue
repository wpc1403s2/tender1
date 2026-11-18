<template>
  <div class="pdf-viewer-container">
    <!-- 顶部工具栏（已修复长文件名挤压换行问题） -->
    <div class="pdf-toolbar">
      <div class="doc-info" :title="fileName">
        <el-tag size="small" type="info" class="file-tag">
          {{ fileName || '未选择文档' }}
        </el-tag>
      </div>

      <div class="page-controls">
        <el-button size="small" :disabled="currentPage <= 1" @click="changePage(-1)">
          上一页
        </el-button>
        <span class="page-indicator">第 {{ currentPage }} / {{ totalPages || 1 }} 页</span>
        <el-button size="small" :disabled="currentPage >= totalPages" @click="changePage(1)">
          下一页
        </el-button>
      </div>

      <div class="zoom-controls">
        <el-button size="small" @click="changeZoom(-0.15)">-</el-button>
        <span class="zoom-text">{{ Math.round(scale * 100) }}%</span>
        <el-button size="small" @click="changeZoom(0.15)">+</el-button>
      </div>
    </div>

    <!-- 错误或文件缺失提示层 -->
    <div v-if="loadError" class="pdf-error-banner">
      <el-alert :title="loadError" type="warning" show-icon :closable="false" />
    </div>

    <!-- PDF 画布与高亮蒙层滚动区 -->
    <div ref="scrollContainer" class="pdf-canvas-wrapper">
      <div class="canvas-stage" :style="{ width: canvasWidth + 'px', height: canvasHeight + 'px' }">
        <canvas ref="pdfCanvas"></canvas>

        <!-- BBox 坐标溯源高亮框 -->
        <div
          v-if="highlightStyle"
          ref="highlightBoxRef"
          class="bbox-highlight-overlay"
          :style="highlightStyle"
          :title="tenderStore.activeOriginalText"
        >
          <span class="trace-badge">原文溯源锚点</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue';
import * as pdfjsLib from 'pdfjs-dist';
// 【关键修复1】直接从本地 node_modules 引入 worker，彻底解决 CDN 加载失败导致白屏
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.js?url';
import { useTenderStore } from '../../store/tenderStore';
import { convertPdfBboxToStyle } from '../../utils/bboxUtils';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const props = defineProps<{
  pdfUrl: string;
  fileName: string;
}>();

const tenderStore = useTenderStore();
const pdfCanvas = ref<HTMLCanvasElement | null>(null);
const scrollContainer = ref<HTMLElement | null>(null);
const highlightBoxRef = ref<HTMLElement | null>(null);

// 【关键修复2】必须使用普通非响应式变量保存 pdfDoc 和 renderTask，防止被 Vue3 Proxy 破坏
let pdfDoc: any = null;
let currentRenderTask: any = null;

const currentPage = ref<number>(1);
const totalPages = ref<number>(0);
const scale = ref<number>(1.2);
const canvasWidth = ref<number>(760);
const canvasHeight = ref<number>(1050);
const loadError = ref<string>('');

const highlightStyle = computed(() => {
  if (tenderStore.activePage !== currentPage.value || !tenderStore.activeBbox) {
    return null;
  }
  return convertPdfBboxToStyle(tenderStore.activeBbox, scale.value);
});

async function loadPdfDocument(url: string) {
  if (!url) return;
  loadError.value = '';
  try {
    const loadingTask = pdfjsLib.getDocument({
      url,
      // 支持标准字体渲染，防止部分特殊工业符号空白
      cMapUrl: 'https://unpkg.com/pdfjs-dist@3.11.174/cmaps/',
      cMapPacked: true,
    });
    pdfDoc = await loadingTask.promise;
    totalPages.value = pdfDoc.numPages;

    // 同步当前激活页码（防止超出总页数）
    const targetPage = Math.min(Math.max(1, tenderStore.activePage || 1), totalPages.value);
    currentPage.value = targetPage;
    await renderPage(targetPage);
  } catch (err: any) {
    console.error('PDF 加载失败:', err);
    loadError.value = `无法加载 PDF 文件 (${url})。请确认前端 public/ 目录下已放置对应的 PDF 文件，或后端文件流接口已启动。`;
  }
}

async function renderPage(pageNum: number) {
  if (!pdfDoc || !pdfCanvas.value) return;

  try {
    // 如果上一次渲染还没结束，先取消它，防止 Canvas 并发冲突空白
    if (currentRenderTask) {
      currentRenderTask.cancel();
    }

    const page = await pdfDoc.getPage(pageNum);
    const viewport = page.getViewport({ scale: scale.value });

    const canvas = pdfCanvas.value;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    canvas.width = viewport.width;
    canvas.height = viewport.height;
    canvasWidth.value = viewport.width;
    canvasHeight.value = viewport.height;

    currentRenderTask = page.render({ canvasContext: ctx, viewport });
    await currentRenderTask.promise;
    currentRenderTask = null;

    await nextTick();
    if (highlightBoxRef.value && scrollContainer.value) {
      highlightBoxRef.value.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  } catch (err: any) {
    if (err?.name !== 'RenderingCancelledException') {
      console.error('单页渲染异常:', err);
    }
  }
}

function changePage(delta: number) {
  const target = currentPage.value + delta;
  if (target >= 1 && target <= totalPages.value) {
    currentPage.value = target;
    tenderStore.activePage = target;
    renderPage(target);
  }
}

function changeZoom(delta: number) {
  scale.value = Math.min(2.5, Math.max(0.6, scale.value + delta));
  renderPage(currentPage.value);
}

watch(
  () => [tenderStore.activePage, tenderStore.activeBbox],
  async ([newPage]) => {
    if (!pdfDoc) return;
    const validPage = Math.min(Math.max(1, Number(newPage) || 1), totalPages.value);
    if (validPage !== currentPage.value) {
      currentPage.value = validPage;
      await renderPage(validPage);
    } else {
      await nextTick();
      highlightBoxRef.value?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
);

watch(() => props.pdfUrl, (newUrl) => loadPdfDocument(newUrl));

onMounted(() => {
  if (props.pdfUrl) loadPdfDocument(props.pdfUrl);
});
</script>

<style scoped lang="scss">
.pdf-viewer-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #2b2d30;
  border-radius: 6px;
  overflow: hidden;
}

.pdf-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #1e1f22;
  color: #fff;
  border-bottom: 1px solid #3c3f41;
  flex-shrink: 0;

  .doc-info {
    flex: 1;
    min-width: 0; /* 允许 flex 子项收缩截断 */
    .file-tag {
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      display: inline-block;
      vertical-align: middle;
    }
  }

  .page-controls,
  .zoom-controls {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0; /* 禁止按钮区被长文件名挤压换行 */
    white-space: nowrap;
  }

  .page-indicator,
  .zoom-text {
    font-size: 12px;
    min-width: 55px;
    text-align: center;
  }
}

.pdf-error-banner {
  padding: 8px 12px;
  background: #2b2d30;
}

.pdf-canvas-wrapper {
  flex: 1;
  overflow: auto;
  display: flex;
  justify-content: center;
  padding: 16px;

  .canvas-stage {
    position: relative;
    background: #fff;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
  }
}

.bbox-highlight-overlay {
  position: absolute;
  background-color: rgba(255, 215, 0, 0.35);
  border: 2px solid #ff5722;
  border-radius: 3px;
  pointer-events: none;
  z-index: 10;
  animation: pulse-border 1.5s infinite;

  .trace-badge {
    position: absolute;
    top: -22px;
    left: -2px;
    background: #ff5722;
    color: #fff;
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 3px;
    white-space: nowrap;
  }
}

@keyframes pulse-border {
  0% { box-shadow: 0 0 0 0 rgba(255, 87, 34, 0.7); }
  70% { box-shadow: 0 0 0 8px rgba(255, 87, 34, 0); }
  100% { box-shadow: 0 0 0 0 rgba(255, 87, 34, 0); }
}
</style>