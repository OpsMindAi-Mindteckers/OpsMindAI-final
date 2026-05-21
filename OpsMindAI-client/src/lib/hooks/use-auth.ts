/**
 * React hooks for API operations
 */

'use client';

import { useState, useCallback } from 'react';
import { authService } from '@/lib/services';
import type { LoginRequest, RegisterRequest, UserProfile } from '@/lib/api-types';

/**
 * Hook for authentication operations
 */
export function useAuth() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = useCallback(
    async (credentials: LoginRequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await authService.login(credentials);
        if (result) {
          const profile = await authService.getCurrentUser();
          setUser(profile);
          return true;
        }
        setError('Login failed');
        return false;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Login failed';
        setError(message);
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const register = useCallback(
    async (data: RegisterRequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await authService.register(data);
        if (result) {
          const profile = await authService.getCurrentUser();
          setUser(profile);
          return true;
        }
        setError('Registration failed');
        return false;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Registration failed';
        setError(message);
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const logout = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await authService.logout();
      setUser(null);
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Logout failed';
      setError(message);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      if (authService.isAuthenticated()) {
        const profile = await authService.getCurrentUser();
        setUser(profile);
        return true;
      }
      return false;
    } catch (err) {
      console.error('Auth check failed:', err);
      return false;
    }
  }, []);

  return {
    user,
    isLoading,
    error,
    login,
    register,
    logout,
    checkAuth,
    isAuthenticated: !!user,
  };
}
