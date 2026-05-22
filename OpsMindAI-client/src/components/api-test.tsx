/**
 * API Connection Test Component
 * This component tests if the frontend can successfully connect to the backend APIs
 */

'use client';

import { useState } from 'react';
import { apiClient } from '@/lib/api-client';

interface TestResult {
  endpoint: string;
  status: 'pending' | 'success' | 'error';
  statusCode?: number;
  message: string;
  responseTime: number;
}

export default function ApiConnectionTest() {
  const [results, setResults] = useState<TestResult[]>([]);
  const [isTesting, setIsTesting] = useState(false);
  const [testToken, setTestToken] = useState<string | null>(null);
  const [tokenError, setTokenError] = useState<string | null>(null);

  const getTestToken = async () => {
    setTokenError(null);
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';
      const response = await fetch(`${baseUrl}/auth/test-token`);
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(`Failed to get test token: ${data.detail || data.message}`);
      }
      
      setTestToken(data.access_token);
      localStorage.setItem('auth_token', data.access_token);
      return data.access_token;
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      setTokenError(errorMsg);
      console.error('Failed to get test token:', errorMsg);
      return null;
    }
  };

  const testEndpoint = async (endpoint: string, token: string | null) => {
    const startTime = Date.now();
    try {
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';
      const response = await fetch(`${baseUrl}${endpoint}`, {
        headers,
        credentials: 'include',
      });
      
      const responseTime = Date.now() - startTime;
      const data = await response.json().catch(() => ({}));

      return {
        endpoint,
        status: response.ok ? 'success' : 'error',
        statusCode: response.status,
        message: response.ok ? 'Connected successfully' : `Error: ${JSON.stringify(data)}`,
        responseTime,
      };
    } catch (error) {
      const responseTime = Date.now() - startTime;
      return {
        endpoint,
        status: 'error',
        message: `Exception: ${error instanceof Error ? error.message : String(error)}`,
        responseTime,
      };
    }
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    setResults([]);

    // First, get a test token
    const token = await getTestToken();
    if (!token) {
      setIsTesting(false);
      return;
    }

    const endpoints = [
      '/users/me',
      '/projects',
      '/agents/sre/history',
      '/agents/testing/history',
      '/users',
    ];

    const testPromises = endpoints.map((endpoint) =>
      testEndpoint(endpoint, token).then((result) => {
        setResults((prev) => [...prev, result]);
        return result;
      })
    );

    await Promise.all(testPromises);
    setIsTesting(false);
  };

  const successCount = results.filter((r) => r.status === 'success').length;
  const errorCount = results.filter((r) => r.status === 'error').length;

  return (
    <div
      style={{
        padding: '20px',
        fontFamily: 'monospace',
        backgroundColor: '#f5f5f5',
        borderRadius: '8px',
        minHeight: '400px',
      }}
    >
      <h1>API Connection Test</h1>

      <div style={{ marginBottom: '20px' }}>
        <p>
          <strong>Backend URL:</strong> {process.env.NEXT_PUBLIC_API_BASE_URL}
        </p>
        
        {/* Token Status */}
        <div style={{ marginBottom: '15px', padding: '10px', backgroundColor: testToken ? '#d4edda' : '#fff3cd', borderRadius: '4px', border: '1px solid #ccc' }}>
          <p>
            <strong>Test Token Status:</strong>{' '}
            {testToken ? (
              <span style={{ color: 'green' }}>✅ Active</span>
            ) : (
              <span style={{ color: 'orange' }}>⏳ Not yet fetched</span>
            )}
          </p>
          {tokenError && (
            <p style={{ color: 'red', margin: '5px 0 0 0' }}>
              ⚠️ Token Error: {tokenError}
            </p>
          )}
        </div>

        {/* Buttons */}
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={getTestToken}
            disabled={isTesting}
            style={{
              padding: '10px 20px',
              fontSize: '16px',
              backgroundColor: isTesting ? '#ccc' : '#2196F3',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: isTesting ? 'not-allowed' : 'pointer',
            }}
          >
            {testToken ? 'Refresh Token' : 'Get Test Token'}
          </button>

          <button
            onClick={handleTestConnection}
            disabled={isTesting || !testToken}
            style={{
              padding: '10px 20px',
              fontSize: '16px',
              backgroundColor: isTesting || !testToken ? '#ccc' : '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: isTesting || !testToken ? 'not-allowed' : 'pointer',
            }}
          >
            {isTesting ? 'Testing...' : 'Test All Endpoints'}
          </button>
        </div>
      </div>

      {results.length > 0 && (
        <div>
          <h2>Results</h2>
          <p>
            <strong>Summary:</strong> {successCount} passed, {errorCount} failed
          </p>

          <div style={{ marginTop: '20px' }}>
            {results.map((result, index) => (
              <div
                key={index}
                style={{
                  padding: '15px',
                  marginBottom: '10px',
                  backgroundColor: result.status === 'success' ? '#e8f5e9' : '#ffebee',
                  border: `2px solid ${result.status === 'success' ? '#4CAF50' : '#f44336'}`,
                  borderRadius: '4px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <div>
                    <strong>{result.endpoint}</strong>
                    <p style={{ margin: '5px 0', fontSize: '12px' }}>
                      Status: {result.statusCode || 'N/A'} | Time: {result.responseTime}ms
                    </p>
                    <p style={{ margin: '5px 0', color: result.status === 'success' ? '#4CAF50' : '#f44336' }}>
                      {result.status === 'success' ? '✓' : '✗'} {result.message}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div
            style={{
              marginTop: '20px',
              padding: '15px',
              backgroundColor: '#fff3cd',
              borderRadius: '4px',
            }}
          >
            <h3>What This Means:</h3>
            {successCount === 5 ? (
              <p>
                ✓ <strong>All APIs are connected!</strong> Your frontend can successfully reach the backend
                server. You're ready to use all the API services in your components.
              </p>
            ) : errorCount > 0 ? (
              <div>
                ✗ <strong>Some APIs are not connected.</strong> Check that:
                <ul>
                  <li>Backend server is running on http://localhost:8000</li>
                  <li>.env.local has correct NEXT_PUBLIC_API_BASE_URL</li>
                  <li>Backend is properly initialized (database, Redis, etc.)</li>
                  <li>Check browser console (F12) for CORS or network errors</li>
                </ul>
              </div>
            ) : (
              <p>Click "Test Connection" to check if APIs are connected.</p>
            )}
          </div>
        </div>
      )}

      <div style={{ marginTop: '30px', padding: '15px', backgroundColor: '#e3f2fd', borderRadius: '4px' }}>
        <h3>Next Steps:</h3>
        <ol>
          <li>Make sure both servers are running (backend on 8000, frontend on 3000/3001)</li>
          <li>Click "Test Connection" button above</li>
          <li>Check if all endpoints return success</li>
          <li>If tests pass, use the API services in your components</li>
          <li>If tests fail, check the error messages and troubleshoot</li>
        </ol>
      </div>
    </div>
  );
}
