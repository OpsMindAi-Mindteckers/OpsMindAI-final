/**
 * Testing Agent API Service
 * Handles all testing-related API calls
 */

import { apiClient } from '../api-client';
import type {
  GenerateTestRequest,
  SuiteRequest,
  RegressionRequest,
  JobSubmitResponse,
  TestingJobStatus,
  TestingHistory,
} from '../api-types';

export const testingService = {
  /**
   * Generate test stubs
   * Phase 1: generate test stubs
   */
  async generateTests(data: GenerateTestRequest): Promise<JobSubmitResponse | null> {
    const response = await apiClient.post<JobSubmitResponse>('/agents/testing/generate', data);
    if (response.error) {
      console.error('Generate tests error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Run test suite
   * Phase 2: run tests + coverage gate
   */
  async runTestSuite(data: SuiteRequest): Promise<JobSubmitResponse | null> {
    const response = await apiClient.post<JobSubmitResponse>('/agents/testing/suite', data);
    if (response.error) {
      console.error('Run test suite error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Build regression suite
   * Phase 3: build regression suite
   */
  async buildRegressionSuite(data: RegressionRequest): Promise<JobSubmitResponse | null> {
    const response = await apiClient.post<JobSubmitResponse>('/agents/testing/regression', data);
    if (response.error) {
      console.error('Build regression suite error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Get testing job status by ID
   */
  async getJobStatus(jobId: string): Promise<TestingJobStatus | null> {
    const response = await apiClient.get<TestingJobStatus>(`/agents/testing/jobs/${jobId}`);
    if (response.error) {
      console.error('Get job status error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Get testing job history for current user
   */
  async getHistory(page: number = 1, limit: number = 20): Promise<TestingHistory | null> {
    const response = await apiClient.get<TestingHistory>(
      `/agents/testing/history?page=${page}&limit=${limit}`
    );
    if (response.error) {
      console.error('Get history error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Poll for job completion
   */
  async pollJobStatus(
    jobId: string,
    maxAttempts: number = 60,
    intervalMs: number = 1000
  ): Promise<TestingJobStatus | null> {
    let attempts = 0;

    while (attempts < maxAttempts) {
      const status = await this.getJobStatus(jobId);
      if (!status) {
        return null;
      }

      if (status.status === 'completed' || status.status === 'failed' || status.status === 'error') {
        return status;
      }

      attempts++;
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }

    console.warn(`Job ${jobId} polling timed out after ${maxAttempts} attempts`);
    return null;
  },
};
