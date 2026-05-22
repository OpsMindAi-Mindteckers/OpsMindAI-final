'use client';

import { useState, useCallback, useEffect } from 'react';
import { refactorService } from '@/lib/services/refactor-service';
import type {
  AgentInfo,
  RefactorAnalyzeRequest,
  RefactorSuggestRequest,
  RefactorApplyRequest,
  RefactorJobStatus,
  RefactorSuggestResponse,
} from '@/lib/api-types';

export function useRefactor() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(false);

  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<RefactorJobStatus | null>(null);
  const [polling, setPolling] = useState(false);

  const [suggestLoading, setSuggestLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<RefactorSuggestResponse | null>(null);
  const [suggestJobId, setSuggestJobId] = useState<string | null>(null);

  const [applyLoading, setApplyLoading] = useState(false);
  const [prUrl, setPrUrl] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    setAgentsLoading(true);
    try {
      const result = await refactorService.listAgents();
      setAgents(result);
    } catch (err) {
      console.error('Failed to fetch agents', err);
    } finally {
      setAgentsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const analyze = useCallback(async (data: RefactorAnalyzeRequest) => {
    setAnalyzeLoading(true);
    setError(null);
    setJobId(null);
    setJobStatus(null);
    setSuggestions(null);
    setPrUrl(null);
    try {
      const result = await refactorService.analyze(data);
      if (result?.job_id) {
        setJobId(result.job_id);
        return result;
      }
      setError('Analyze returned no job_id');
      return null;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analyze failed');
      return null;
    } finally {
      setAnalyzeLoading(false);
    }
  }, []);

  const pollJob = useCallback(async (id: string) => {
    setPolling(true);
    setError(null);
    try {
      const result = await refactorService.pollJobStatus(id);
      if (result) setJobStatus(result);
      if (result?.status === 'failed' || result?.status === 'error') {
        setError(result.error || 'Job failed');
      }
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Polling failed');
      return null;
    } finally {
      setPolling(false);
    }
  }, []);

  const suggest = useCallback(async (data: RefactorSuggestRequest) => {
    setSuggestLoading(true);
    setError(null);
    try {
      const result = await refactorService.suggest(data);
      if (result) {
        setSuggestions(result);
        setSuggestJobId(result.job_id);
      }
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Suggest failed');
      return null;
    } finally {
      setSuggestLoading(false);
    }
  }, []);

  const apply = useCallback(async (data: RefactorApplyRequest) => {
    setApplyLoading(true);
    setError(null);
    try {
      const result = await refactorService.apply(data);
      if (result?.pr_url) setPrUrl(result.pr_url);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Apply failed');
      return null;
    } finally {
      setApplyLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setJobId(null);
    setJobStatus(null);
    setSuggestions(null);
    setSuggestJobId(null);
    setPrUrl(null);
    setError(null);
  }, []);

  return {
    agents,
    agentsLoading,
    fetchAgents,
    analyzeLoading,
    jobId,
    jobStatus,
    polling,
    suggestLoading,
    suggestions,
    suggestJobId,
    applyLoading,
    prUrl,
    error,
    analyze,
    pollJob,
    suggest,
    apply,
    reset,
  };
}
