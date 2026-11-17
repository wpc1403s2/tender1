import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { TenderReviewData } from '../types/tender';

export const useTenderStore = defineStore('tender', () => {
  const currentProject = ref<TenderReviewData | null>(null);

  return {
    currentProject,
  };
});