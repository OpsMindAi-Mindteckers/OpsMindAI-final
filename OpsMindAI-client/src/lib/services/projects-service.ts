/**
 * Projects API Service
 * Handles all project-related API calls
 */

import { apiClient } from '../api-client';
import type {
  CreateProjectRequest,
  CreateProjectResponse,
  ProjectResponse,
  ProjectListResponse,
  UpdateProjectRequest,
  FileListResponse,
  DiffResponse,
} from '../api-types';

export const projectsService = {
  /**
   * Create a new project
   */
  async createProject(data: CreateProjectRequest): Promise<CreateProjectResponse | null> {
    const response = await apiClient.post<CreateProjectResponse>('/projects', data);
    if (response.error) {
      console.error('Create project error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Get all projects with pagination
   */
  async listProjects(page: number = 1, pageSize: number = 10): Promise<ProjectListResponse | null> {
    const response = await apiClient.get<ProjectListResponse>(
      `/projects?page=${page}&page_size=${pageSize}`
    );
    if (response.error) {
      console.error('List projects error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Get a specific project by ID
   */
  async getProject(projectId: string): Promise<ProjectResponse | null> {
    const response = await apiClient.get<ProjectResponse>(`/projects/${projectId}`);
    if (response.error) {
      console.error('Get project error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Update a project
   */
  async updateProject(
    projectId: string,
    data: UpdateProjectRequest
  ): Promise<ProjectResponse | null> {
    const response = await apiClient.patch<ProjectResponse>(`/projects/${projectId}`, data);
    if (response.error) {
      console.error('Update project error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Delete a project
   */
  async deleteProject(projectId: string): Promise<boolean> {
    const response = await apiClient.delete<{ message: string }>(`/projects/${projectId}`);
    return !response.error;
  },

  /**
   * Get project build status
   */
  async getProjectStatus(projectId: string): Promise<any | null> {
    const response = await apiClient.get<any>(`/projects/${projectId}/status`);
    if (response.error) {
      console.error('Get project status error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Get project files
   */
  async getProjectFiles(projectId: string): Promise<FileListResponse | null> {
    const response = await apiClient.get<FileListResponse>(`/projects/${projectId}/files`);
    if (response.error) {
      console.error('Get project files error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Get diff between builds
   */
  async getProjectDiff(
    projectId: string,
    fromBuild: string,
    toBuild: string
  ): Promise<DiffResponse | null> {
    const response = await apiClient.get<DiffResponse>(
      `/projects/${projectId}/diff?from=${fromBuild}&to=${toBuild}`
    );
    if (response.error) {
      console.error('Get diff error:', response.error);
      return null;
    }
    return response.data || null;
  },
};
