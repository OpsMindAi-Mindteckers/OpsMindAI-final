/**
 * React hooks for Projects operations
 */

'use client';

import { useState, useCallback } from 'react';
import { projectsService } from '@/lib/services';
import type {
  CreateProjectRequest,
  ProjectResponse,
  ProjectListResponse,
  UpdateProjectRequest,
} from '@/lib/api-types';

/**
 * Hook for project operations
 */
export function useProjects() {
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [currentProject, setCurrentProject] = useState<ProjectResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createProject = useCallback(
    async (data: CreateProjectRequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await projectsService.createProject(data);
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to create project';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const listProjects = useCallback(
    async (page: number = 1, pageSize: number = 10) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await projectsService.listProjects(page, pageSize);
        if (result) {
          setProjects(result.projects);
          return result;
        }
        return null;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch projects';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const getProject = useCallback(
    async (projectId: string) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await projectsService.getProject(projectId);
        if (result) {
          setCurrentProject(result);
        }
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch project';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const updateProject = useCallback(
    async (projectId: string, data: UpdateProjectRequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await projectsService.updateProject(projectId, data);
        if (result) {
          setCurrentProject(result);
        }
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to update project';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const deleteProject = useCallback(
    async (projectId: string) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await projectsService.deleteProject(projectId);
        if (result) {
          setProjects((prev) => prev.filter((p) => p.project_id !== projectId));
        }
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to delete project';
        setError(message);
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  return {
    projects,
    currentProject,
    isLoading,
    error,
    createProject,
    listProjects,
    getProject,
    updateProject,
    deleteProject,
  };
}
