/**
 * React hooks for Testing operations
 */

'use client';

import { useState, useCallback } from 'react';
import { testingService } from '@/lib/services';
import type {
  GenerateTestRequest,
  SuiteRequest,
  RegressionRequest,
  TestingJobStatus,
} from '@/lib/api-types';

/**
 * Hook for testing operations
 */
export function useTesting() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<TestingJobStatus | null>(null);

  const generateTests = useCallback(
    async (data: GenerateTestRequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await testingService.generateTests(data);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to generate tests';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const runTestSuite = useCallback(
    async (data: SuiteRequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await testingService.runTestSuite(data);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to run test suite';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const buildRegressionSuite = useCallback(
    async (data: RegressionRequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await testingService.buildRegressionSuite(data);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to build regression suite';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const getJobStatus = useCallback(
    async (jobId: string) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await testingService.getJobStatus(jobId);
        if (result) {
          setJobStatus(result);
        }
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch job status';
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
        return await testingService.pollJobStatus(jobId);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to poll job status';
        setError(message);
        return null;
      }
    },
    []
  );

  return {
    jobStatus,
    isLoading,
    error,
    generateTests,
    runTestSuite,
    buildRegressionSuite,
    getJobStatus,
    pollJobStatus,
  };
}
