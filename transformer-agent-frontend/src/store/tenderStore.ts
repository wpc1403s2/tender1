import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { TenderReviewData, SourceReference } from '../types/tender';

export const useTenderStore = defineStore('tender', () => {
  const currentProject = ref<TenderReviewData | null>(null);

  const activeFileName = ref<string>('');
  const activePage = ref<number>(1);
  const activeBbox = ref<[number, number, number, number] | null>(null);
  const activeOriginalText = ref<string>('');

  function triggerTraceHighlight(refData: SourceReference) {
    if (!refData) return;
    if (refData.file_name) {
      activeFileName.value = refData.file_name;
    }
    activePage.value = refData.page_number || 1;
    activeBbox.value = refData.bbox || null;
    activeOriginalText.value = refData.original_text || '';
  }

  function clearHighlight() {
    activeBbox.value = null;
    activeOriginalText.value = '';
  }

  return {
    currentProject,
    activeFileName,
    activePage,
    activeBbox,
    activeOriginalText,
    triggerTraceHighlight,
    clearHighlight,
  };
});