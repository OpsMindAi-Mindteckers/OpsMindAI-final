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

  const testEndpoint = async (endpoint: string) => {
    const startTime = Date.now();
    try {
      const response = await apiClient.get(endpoint);
      const responseTime = Date.now() - startTime;

      return {
        endpoint,
        status: response.error ? 'error' : 'success',
        statusCode: response.status,
        message: response.error ? `Error: ${JSON.stringify(response.error)}` : 'Connected successfully',
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

    const endpoints = [
      '/auth/me',
      '/projects',
      '/agents/sre/history',
      '/agents/testing/history',
      '/users',
    ];

    const testPromises = endpoints.map((endpoint) =>
      testEndpoint(endpoint).then((result) => {
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
        <button
          onClick={handleTestConnection}
          disabled={isTesting}
          style={{
            padding: '10px 20px',
            fontSize: '16px',
            backgroundColor: isTesting ? '#ccc' : '#4CAF50',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: isTesting ? 'not-allowed' : 'pointer',
          }}
        >
          {isTesting ? 'Testing...' : 'Test Connection'}
        </button>
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
              <p>
                ✗ <strong>Some APIs are not connected.</strong> Check that:
                <ul>
                  <li>Backend server is running on http://localhost:8000</li>
                  <li>.env.local has correct NEXT_PUBLIC_API_BASE_URL</li>
                  <li>Backend is properly initialized (database, Redis, etc.)</li>
                  <li>Check browser console (F12) for CORS or network errors</li>
                </ul>
              </p>
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
