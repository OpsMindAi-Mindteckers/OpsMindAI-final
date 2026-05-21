/**
 * SRE / Incidents API Service
 * Handles all SRE and incident response API calls
 */

import { apiClient } from '../api-client';
import type {
  IngestRequest,
  RCARequest,
  RemediateRequest,
  JobSubmitResponse,
  JobStatusResponse,
  IncidentDetail,
  IncidentHistory,
} from '../api-types';

export const sreService = {
  /**
   * Ingest an alert (webhook-style)
   * Starts Phase 1: ingest alert + auto-dispatch RCA
   */
  async ingestAlert(data: IngestRequest): Promise<JobSubmitResponse | null> {
    const response = await apiClient.post<JobSubmitResponse>('/agents/sre/ingest', data);
    if (response.error) {
      console.error('Alert ingest error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Trigger Root Cause Analysis on an incident
   * Phase 2: manual RCA trigger
   */
  async triggerRCA(data: RCARequest): Promise<JobSubmitResponse | null> {
    const response = await apiClient.post<JobSubmitResponse>('/agents/sre/rca', data);
    if (response.error) {
      console.error('RCA trigger error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Trigger remediation on an incident
   * Phase 3: manual remediation trigger
   */
  async triggerRemediation(data: RemediateRequest): Promise<JobSubmitResponse | null> {
    const response = await apiClient.post<JobSubmitResponse>('/agents/sre/remediate', data);
    if (response.error) {
      console.error('Remediation trigger error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Get SRE job status by ID
   */
  async getJobStatus(jobId: string): Promise<JobStatusResponse | null> {
    const response = await apiClient.get<JobStatusResponse>(`/agents/sre/jobs/${jobId}`);
    if (response.error) {
      console.error('Get job status error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Get incident details including timeline and RCA results
   */
  async getIncident(incidentId: string): Promise<IncidentDetail | null> {
    const response = await apiClient.get<IncidentDetail>(`/agents/sre/incidents/${incidentId}`);
    if (response.error) {
      console.error('Get incident error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Get SRE job history for current user
   */
  async getHistory(page: number = 1, limit: number = 20): Promise<IncidentHistory | null> {
    const response = await apiClient.get<IncidentHistory>(
      `/agents/sre/history?page=${page}&limit=${limit}`
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
  ): Promise<JobStatusResponse | null> {
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
