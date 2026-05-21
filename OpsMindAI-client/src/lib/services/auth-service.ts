/**
 * Authentication API Service
 * Handles all auth-related API calls
 */

import { apiClient } from '../api-client';
import type {
  RegisterRequest,
  LoginRequest,
  TokenResponse,
  RegisterResponse,
  UserProfile,
} from '../api-types';

export const authService = {
  /**
   * Register a new user
   */
  async register(data: RegisterRequest): Promise<RegisterResponse | null> {
    const response = await apiClient.post<RegisterResponse>('/auth/register', data);
    if (response.error) {
      console.error('Registration error:', response.error);
      return null;
    }
    if (response.data?.access_token) {
      localStorage.setItem('auth_token', response.data.access_token);
    }
    return response.data || null;
  },

  /**
   * Login user
   */
  async login(data: LoginRequest): Promise<TokenResponse | null> {
    const response = await apiClient.post<TokenResponse>('/auth/login', data);
    if (response.error) {
      console.error('Login error:', response.error);
      return null;
    }
    if (response.data?.access_token) {
      localStorage.setItem('auth_token', response.data.access_token);
    }
    return response.data || null;
  },

  /**
   * Logout user
   */
  async logout(): Promise<boolean> {
    const response = await apiClient.post<{ message: string }>('/auth/logout');
    if (!response.error) {
      localStorage.removeItem('auth_token');
      return true;
    }
    return false;
  },

  /**
   * Set authentication cookie after Clerk frontend sign-in
   */
  async setCookie(): Promise<boolean> {
    const response = await apiClient.post<{ message: string }>('/auth/set-cookie');
    return !response.error;
  },

  /**
   * Clear authentication cookie
   */
  async clearCookie(): Promise<boolean> {
    const response = await apiClient.post<{ message: string }>('/auth/clear-cookie');
    return !response.error;
  },

  /**
   * Get current user profile
   */
  async getCurrentUser(): Promise<UserProfile | null> {
    const response = await apiClient.get<UserProfile>('/auth/me');
    if (response.error) {
      console.error('Error fetching current user:', response.error);
      return null;
    }
    return response.data || null;
  },

  /**
   * Store token in localStorage
   */
  setToken(token: string): void {
    localStorage.setItem('auth_token', token);
  },

  /**
   * Get token from localStorage
   */
  getToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('auth_token');
  },

  /**
   * Check if user is authenticated
   */
  isAuthenticated(): boolean {
    return !!this.getToken();
  },

  /**
   * Clear authentication
   */
  clearAuth(): void {
    localStorage.removeItem('auth_token');
  },
};
