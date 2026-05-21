/**
 * Users API Service
 * Handles all user management API calls
 */

import { apiClient } from '../api-client';
import type { UserResponse, UserListResponse } from '../api-types';

export const usersService = {
  /**
   * Get all users (admin only)
   */
  async listUsers(page: number = 1, pageSize: number = 10): Promise<UserListResponse | null> {
    const response = await apiClient.get<UserListResponse>(
      `/users?page=${page}&page_size=${pageSize}`
    );
    if (response.error) {
      console.error('List users error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Get a specific user by ID
   */
  async getUser(userId: string): Promise<UserResponse | null> {
    const response = await apiClient.get<UserResponse>(`/users/${userId}`);
    if (response.error) {
      console.error('Get user error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Get current user profile
   */
  async getCurrentUser(): Promise<UserResponse | null> {
    const response = await apiClient.get<UserResponse>('/users/me');
    if (response.error) {
      console.error('Get current user error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Update user profile
   */
  async updateUser(userId: string, data: Partial<UserResponse>): Promise<UserResponse | null> {
    const response = await apiClient.patch<UserResponse>(`/users/${userId}`, data);
    if (response.error) {
      console.error('Update user error:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Delete a user
   */
  async deleteUser(userId: string): Promise<boolean> {
    const response = await apiClient.delete<{ message: string }>(`/users/${userId}`);
    return !response.error;
  },
};
