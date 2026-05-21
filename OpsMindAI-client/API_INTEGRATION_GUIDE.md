# Frontend API Integration Guide

## Overview

This guide explains how to use the API services to connect your frontend components to the backend APIs.

## Structure

```
src/
├── lib/
│   ├── api-client.ts          # Core HTTP client
│   ├── api-types.ts           # TypeScript interfaces for all API responses
│   ├── api-utils.ts           # Utility functions for API operations
│   ├── services/              # Service modules for different API domains
│   │   ├── auth-service.ts    # Authentication endpoints
│   │   ├── projects-service.ts # Project management endpoints
│   │   ├── sre-service.ts     # SRE/Incidents endpoints
│   │   ├── testing-service.ts # Testing agent endpoints
│   │   ├── users-service.ts   # User management endpoints
│   │   └── index.ts           # Export all services
│   └── hooks/                 # Custom React hooks
│       ├── use-auth.ts        # Authentication hook
│       ├── use-projects.ts    # Projects hook
│       ├── use-sre.ts         # SRE hook
│       ├── use-testing.ts     # Testing hook
│       └── index.ts           # Export all hooks
```

## Configuration

Set the backend API URL in `.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

For production, update to your deployment URL:

```env
NEXT_PUBLIC_API_BASE_URL=https://api.opsmindai.com/api/v1
```

## Usage Examples

### 1. Authentication

#### Using the Hook (Recommended)

```typescript
'use client';

import { useAuth } from '@/lib/hooks';

export default function LoginPage() {
  const { user, isLoading, error, login, logout } = useAuth();

  const handleLogin = async () => {
    const success = await login({
      email: 'user@example.com',
      password: 'password123',
    });

    if (success) {
      // Redirect to dashboard
    }
  };

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  if (user) {
    return (
      <div>
        <p>Logged in as: {user.email}</p>
        <button onClick={logout}>Logout</button>
      </div>
    );
  }

  return <button onClick={handleLogin}>Login</button>;
}
```

#### Using the Service Directly

```typescript
import { authService } from '@/lib/services';

const token = await authService.login({
  email: 'user@example.com',
  password: 'password123',
});

if (token) {
  console.log('Logged in!');
}
```

### 2. Project Management

```typescript
'use client';

import { useProjects } from '@/lib/hooks';

export default function ProjectsPage() {
  const { projects, isLoading, createProject, listProjects } = useProjects();

  React.useEffect(() => {
    listProjects();
  }, [listProjects]);

  const handleCreateProject = async () => {
    await createProject({
      name: 'My Project',
      prompt: 'Create a full-stack e-commerce platform',
      constraints: {
        frontend_framework: 'next',
        backend_framework: 'fastapi',
        database: 'postgresql',
      },
    });

    await listProjects(); // Refresh list
  };

  return (
    <div>
      <button onClick={handleCreateProject}>Create Project</button>
      {projects.map((project) => (
        <div key={project.project_id}>
          <h3>{project.name}</h3>
          <p>Status: {project.status}</p>
        </div>
      ))}
    </div>
  );
}
```

### 3. SRE / Incident Management

```typescript
'use client';

import { useSRE } from '@/lib/hooks';
import { AlertSource, IncidentSeverity } from '@/lib/api-types';

export default function IncidentsPage() {
  const { incident, ingestAlert, triggerRCA, getIncident } = useSRE();

  const handleIngestAlert = async () => {
    const result = await ingestAlert({
      source: AlertSource.PROMETHEUS,
      service: 'api-server',
      severity: IncidentSeverity.HIGH,
      alert_name: 'HighLatency',
      labels: {
        instance: 'api-1',
        region: 'us-east-1',
      },
    });

    if (result?.incident_id) {
      // Poll for incident details
      await getIncident(result.incident_id);
    }
  };

  return (
    <div>
      <button onClick={handleIngestAlert}>Report Alert</button>
      {incident && (
        <div>
          <h3>{incident.alert_name}</h3>
          <p>Status: {incident.status}</p>
          <p>RCA: {incident.rca_result?.root_cause}</p>
        </div>
      )}
    </div>
  );
}
```

### 4. Testing Agent

```typescript
'use client';

import { useTesting } from '@/lib/hooks';

export default function TestingPage() {
  const { generateTests, pollJobStatus } = useTesting();

  const handleGenerateTests = async () => {
    const result = await generateTests({
      repo_url: 'https://github.com/user/repo',
      branch: 'main',
      framework: 'pytest',
      coverage_threshold: 0.80,
    });

    if (result?.job_id) {
      // Wait for job completion
      const finalStatus = await pollJobStatus(result.job_id);
      console.log('Tests generated:', finalStatus);
    }
  };

  return <button onClick={handleGenerateTests}>Generate Tests</button>;
}
```

## Error Handling

All service methods return `null` on error. Use the hooks for automatic error handling:

```typescript
const { error, isLoading } = useSRE();

if (error) {
  // Display error message
  <ErrorAlert message={error} />;
}

if (isLoading) {
  // Show loading indicator
  <LoadingSpinner />;
}
```

Or use utility functions:

```typescript
import { getErrorMessage } from '@/lib/api-utils';

try {
  const result = await authService.login(credentials);
} catch (error) {
  const message = getErrorMessage(error);
  showToast(message, 'error');
}
```

## Authentication

The API client automatically includes the auth token from localStorage. When you login:

```typescript
const result = await authService.login(credentials);
// Token is automatically stored in localStorage
// All subsequent requests will include the Bearer token
```

For manual token management:

```typescript
import { authService } from '@/lib/services';

// Set token manually
authService.setToken('your-token');

// Get current token
const token = authService.getToken();

// Check if authenticated
if (authService.isAuthenticated()) {
  // User is logged in
}

// Clear authentication
authService.clearAuth();
```

## API Client Direct Usage

For advanced use cases, use the API client directly:

```typescript
import { apiClient } from '@/lib/api-client';

// GET
const { data, error, status } = await apiClient.get('/projects');

// POST
const { data, error } = await apiClient.post('/projects', {
  name: 'My Project',
  prompt: 'Create a project',
});

// PATCH
const { data, error } = await apiClient.patch('/projects/123', {
  name: 'Updated Name',
});

// DELETE
const { error } = await apiClient.delete('/projects/123');
```

## Polling for Long-Running Operations

Several endpoints return job IDs that require polling:

```typescript
const { pollJobStatus } = useSRE();

const result = await ingestAlert(alertData);
if (result?.job_id) {
  // Poll until job is complete
  const finalStatus = await pollJobStatus(result.job_id);
  console.log(finalStatus.status); // 'completed', 'failed', or 'error'
}
```

## WebSocket Support (Future)

For real-time updates on long-running operations, watch for WebSocket support:

```typescript
// Coming soon: WebSocket client for real-time job status updates
const ws = new WebSocketClient('/api/v1/jobs/123/stream');
```

## Type Safety

All responses are fully typed with TypeScript. Use the types for better IDE autocomplete:

```typescript
import type { ProjectResponse, IncidentDetail } from '@/lib/api-types';

const project: ProjectResponse = await projectsService.getProject('123');
const incident: IncidentDetail = await sreService.getIncident('456');
```

## Testing

For testing API calls, mock the services:

```typescript
// Mock in your test setup
jest.mock('@/lib/services', () => ({
  authService: {
    login: jest.fn().mockResolvedValue({
      access_token: 'mock-token',
      user_id: 'mock-user',
    }),
  },
}));

// Use in tests
test('login works', async () => {
  const result = await authService.login(credentials);
  expect(result.access_token).toBe('mock-token');
});
```

## Environment Variables

Supported environment variables:

```env
# API Configuration
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

# For authentication/Clerk (if used)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your-key
```

## Troubleshooting

### 401 Unauthorized

- Check if token is stored in localStorage
- Verify token hasn't expired
- Re-login if needed

### CORS Errors

- Ensure backend CORS middleware is configured
- Check `Access-Control-Allow-Origin` headers
- Verify `credentials: 'include'` in API client

### API Timeouts

- Increase timeout in `.env.local`
- Use polling for long-running operations
- Check backend health

### Network Errors

- Use `isNetworkError()` utility to detect network issues
- Implement retry logic with `retryWithBackoff()`

## Contributing

When adding new API endpoints:

1. Add types to `api-types.ts`
2. Create service methods in appropriate service file
3. Add hooks to corresponding hook file
4. Update this guide with usage examples
