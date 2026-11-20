import axios from 'axios';
import type { ComponentCategoryOption, ComponentLibraryItem } from '../types/component';

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 120000,
});

export const libraryApi = {
  async getCategories(): Promise<ComponentCategoryOption[]> {
    const { data } = await request.get<{ code: number; data: ComponentCategoryOption[] }>(
      '/api/v1/components/categories'
    );
    return data.data;
  },

  async listComponents(category?: string, keyword?: string): Promise<{
    total: number;
    pgvector_enabled: boolean;
    items: ComponentLibraryItem[];
  }> {
    const { data } = await request.get('/api/v1/components/', {
      params: { category, keyword },
    });
    return data.data;
  },

  async uploadCatalogFiles(
    files: File[],
    defaultCategory?: string,
    defaultManufacturer?: string
  ) {
    const formData = new FormData();
    files.forEach((f) => formData.append('files', f));
    if (defaultCategory) formData.append('default_category', defaultCategory);
    if (defaultManufacturer) formData.append('default_manufacturer', defaultManufacturer);

    const { data } = await request.post('/api/v1/components/upload-catalog', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  async seedDefaultLibrary() {
    const { data } = await request.post('/api/v1/components/seed');
    return data;
  },

  async updateComponent(compId: string, payload: Partial<ComponentLibraryItem>) {
    const { data } = await request.put(`/api/v1/components/${compId}`, payload);
    return data;
  },

  async deleteComponent(compId: string) {
    const { data } = await request.delete(`/api/v1/components/${compId}`);
    return data;
  },
};
