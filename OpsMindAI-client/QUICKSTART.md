# Quick Start: Frontend API Integration

## What's Been Set Up

I've connected all your backend APIs to the frontend with:

✅ **API Client** - Centralized HTTP client for all requests  
✅ **Service Modules** - Organized services for each API domain  
✅ **TypeScript Types** - Full type safety for all API responses  
✅ **React Hooks** - Custom hooks for state management and API calls  
✅ **Example Components** - Working examples of API integration  
✅ **Utilities** - Helper functions for common API operations  

## File Structure

```
frontend/ops_mindai/src/lib/
├── api-client.ts           # Core HTTP client with auth support
├── api-types.ts            # All TypeScript interfaces
├── api-utils.ts            # Utility functions (formatting, error handling, retry logic)
├── services/               # API service modules
│   ├── auth-service.ts     # Login, register, auth management
│   ├── projects-service.ts # Project CRUD operations
│   ├── sre-service.ts      # Incident response, RCA, remediation
│   ├── testing-service.ts  # Test generation, coverage, regression
│   ├── users-service.ts    # User management
│   └── index.ts
└── hooks/                  # Custom React hooks
    ├── use-auth.ts         # Auth operations with state
    ├── use-projects.ts     # Project operations with state
    ├── use-sre.ts          # SRE operations with state
    ├── use-testing.ts      # Testing operations with state
    └── index.ts

src/components/examples/    # Example implementations
├── login-example.tsx
├── projects-list-example.tsx
├── incident-response-example.tsx
├── testing-agent-example.tsx
└── index.ts
```

## Available API Endpoints

### Authentication (`/auth`)
- `POST /register` - Register new user
- `POST /login` - User login
- `POST /logout` - User logout
- `POST /set-cookie` - Set auth cookie (Clerk)
- `POST /clear-cookie` - Clear auth cookie
- `GET /me` - Get current user profile

### Projects (`/projects`)
- `POST /` - Create project
- `GET /` - List projects
- `GET /{id}` - Get project details
- `PATCH /{id}` - Update project
- `DELETE /{id}` - Delete project
- `GET /{id}/files` - List project files
- `GET /{id}/diff` - Get build diff

### SRE/Incidents (`/agents/sre`)
- `POST /ingest` - Report alert
- `POST /rca` - Trigger root cause analysis
- `POST /remediate` - Execute remediation
- `GET /jobs/{id}` - Get job status
- `GET /incidents/{id}` - Get incident details
- `GET /history` - List incident history

### Testing (`/agents/testing`)
- `POST /generate` - Generate test stubs
- `POST /suite` - Run test suite
- `POST /regression` - Build regression suite
- `GET /jobs/{id}` - Get job status
- `GET /history` - List testing history

### Users (`/users`)
- `GET /` - List users
- `GET /me` - Get current user
- `GET /{id}` - Get user details
- `PATCH /{id}` - Update user
- `DELETE /{id}` - Delete user

## Getting Started

### 1. Start Your Backend Server

```bash
cd backend
python -m uvicorn opsmindai.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000/api/v1`

### 2. Update Frontend Environment

Edit `.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

### 3. Import and Use in Your Components

```typescript
'use client';

import { useAuth } from '@/lib/hooks';

export default function MyComponent() {
  const { user, login, logout, isLoading, error } = useAuth();

  // Use the hook methods in your component
}
```

### 4. Choose Your Integration Method

#### Option A: Using Hooks (Recommended)

```typescript
import { useAuth, useProjects, useSRE, useTesting } from '@/lib/hooks';

export default function Dashboard() {
  const { user } = useAuth();
  const { projects } = useProjects();
  const { incident } = useSRE();
  
  // Use these in JSX
}
```

#### Option B: Using Services Directly

```typescript
import { authService, projectsService, sreService } from '@/lib/services';

async function loadData() {
  const projects = await projectsService.listProjects();
  const incident = await sreService.getIncident('id');
}
```

#### Option C: Using API Client Directly

```typescript
import { apiClient } from '@/lib/api-client';

const { data, error } = await apiClient.get('/projects');
const { data, error } = await apiClient.post('/incidents', payload);
```

## Common Tasks

### Authenticate User

```typescript
const { login } = useAuth();

await login({
  email: 'user@example.com',
  password: 'password123',
});
```

### Create a Project

```typescript
const { createProject } = useProjects();

await createProject({
  name: 'E-Commerce Platform',
  prompt: 'Build a full-stack e-commerce platform',
  constraints: {
    frontend_framework: 'next',
    backend_framework: 'fastapi',
  },
});
```

### Handle an Incident

```typescript
const { ingestAlert, triggerRCA, triggerRemediation } = useSRE();

// Report alert
const { job_id, incident_id } = await ingestAlert({
  source: 'prometheus',
  service: 'api-server',
  severity: 'high',
  alert_name: 'HighLatency',
});

// Trigger analysis
await triggerRCA({ incident_id });

// Execute remediation
await triggerRemediation({ incident_id, playbook: 'auto' });
```

### Generate Tests

```typescript
const { generateTests, pollJobStatus } = useTesting();

const { job_id } = await generateTests({
  repo_url: 'https://github.com/user/repo',
  framework: 'pytest',
  coverage_threshold: 0.80,
});

// Wait for job to complete
const status = await pollJobStatus(job_id);
console.log(status.coverage); // Coverage report
```

## Error Handling

All hooks provide `error` and `isLoading` states:

```typescript
const { data, error, isLoading } = useSRE();

if (isLoading) return <Spinner />;
if (error) return <Error message={error} />;
return <IncidentDetail incident={data} />;
```

Use utility functions for error messages:

```typescript
import { getErrorMessage } from '@/lib/api-utils';

const message = getErrorMessage(apiError);
showToast(message);
```

## CORS & Authentication

✅ **CORS is configured** - The backend already has CORS middleware  
✅ **Cookie-based auth** - Auth tokens are automatically included  
✅ **Bearer token support** - Also works with Authorization header  

## Testing

Example test setup with mocked services:

```typescript
jest.mock('@/lib/services', () => ({
  projectsService: {
    listProjects: jest.fn().mockResolvedValue({
      projects: [{ project_id: '1', name: 'Test' }],
    }),
  },
}));

test('loads projects', async () => {
  render(<ProjectsList />);
  await waitFor(() => {
    expect(screen.getByText('Test')).toBeInTheDocument();
  });
});
```

## Next Steps

1. **Review Example Components** - Check `src/components/examples/` for working implementations
2. **Read Full Guide** - See `API_INTEGRATION_GUIDE.md` for detailed documentation
3. **Build Your Components** - Start integrating the hooks into your UI components
4. **Test Locally** - Run both frontend and backend servers and test the APIs
5. **Deploy** - Update `NEXT_PUBLIC_API_BASE_URL` for production

## Configuration for Different Environments

### Development
```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

### Staging
```env
NEXT_PUBLIC_API_BASE_URL=https://api-staging.opsmindai.com/api/v1
```

### Production
```env
NEXT_PUBLIC_API_BASE_URL=https://api.opsmindai.com/api/v1
```

## Troubleshooting

### 404 Errors
- Check backend is running on correct port
- Verify endpoint paths match your API
- Check `NEXT_PUBLIC_API_BASE_URL` is correct

### 401 Unauthorized
- User needs to login first
- Token might be expired - re-login
- Check browser localStorage for `auth_token`

### CORS Errors
- Backend CORS middleware handles this
- Should work automatically
- Check browser console for details

### Connection Refused
- Backend server not running
- Start with: `python -m uvicorn opsmindai.main:app --reload`
- Check port 8000 is accessible

## Support

For issues or questions:
1. Check `API_INTEGRATION_GUIDE.md` for detailed docs
2. Review example components in `src/components/examples/`
3. Check backend logs: `python -m uvicorn opsmindai.main:app --reload --log-level debug`
4. Verify browser network tab shows correct API calls

Happy coding! 🚀
