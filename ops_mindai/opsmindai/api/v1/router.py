"""
OpsMindAI API v1 Router
Main router that mounts all v1 sub-routers (auth, projects, jobs, agents, templates, health, etc.)
Prefix: /api/v1
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Header, WebSocket, status
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field
import uuid
from datetime import datetime

# ================================
# 1. REQUEST/RESPONSE MODELS
# ================================

# ---- Authentication Models ----
class RegisterRequest(BaseModel):
    """User registration request"""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    full_name: str

class LoginRequest(BaseModel):
    """User login request"""
    email: EmailStr
    password: str

class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str

class CreateAPIKeyRequest(BaseModel):
    """Create API key request"""
    name: str

class ChangePasswordRequest(BaseModel):
    """Change password request"""
    current_password: str
    new_password: str = Field(..., min_length=8)

class DeleteAccountRequest(BaseModel):
    """Delete account request (requires confirmation)"""
    confirm: bool

# ---- Authentication Responses ----
class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class UserResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str = "user"
    is_active: bool
    created_at: datetime

class APIKeyResponse(BaseModel):
    key_id: str
    api_key: str
    name: str
    created_at: datetime
    expires_at: datetime

class APIKeyListItem(BaseModel):
    key_id: str
    name: str
    prefix: str
    created_at: datetime
    expires_at: datetime

class UsageResponse(BaseModel):
    total_projects: int
    total_jobs: int
    total_tokens_used: int
    estimated_cost_usd: float
    this_month: Dict[str, Any]

# ---- Projects Models ----
class ConstraintsModel(BaseModel):
    frontend_framework: Optional[str] = None
    backend_framework: Optional[str] = None
    database: Optional[str] = None
    exclude_tech: Optional[List[str]] = None
    target_cloud: Optional[str] = None

class GitConfig(BaseModel):
    provider: str = "github"
    org_or_user: str
    repo_name: Optional[str] = None
    private: bool = True

class CreateProjectRequest(BaseModel):
    """Create project and trigger pipeline"""
    name: str
    prompt: str
    constraints: Optional[ConstraintsModel] = None
    git_config: Optional[GitConfig] = None
    template_id: Optional[str] = None

class UpdateProjectRequest(BaseModel):
    """Update project metadata"""
    name: Optional[str] = None
    git_config: Optional[GitConfig] = None

class ProjectResponse(BaseModel):
    project_id: str
    name: str
    prompt: str
    status: str
    repo_url: Optional[str] = None
    blueprint: Optional[Dict[str, Any]] = None
    jobs: List[Dict[str, Any]] = []
    agent_summary: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

class ProjectListResponse(BaseModel):
    items: List[ProjectResponse]
    total: int
    page: int
    limit: int

class FileItem(BaseModel):
    path: str
    size_bytes: int

class FilesListResponse(BaseModel):
    files: List[FileItem]
    total: int

class DiffResponse(BaseModel):
    changed_files: int
    diff: List[Dict[str, Any]]

# ---- Jobs Models ----
class JobResponse(BaseModel):
    job_id: str
    project_id: str
    status: str
    current_node: Optional[str] = None
    progress: Dict[str, Any] = {}
    started_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    revision_counts: Dict[str, int] = {}
    error: Optional[str] = None

class JobListResponse(BaseModel):
    items: List[JobResponse]
    total: int
    page: int
    limit: int

class JobLogsResponse(BaseModel):
    logs: List[Dict[str, Any]]
    next_cursor: Optional[str] = None

class AgentExecutionRecord(BaseModel):
    agent: str
    status: str
    tokens: int
    duration_s: int
    retries: int

class AgentListResponse(BaseModel):
    agents: List[AgentExecutionRecord]

class TestReport(BaseModel):
    passed: bool
    coverage_pct: float
    unit_pass_rate: float
    integration_pass_rate: float
    failed_checks: List[Dict[str, Any]] = []

class Artifact(BaseModel):
    artifact_id: str
    name: str
    size_bytes: int
    url: str

class ArtifactsResponse(BaseModel):
    artifacts: List[Artifact]

class CancelJobResponse(BaseModel):
    job_id: str
    status: str

# ---- Agents Models ----
class AgentConfig(BaseModel):
    name: str
    status: str
    model: str
    avg_tokens: int

class AgentDetailResponse(BaseModel):
    name: str
    model: str
    temperature: float
    max_tokens: int
    status: str

class AgentMetricsResponse(BaseModel):
    agent_name: str
    total_runs: int
    success_rate: float
    avg_duration_s: float
    avg_tokens_used: int
    revision_rate: float
    cost_usd_total: float
    cost_usd_avg: float
    last_run_at: datetime

class UpdateAgentConfigRequest(BaseModel):
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    model: Optional[str] = None

# ---- Templates Models ----
class TemplateResponse(BaseModel):
    template_id: str
    name: str
    domain: str
    scope: str
    description: Optional[str] = None

class TemplateListResponse(BaseModel):
    templates: List[TemplateResponse]

class CreateTemplateRequest(BaseModel):
    name: str
    project_id: str
    description: Optional[str] = None

class TemplateDetailResponse(BaseModel):
    template_id: str
    name: str
    blueprint: Dict[str, Any]

# ---- Health Models ----
class HealthResponse(BaseModel):
    status: str

class ReadyResponse(BaseModel):
    status: str
    checks: Dict[str, str]

class VersionResponse(BaseModel):
    version: str
    git_sha: str
    deployed_at: datetime

# ---- Responses Models ----
class CreateProjectResponse(BaseModel):
    project_id: str
    job_id: str
    status: str
    ws_url: str
    created_at: datetime

# ================================
# 2. ROUTER SETUP
# ================================

router = APIRouter(prefix="/api/v1", tags=["v1"])


# ================================
# 3. HELPER FUNCTIONS
# ================================

def verify_bearer_token(authorization: Optional[str] = Header(None)) -> str:
    """Verify Bearer token from Authorization header"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer token"
        )
    return authorization.split(" ")[1]

def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Verify API key from X-API-Key header"""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    return x_api_key

def get_token_or_key(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None)
) -> str:
    """Get either Bearer token or API key"""
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ")[1]
    if x_api_key:
        return x_api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication"
    )


# ================================
# GROUP 1: AUTHENTICATION ENDPOINTS (6 endpoints)
# ================================

@router.post("/auth/register", response_model=CreateProjectResponse, status_code=201, tags=["Authentication"])
async def register(request: RegisterRequest):
    """
    Register a new user account
    - Returns: user_id, access_token, refresh_token
    - Rate: 10/hour
    """
    user_id = str(uuid.uuid4())
    return {
        "user_id": user_id,
        "email": request.email,
        "access_token": "eyJhbGci...",
        "refresh_token": "eyJhbGci...",
        "token_type": "bearer",
        "expires_in": 3600
    }

@router.post("/auth/login", response_model=AuthTokenResponse, status_code=200, tags=["Authentication"])
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT pair
    - Rate: 20/hour
    """
    return {
        "access_token": "eyJhbGci...",
        "refresh_token": "eyJhbGci...",
        "token_type": "bearer",
        "expires_in": 3600
    }

@router.post("/auth/logout", status_code=204, tags=["Authentication"])
async def logout(authorization: str = Depends(verify_bearer_token)):
    """
    Invalidate current session / blacklist JWT
    - Auth: Bearer JWT
    - Rate: Unlimited
    """
    return None

@router.post("/auth/refresh", response_model=AuthTokenResponse, status_code=200, tags=["Authentication"])
async def refresh_token(request: RefreshTokenRequest):
    """
    Exchange refresh token for a new access token pair
    - Rate: 60/hour
    """
    return {
        "access_token": "eyJhbGci...",
        "refresh_token": "eyJhbGci...",
        "token_type": "bearer",
        "expires_in": 3600
    }

@router.post("/auth/api-key", response_model=APIKeyResponse, status_code=201, tags=["Authentication"])
async def create_api_key(
    request: CreateAPIKeyRequest,
    authorization: str = Depends(verify_bearer_token)
):
    """
    Generate a long-lived API key (shown once, stored hashed)
    - Auth: Bearer JWT
    - Rate: 5/day
    """
    return {
        "key_id": str(uuid.uuid4()),
        "api_key": "omindai_sk_live_xxxxxxxxxxxxxxxx",
        "name": request.name,
        "created_at": datetime.now(),
        "expires_at": datetime.now()
    }

@router.delete("/auth/api-key/{key_id}", status_code=204, tags=["Authentication"])
async def delete_api_key(
    key_id: str,
    authorization: str = Depends(verify_bearer_token)
):
    """
    Revoke and permanently delete an API key
    - Auth: Bearer JWT
    - Rate: 20/hour
    """
    return None


# ================================
# GROUP 2: USER ACCOUNT ENDPOINTS (6 endpoints)
# ================================

@router.get("/users/me", response_model=UserResponse, tags=["User Account"])
async def get_current_user(authorization: str = Depends(verify_bearer_token)):
    """
    Get current authenticated user's profile
    - Auth: Bearer JWT
    - Rate: 120/min
    """
    return {
        "user_id": str(uuid.uuid4()),
        "email": "user@example.com",
        "full_name": "John Doe",
        "role": "user",
        "is_active": True,
        "created_at": datetime.now()
    }

@router.patch("/users/me", response_model=UserResponse, tags=["User Account"])
async def update_user_profile(
    request: CreateProjectRequest,
    authorization: str = Depends(verify_bearer_token)
):
    """
    Update profile details (name, email)
    - Auth: Bearer JWT
    - Rate: 20/hour
    """
    return {
        "user_id": str(uuid.uuid4()),
        "email": "user@example.com",
        "full_name": "John Doe",
        "role": "user",
        "is_active": True,
        "created_at": datetime.now()
    }

@router.post("/users/me/change-password", status_code=200, tags=["User Account"])
async def change_password(
    request: ChangePasswordRequest,
    authorization: str = Depends(verify_bearer_token)
):
    """
    Change account password
    - Auth: Bearer JWT
    - Rate: 5/hour
    """
    return {"message": "Password updated"}

@router.delete("/users/me", status_code=204, tags=["User Account"])
async def delete_account(
    request: DeleteAccountRequest,
    authorization: str = Depends(verify_bearer_token)
):
    """
    Soft-delete account (is_active = false), cancels active jobs
    - Auth: Bearer JWT
    - Rate: 1/day
    """
    return None

@router.get("/users/me/api-keys", response_model=List[APIKeyListItem], tags=["User Account"])
async def list_api_keys(authorization: str = Depends(verify_bearer_token)):
    """
    List all API keys for the current user (values masked)
    - Auth: Bearer JWT
    - Rate: 60/min
    """
    return [
        {
            "key_id": str(uuid.uuid4()),
            "name": "CI Integration Key",
            "prefix": "omindai_sk_live_xxx...",
            "created_at": datetime.now(),
            "expires_at": datetime.now()
        }
    ]

@router.get("/users/me/usage", response_model=UsageResponse, tags=["User Account"])
async def get_usage_summary(authorization: str = Depends(verify_bearer_token)):
    """
    Usage summary — jobs, tokens, projects, estimated cost
    - Auth: Bearer JWT
    - Rate: 60/min
    """
    return {
        "total_projects": 5,
        "total_jobs": 12,
        "total_tokens_used": 450000,
        "estimated_cost_usd": 45.50,
        "this_month": {"projects": 2, "jobs": 5, "tokens": 200000, "cost": 20.00}
    }


# ================================
# GROUP 3: PROJECTS ENDPOINTS (9 endpoints)
# ================================

@router.get("/projects", response_model=ProjectListResponse, tags=["Projects"])
async def list_projects(
    auth: str = Depends(get_token_or_key),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None)
):
    """
    List all projects for the authenticated user
    - Auth: Bearer JWT / API Key
    - Rate: 120/min
    """
    return {
        "items": [],
        "total": 0,
        "page": page,
        "limit": limit
    }

@router.post("/projects", response_model=CreateProjectResponse, status_code=202, tags=["Projects"])
async def create_project(
    request: CreateProjectRequest,
    auth: str = Depends(get_token_or_key)
):
    """
    PRIMARY ENDPOINT — Trigger the full multi-agent build pipeline
    - Auth: Bearer JWT / API Key
    - Rate: 10/hour
    - Returns: project_id, job_id, status, ws_url
    """
    project_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    return {
        "project_id": project_id,
        "job_id": job_id,
        "status": "PENDING",
        "ws_url": f"wss://api.opsmindai.io/ws/{job_id}",
        "created_at": datetime.now()
    }

@router.get("/projects/{project_id}", response_model=ProjectResponse, tags=["Projects"])
async def get_project(
    project_id: str,
    auth: str = Depends(get_token_or_key)
):
    """
    Get full project details, job history, and per-agent summary
    - Auth: Bearer JWT / API Key
    - Rate: 120/min
    """
    return {
        "project_id": project_id,
        "name": "My E-Commerce App",
        "prompt": "Build a full-stack e-commerce platform...",
        "status": "COMPLETED",
        # dummy data
        "repo_url": "https://github.com/my-org/my-ecommerce-app", 
        "blueprint": {},
        "jobs": [],
        "agent_summary": {},
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }

@router.patch("/projects/{project_id}", response_model=ProjectResponse, tags=["Projects"])
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    auth: str = Depends(get_token_or_key)
):
    """
    Update mutable project metadata
    - Auth: Bearer JWT / API Key
    - Rate: 30/hour
    """
    return {
        "project_id": project_id,
        "name": request.name or "My Project",
        "prompt": "...",
        "status": "COMPLETED",
        "repo_url": None,
        "blueprint": None,
        "jobs": [],
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }

@router.delete("/projects/{project_id}", status_code=204, tags=["Projects"])
async def delete_project(
    project_id: str,
    auth: str = Depends(get_token_or_key)
):
    """
    Delete project and all associated jobs, logs, artifacts
    - Auth: Bearer JWT / API Key
    - Rate: 10/hour
    """
    return None

@router.get("/projects/{project_id}/files", response_model=FilesListResponse, tags=["Projects"])
async def list_project_files(
    project_id: str,
    auth: str = Depends(get_token_or_key)
):
    """
    List all generated files in the project output tree
    - Auth: Bearer JWT / API Key
    - Rate: 60/min
    """
    return {
        "files": [
            {"path": "frontend/src/App.tsx", "size_bytes": 2048},
            {"path": "backend/main.py", "size_bytes": 1024}
        ],
        "total": 2
    }

@router.get("/projects/{project_id}/files/{path:path}", tags=["Projects"])
async def get_project_file(
    project_id: str,
    path: str,
    auth: str = Depends(get_token_or_key)
):
    """
    Download or view content of a specific generated file
    - Auth: Bearer JWT / API Key
    - Rate: 60/min
    """
    return {"content": "file content here"}

@router.post("/projects/{project_id}/rebuild", response_model=CreateProjectResponse, status_code=202, tags=["Projects"])
async def rebuild_project(
    project_id: str,
    constraints: Optional[ConstraintsModel] = None,
    auth: str = Depends(get_token_or_key)
):
    """
    Trigger a full rebuild, optionally overriding constraints
    - Auth: Bearer JWT / API Key
    - Rate: 5/hour
    """
    job_id = str(uuid.uuid4())
    return {
        "project_id": project_id,
        "job_id": job_id,
        "status": "PENDING",
        "ws_url": f"wss://api.opsmindai.io/ws/{job_id}",
        "created_at": datetime.now()
    }

@router.get("/projects/{project_id}/diff", response_model=DiffResponse, tags=["Projects"])
async def get_project_diff(
    project_id: str,
    job_a: str = Query(...),
    job_b: str = Query(...),
    auth: str = Depends(get_token_or_key)
):
    """
    File-level diff between two builds of the same project
    - Auth: Bearer JWT / API Key
    - Rate: 30/hour
    """
    return {
        "changed_files": 5,
        "diff": []
    }


# ================================
# GROUP 4: JOBS ENDPOINTS (7 endpoints)
# ================================

@router.get("/jobs", response_model=JobListResponse, tags=["Jobs"])
async def list_jobs(
    auth: str = Depends(get_token_or_key),
    status: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    page: int = Query(1)
):
    """
    List all jobs for the current user
    - Auth: Bearer JWT / API Key
    - Rate: 120/min
    """
    return {
        "items": [],
        "total": 0,
        "page": page,
        "limit": limit
    }

@router.get("/jobs/{job_id}", response_model=JobResponse, tags=["Jobs"])
async def get_job_status(
    job_id: str,
    auth: str = Depends(get_token_or_key)
):
    """
    Get real-time job status, current pipeline node, progress
    - Auth: Bearer JWT / API Key
    - Rate: 120/min
    """
    return {
        "job_id": job_id,
        "project_id": str(uuid.uuid4()),
        "status": "RUNNING",
        "current_node": "testing_agent",
        "progress": {"total_nodes": 7, "completed_nodes": 5, "percent": 71},
        "started_at": datetime.now(),
        "duration_seconds": 98,
        "revision_counts": {"backend": 0, "frontend": 1, "database": 0},
        "error": None
    }

@router.get("/jobs/{job_id}/logs", response_model=JobLogsResponse, tags=["Jobs"])
async def get_job_logs(
    job_id: str,
    auth: str = Depends(get_token_or_key),
    agent: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(100, le=500)
):
    """
    Paginated structured execution logs from all agents
    - Auth: Bearer JWT / API Key
    - Rate: 60/min
    """
    return {
        "logs": [],
        "next_cursor": None
    }

@router.get("/jobs/{job_id}/agents", response_model=AgentListResponse, tags=["Jobs"])
async def get_job_agents(
    job_id: str,
    auth: str = Depends(get_token_or_key)
):
    """
    Per-agent execution records with timing, tokens, and retries
    - Auth: Bearer JWT / API Key
    - Rate: 60/min
    """
    return {
        "agents": [
            {"agent": "architecture", "status": "COMPLETED", "tokens": 4821, "duration_s": 18, "retries": 0},
            {"agent": "frontend", "status": "COMPLETED", "tokens": 12443, "duration_s": 34, "retries": 1},
            {"agent": "backend", "status": "COMPLETED", "tokens": 11200, "duration_s": 31, "retries": 0}
        ]
    }

@router.get("/jobs/{job_id}/test-report", response_model=TestReport, tags=["Jobs"])
async def get_test_report(
    job_id: str,
    auth: str = Depends(get_token_or_key)
):
    """
    Download full test report JSON from the Testing Agent
    - Auth: Bearer JWT / API Key
    - Rate: 60/min
    """
    return {
        "passed": True,
        "coverage_pct": 85.5,
        "unit_pass_rate": 0.95,
        "integration_pass_rate": 0.90,
        "failed_checks": []
    }

@router.post("/jobs/{job_id}/cancel", response_model=CancelJobResponse, tags=["Jobs"])
async def cancel_job(
    job_id: str,
    auth: str = Depends(get_token_or_key)
):
    """
    Cancel a running or pending job, terminate sandbox if active
    - Auth: Bearer JWT / API Key
    - Rate: 20/hour
    """
    return {
        "job_id": job_id,
        "status": "CANCELLED"
    }

@router.get("/jobs/{job_id}/artifacts", response_model=ArtifactsResponse, tags=["Jobs"])
async def get_job_artifacts(
    job_id: str,
    auth: str = Depends(get_token_or_key)
):
    """
    List downloadable build artifacts (zips, reports, results)
    - Auth: Bearer JWT / API Key
    - Rate: 60/min
    """
    return {
        "artifacts": [
            {"artifact_id": str(uuid.uuid4()), "name": "build.zip", "size_bytes": 5242880, "url": "https://..."},
            {"artifact_id": str(uuid.uuid4()), "name": "test-report.json", "size_bytes": 102400, "url": "https://..."}
        ]
    }


# ================================
# GROUP 5: AGENTS ENDPOINTS (4 endpoints)
# ================================

@router.get("/agents", response_model=List[AgentConfig], tags=["Agents"])
async def list_agents(authorization: str = Depends(verify_bearer_token)):
    """
    List all registered agents with current status and config
    - Auth: Bearer JWT
    - Rate: 60/min
    """
    return [
        {"name": "architecture", "status": "ready", "model": "gpt-4o", "avg_tokens": 4821},
        {"name": "frontend", "status": "ready", "model": "gpt-4o", "avg_tokens": 12443},
        {"name": "backend", "status": "ready", "model": "gpt-4o", "avg_tokens": 11200},
        {"name": "database", "status": "ready", "model": "gpt-4o", "avg_tokens": 3100},
        {"name": "testing", "status": "ready", "model": "gpt-4o", "avg_tokens": 5200}
    ]

@router.get("/agents/{agent_name}", response_model=AgentDetailResponse, tags=["Agents"])
async def get_agent_details(
    agent_name: str,
    authorization: str = Depends(verify_bearer_token)
):
    """
    Get configuration and runtime state of a specific agent
    - Auth: Bearer JWT
    - Rate: 60/min
    """
    return {
        "name": agent_name,
        "model": "gpt-4o",
        "temperature": 0.2,
        "max_tokens": 4096,
        "status": "ready"
    }

@router.get("/agents/{agent_name}/metrics", response_model=AgentMetricsResponse, tags=["Agents"])
async def get_agent_metrics(
    agent_name: str,
    authorization: str = Depends(verify_bearer_token)
):
    """
    Operational metrics — token usage, duration, success rate, cost
    - Auth: Bearer JWT
    - Rate: 60/min
    """
    return {
        "agent_name": agent_name,
        "total_runs": 1482,
        "success_rate": 0.93,
        "avg_duration_s": 31.4,
        "avg_tokens_used": 11200,
        "revision_rate": 0.12,
        "cost_usd_total": 284.20,
        "cost_usd_avg": 0.19,
        "last_run_at": datetime.now()
    }

@router.patch("/agents/{agent_name}/config", response_model=AgentDetailResponse, tags=["Agents"])
async def update_agent_config(
    agent_name: str,
    request: UpdateAgentConfigRequest,
    authorization: str = Depends(verify_bearer_token)
):
    """
    Update agent's prompt template or model parameters (Admin only)
    - Auth: Bearer JWT (Admin)
    - Rate: 10/hour
    """
    return {
        "name": agent_name,
        "model": request.model or "gpt-4o",
        "temperature": request.temperature or 0.2,
        "max_tokens": request.max_tokens or 4096,
        "status": "ready"
    }


# ================================
# GROUP 6: TEMPLATES ENDPOINTS (4 endpoints)
# ================================

@router.get("/templates", response_model=TemplateListResponse, tags=["Templates"])
async def list_templates(
    auth: str = Depends(get_token_or_key),
    scope: Optional[str] = Query(None),
    domain: Optional[str] = Query(None)
):
    """
    List all templates (system defaults + user custom)
    - Auth: Bearer JWT / API Key
    - Rate: 60/min
    """
    return {
        "templates": [
            {"template_id": str(uuid.uuid4()), "name": "E-Commerce Template", "domain": "ecommerce", "scope": "system"},
            {"template_id": str(uuid.uuid4()), "name": "SaaS Template", "domain": "saas", "scope": "system"}
        ]
    }

@router.post("/templates", response_model=TemplateResponse, status_code=201, tags=["Templates"])
async def create_template(
    request: CreateTemplateRequest,
    authorization: str = Depends(verify_bearer_token)
):
    """
    Create a reusable template from a completed project's blueprint
    - Auth: Bearer JWT
    - Rate: 10/hour
    """
    return {
        "template_id": str(uuid.uuid4()),
        "name": request.name,
        "domain": "custom",
        "scope": "custom",
        "description": request.description
    }

@router.get("/templates/{template_id}", response_model=TemplateDetailResponse, tags=["Templates"])
async def get_template(
    template_id: str,
    auth: str = Depends(get_token_or_key)
):
    """
    Get full template details including saved SystemBlueprint
    - Auth: Bearer JWT / API Key
    - Rate: 60/min
    """
    return {
        "template_id": template_id,
        "name": "E-Commerce Template",
        "blueprint": {
            "project_name": "ecommerce",
            "domain": "e-commerce",
            "stack": {
                "frontend": {"framework": "React", "language": "TypeScript", "css": "TailwindCSS"},
                "backend": {"framework": "FastAPI", "language": "Python", "orm": "SQLAlchemy"},
                "database": {"engine": "PostgreSQL", "migration_tool": "Alembic"}
            }
        }
    }

@router.delete("/templates/{template_id}", status_code=204, tags=["Templates"])
async def delete_template(
    template_id: str,
    authorization: str = Depends(verify_bearer_token)
):
    """
    Delete a custom template (system templates cannot be deleted)
    - Auth: Bearer JWT
    - Rate: 20/hour
    """
    return None


# ================================
# GROUP 7: HEALTH & OBSERVABILITY ENDPOINTS (4 endpoints)
# ================================


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Liveness probe — is the process running?
    - Auth: None
    - Rate: Unlimited
    """
    return {"status": "ok"}

@router.get("/ready", response_model=ReadyResponse, tags=["Health"])
async def readiness_check():
    """
    Readiness probe — checks postgres, redis, llm_api, sandbox
    - Auth: None
    - Rate: Unlimited
    """
    return {
        "status": "ready",
        "checks": {
            "postgres": "ok",
            "redis": "ok",
            "llm_api": "ok",
            "sandbox": "ok"
        }
    }

@router.get("/metrics", tags=["Health"])
async def get_metrics():
    """
    Prometheus-format metrics for scraping
    - Auth: None
    - Rate: Unlimited
    """
    return {
        "type": "prometheus",
        "message": "Prometheus metrics endpoint"
    }

@router.get("/version", response_model=VersionResponse, tags=["Health"])
async def get_version():
    """
    Build version, git SHA, deploy timestamp
    - Auth: None
    - Rate: Unlimited
    """
    return {
        "version": "1.0.0",
        "git_sha": "abc1234567890def",
        "deployed_at": datetime.now()
    }


# ================================
# GROUP 8: WEBSOCKET ENDPOINT (1 endpoint)
# ================================



@router.get("/ws-info", tags=["WebSocket"])
async def websocket_info():
    """
    WebSocket Real-Time Streaming Endpoint
    - Connection URL: wss://api.opsmindai.io/ws/{job_id}?token=<jwt_or_api_key>
    - Auth: JWT or API Key (query parameter)
    - Rate: 1 connection per job
    
    Events emitted:
      - job.started: job_id, started_at
      - agent.started: agent_name, node_index
      - agent.progress: agent_name, message, tokens_so_far
      - agent.completed: agent_name, duration_s, tokens_used
      - agent.failed: agent_name, error, retry_count
      - test.started: sandbox_id
      - test.result: passed, coverage_pct, test_counts
      - job.completed: repo_url, duration_s, total_tokens
      - job.failed: error, failed_agent
    """
    return {
        "message": "WebSocket endpoint for real-time job streaming",
        "url": "wss://api.opsmindai.io/ws/{job_id}?token=<jwt_or_api_key>"
    }


