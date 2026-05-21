/**
 * Complete API & Services Export Reference
 * Use this file as a reference for what's available and how to import
 */

// ==================== API Client ====================
// import { apiClient } from '@/lib/api-client';
// const { data, error } = await apiClient.get('/endpoint');
// const { data, error } = await apiClient.post('/endpoint', payload);

// ==================== Services ====================

// Authentication Service
// import { authService } from '@/lib/services';
// - authService.register(data)
// - authService.login(credentials)
// - authService.logout()
// - authService.getCurrentUser()
// - authService.setToken(token)
// - authService.getToken()
// - authService.isAuthenticated()
// - authService.clearAuth()

// Projects Service
// import { projectsService } from '@/lib/services';
// - projectsService.createProject(data)
// - projectsService.listProjects(page, pageSize)
// - projectsService.getProject(projectId)
// - projectsService.updateProject(projectId, data)
// - projectsService.deleteProject(projectId)
// - projectsService.getProjectFiles(projectId)
// - projectsService.getProjectDiff(projectId, from, to)

// SRE Service
// import { sreService } from '@/lib/services';
// - sreService.ingestAlert(alertData)
// - sreService.triggerRCA(incidentData)
// - sreService.triggerRemediation(remediationData)
// - sreService.getJobStatus(jobId)
// - sreService.getIncident(incidentId)
// - sreService.getHistory(page, limit)
// - sreService.pollJobStatus(jobId, maxAttempts, intervalMs)

// Testing Service
// import { testingService } from '@/lib/services';
// - testingService.generateTests(config)
// - testingService.runTestSuite(config)
// - testingService.buildRegressionSuite(config)
// - testingService.getJobStatus(jobId)
// - testingService.getHistory(page, limit)
// - testingService.pollJobStatus(jobId, maxAttempts, intervalMs)

// Users Service
// import { usersService } from '@/lib/services';
// - usersService.listUsers(page, pageSize)
// - usersService.getUser(userId)
// - usersService.getCurrentUser()
// - usersService.updateUser(userId, data)
// - usersService.deleteUser(userId)

// ==================== React Hooks ====================

// useAuth Hook
// import { useAuth } from '@/lib/hooks';
// const { user, isLoading, error, login, register, logout, checkAuth, isAuthenticated } = useAuth();

// useProjects Hook
// import { useProjects } from '@/lib/hooks';
// const { projects, currentProject, isLoading, error, createProject, listProjects, getProject, updateProject, deleteProject } = useProjects();

// useSRE Hook
// import { useSRE } from '@/lib/hooks';
// const { incident, isLoading, error, ingestAlert, triggerRCA, triggerRemediation, getIncident, pollJobStatus } = useSRE();

// useTesting Hook
// import { useTesting } from '@/lib/hooks';
// const { jobStatus, isLoading, error, generateTests, runTestSuite, buildRegressionSuite, getJobStatus, pollJobStatus } = useTesting();

// ==================== Types ====================

// import type {
//   // Auth
//   RegisterRequest, LoginRequest, TokenResponse, RegisterResponse, UserProfile,
//   // Projects
//   CreateProjectRequest, CreateProjectResponse, ProjectResponse, ProjectListResponse,
//   UpdateProjectRequest, FileListResponse, DiffResponse,
//   // SRE
//   AlertSource, IncidentSeverity, IncidentStatus, Playbook,
//   AlertPayload, IngestRequest, RCARequest, RemediateRequest,
//   JobSubmitResponse, JobStatusResponse, TimelineEvent, IncidentDetail, IncidentHistory,
//   // Testing
//   GenerateTestRequest, SuiteRequest, RegressionRequest,
//   GeneratedFileSummary, CoverageBreakdown, TestingJobStatus, TestingHistory,
//   // Users
//   UserResponse, UserListResponse,
// } from '@/lib/api-types';

// ==================== Utility Functions ====================

// import {
//   getErrorMessage,        // Get readable error message from API error
//   buildQueryString,       // Build query string from object
//   formatDuration,         // Format duration in seconds to readable string
//   formatDate,             // Format date string to readable date
//   formatRelativeTime,     // Format date as relative time (e.g., "2 hours ago")
//   retryWithBackoff,       // Retry failed API calls with exponential backoff
//   isApiSuccess,          // Check if response status is successful
//   isNetworkError,        // Check if error is network-related
// } from '@/lib/api-utils';

// ==================== Example Usage ====================

/*
// 1. Import hook
import { useAuth } from '@/lib/hooks';

// 2. Use in component
export default function LoginPage() {
  const { user, isLoading, error, login } = useAuth();

  const handleLogin = async () => {
    const success = await login({ email: 'user@example.com', password: 'pass' });
    if (success) {
      // Redirect or update UI
    }
  };

  return (
    <div>
      {error && <p>Error: {error}</p>}
      <button onClick={handleLogin} disabled={isLoading}>
        {isLoading ? 'Logging in...' : 'Login'}
      </button>
      {user && <p>Logged in as: {user.email}</p>}
    </div>
  );
}
*/

// ==================== Enums ====================

/*
AlertSource {
  PROMETHEUS = 'prometheus',
  GRAFANA = 'grafana',
  DATADOG = 'datadog',
  NEW_RELIC = 'newrelic',
  CLOUDWATCH = 'cloudwatch',
}

IncidentSeverity {
  CRITICAL = 'critical',
  HIGH = 'high',
  MEDIUM = 'medium',
  LOW = 'low',
  INFO = 'info',
}

IncidentStatus {
  OPEN = 'open',
  IN_PROGRESS = 'in_progress',
  RESOLVED = 'resolved',
  ACKNOWLEDGED = 'acknowledged',
  ESCALATED = 'escalated',
  CLOSED = 'closed',
}

Playbook {
  AUTO = 'auto',
  MANUAL = 'manual',
  ESCALATE = 'escalate',
}
*/

// ==================== Common Patterns ====================

/*
// Pattern 1: Using hooks with effects
import { useEffect } from 'react';
import { useProjects } from '@/lib/hooks';

export default function Projects() {
  const { projects, listProjects } = useProjects();

  useEffect(() => {
    listProjects();
  }, [listProjects]);

  return projects.map(p => <div key={p.project_id}>{p.name}</div>);
}

// Pattern 2: Handling async operations with loading state
const { createProject, isLoading, error } = useProjects();

const handleCreate = async () => {
  const result = await createProject({ name: 'New Project', prompt: '...' });
  if (result) {
    console.log('Created:', result.project_id);
  }
};

// Pattern 3: Polling for long-running operations
const { pollJobStatus } = useSRE();

const result = await ingestAlert(alertData);
if (result?.job_id) {
  const finalStatus = await pollJobStatus(result.job_id);
  console.log(finalStatus.status); // 'completed', 'failed', or 'error'
}

// Pattern 4: Error handling with utility
import { getErrorMessage } from '@/lib/api-utils';

try {
  await projectsService.createProject(data);
} catch (error) {
  const message = getErrorMessage(error);
  showErrorToast(message);
}
*/

// ==================== Environment Variables ====================

/*
In .env.local:

# Required
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

# Optional - for Clerk authentication
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your_key
*/

// ==================== Files Created ====================

/*
✓ /src/lib/api-client.ts                  - HTTP client
✓ /src/lib/api-types.ts                   - TypeScript types
✓ /src/lib/api-utils.ts                   - Utility functions
✓ /src/lib/services/auth-service.ts       - Auth service
✓ /src/lib/services/projects-service.ts   - Projects service
✓ /src/lib/services/sre-service.ts        - SRE service
✓ /src/lib/services/testing-service.ts    - Testing service
✓ /src/lib/services/users-service.ts      - Users service
✓ /src/lib/services/index.ts              - Services export
✓ /src/lib/hooks/use-auth.ts              - Auth hook
✓ /src/lib/hooks/use-projects.ts          - Projects hook
✓ /src/lib/hooks/use-sre.ts               - SRE hook
✓ /src/lib/hooks/use-testing.ts           - Testing hook
✓ /src/lib/hooks/index.ts                 - Hooks export
✓ /src/components/examples/                - Example components
✓ /.env.local                             - Environment config
✓ /QUICKSTART.md                          - Quick start guide
✓ /API_INTEGRATION_GUIDE.md               - Full documentation
*/

export {};
