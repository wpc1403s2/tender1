import axios from 'axios';
import type { TenderReviewData, DocumentSummary } from '../types/tender';

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 120000, // 标书解析耗时较长，设置 120s 超时
});

export const tenderApi = {
  // 1. 步骤一：上传标书文件包并触发预处理入内存
  async uploadTenderFiles(files: File[], projectId?: string) {
    const formData = new FormData();
    files.forEach((f) => formData.append('files', f));
    if (projectId) formData.append('project_id', projectId);

    const { data } = await request.post<{
      code: number;
      message: string;
      data: { project_id: string; documents_summary: DocumentSummary[] };
    }>('/api/v1/tender/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data.data;
  },

  // 2. 触发多智能体提取与 RAG 组部件匹配任务
  async startAgentExtraction(projectId: string, force = false): Promise<TenderReviewData> {
    const { data } = await request.post(`/api/v1/tender/${projectId}/analyze`, null, { params: { force } });
    return data.data;
  },

  // 3. 获取项目的提取与组部件匹配完整结果
  async getReviewData(projectId: string): Promise<TenderReviewData> {
    const { data } = await request.get<{ code: number; data: TenderReviewData }>(
      `/api/v1/tender/${projectId}/review`
    );
    return data.data;
  },

  // 4. 保存人工修订后的数据并导出《新版初评表》Excel
  async confirmAndExportExcel(projectId: string, payload: Partial<TenderReviewData>) {
    const response = await request.post(
      `/api/v1/export/${projectId}/evaluation-sheet`,
      payload,
      { responseType: 'blob' }
    );
    // 触发浏览器文件下载
    const blob = new Blob([response.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `投标初评表与组部件选型_${projectId}.xlsx`;
    link.click();
    window.URL.revokeObjectURL(url);
  },
};
