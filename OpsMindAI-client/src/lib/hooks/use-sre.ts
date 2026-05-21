/**
 * React hooks for SRE/Incidents operations
 */

'use client';

import { useState, useCallback } from 'react';
import { sreService } from '@/lib/services';
import type { IngestRequest, RCARequest, RemediateRequest, IncidentDetail } from '@/lib/api-types';

/**
 * Hook for SRE incident operations
 */
export function useSRE() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [incident, setIncident] = useState<IncidentDetail | null>(null);

  const ingestAlert = useCallback(
    async (data: IngestRequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await sreService.ingestAlert(data);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to ingest alert';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const triggerRCA = useCallback(
    async (data: RCARequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await sreService.triggerRCA(data);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to trigger RCA';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const triggerRemediation = useCallback(
    async (data: RemediateRequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await sreService.triggerRemediation(data);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to trigger remediation';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const getIncident = useCallback(
    async (incidentId: string) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await sreService.getIncident(incidentId);
        if (result) {
          setIncident(result);
        }
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch incident';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const pollJobStatus = useCallback(
    async (jobId: string) => {
      try {
        return await sreService.pollJobStatus(jobId);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to poll job status';
        setError(message);
        return null;
      }
    },
    []
  );

  return {
    incident,
    isLoading,
    error,
    ingestAlert,
    triggerRCA,
    triggerRemediation,
    getIncident,
    pollJobStatus,
  };
}
