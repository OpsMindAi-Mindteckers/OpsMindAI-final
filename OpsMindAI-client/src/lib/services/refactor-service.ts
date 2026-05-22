/**
 * Code Refactor Agent API Service
 */

import { apiClient } from '../api-client';
import type {
  AgentInfo,
  AgentListResponse,
  RefactorAnalyzeRequest,
  RefactorSuggestRequest,
  RefactorApplyRequest,
  RefactorJobStatus,
  RefactorSuggestResponse,
  RefactorApplyResponse,
  RefactorHistory,
  JobSubmitResponse,
} from '../api-types';

export const refactorService = {
  async listAgents(): Promise<AgentInfo[]> {
    const response = await apiClient.get<AgentListResponse | AgentInfo[]>('/agents');
    if (response.error) {
      console.error('List agents error:', response.error);
      return [];
    }
    const data = response.data;
    if (!data) return [];
    if (Array.isArray(data)) return data;
    return (data as AgentListResponse).agents ?? [];
  },

  async analyze(data: RefactorAnalyzeRequest): Promise<JobSubmitResponse | null> {
    const response = await apiClient.post<JobSubmitResponse>('/agents/refactor/analyze', data);
    if (response.error) {
      const detail =
        (response.error as any)?.detail ||
        (response.error as any)?.message ||
        JSON.stringify(response.error);
      throw new Error(`Analyze failed (HTTP ${response.status}): ${detail}`);
    }
    return response.data || null;
  },

  async getJobStatus(jobId: string): Promise<RefactorJobStatus | null> {
    const response = await apiClient.get<RefactorJobStatus>(`/agents/refactor/jobs/${jobId}`);
    if (response.error) {
      console.error('Get refactor job status error:', response.error);
      return null;
    }
    return response.data || null;
  },

  async suggest(data: RefactorSuggestRequest): Promise<RefactorSuggestResponse | null> {
    // Step 1: submit the suggest job
    const submitResp = await apiClient.post<{ job_id: string; status: string; message: string }>(
      '/agents/refactor/suggest',
      data,
    );
    if (submitResp.error) {
      const detail: string =
        (submitResp.error as any)?.detail ||
        (submitResp.error as any)?.message ||
        JSON.stringify(submitResp.error);
      if (submitResp.status === 400 && detail.toLowerCase().includes('no smell')) {
        return { job_id: data.source_job_id, status: 'completed', suggestions: [], message: detail };
      }
      throw new Error(`Suggest failed (HTTP ${submitResp.status}): ${detail}`);
    }

    const suggestJobId = submitResp.data?.job_id;
    if (!suggestJobId) return null;

    // Step 2: poll the suggest job until it completes (up to 10 min)
    const jobResult = await this.pollJobStatus(suggestJobId, 200, 3000);
    if (!jobResult) return null;
    if (jobResult.status === 'failed' || jobResult.status === 'error') {
      throw new Error((jobResult as any).error || 'Suggest job failed');
    }

    // Step 3: map PatchFile list → RefactorSuggestion list
    const patches: Array<{ file: string; diff: string; additions: number; deletions: number }> =
      (jobResult as any).result?.patches ?? [];

    const suggestions = patches.map((p) => ({
      smell_type: 'Code Improvement',
      file_path: p.file,
      description: `+${p.additions} / -${p.deletions} lines changed`,
      patch: p.diff,
    }));

    return {
      job_id: suggestJobId,
      status: 'completed',
      suggestions,
      summary: `Refactored ${patches.length} file(s) via ${(jobResult as any).result?.model_used ?? 'LLM'}`,
    };
  },

  async apply(data: RefactorApplyRequest): Promise<RefactorApplyResponse | null> {
    const response = await apiClient.post<RefactorApplyResponse>('/agents/refactor/apply', data);
    if (response.error) {
      console.error('Refactor apply error:', response.error);
      return null;
    }
    return response.data || null;
  },

  async getHistory(page: number = 1, limit: number = 20): Promise<RefactorHistory | null> {
    const response = await apiClient.get<RefactorHistory>(
      `/agents/refactor/history?page=${page}&limit=${limit}`
    );
    if (response.error) {
      console.error('Refactor history error:', response.error);
      return null;
    }
    return response.data || null;
  },

  async pollJobStatus(
    jobId: string,
    maxAttempts: number = 60,
    intervalMs: number = 2000
  ): Promise<RefactorJobStatus | null> {
    let attempts = 0;
    while (attempts < maxAttempts) {
      const status = await this.getJobStatus(jobId);
      if (!status) return null;
      if (status.status === 'completed' || status.status === 'failed' || status.status === 'error') {
        return status;
      }
      attempts++;
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    console.warn(`Refactor job ${jobId} polling timed out`);
    return null;
  },
};
