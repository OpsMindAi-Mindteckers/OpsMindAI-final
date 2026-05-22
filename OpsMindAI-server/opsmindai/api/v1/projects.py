from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID

router = APIRouter(prefix="/projects", tags=["projects"])


# ==================== SCHEMAS ====================

class Constraints(BaseModel):
    frontend_framework: Optional[str] = Field(None, description="Frontend framework hint")
    backend_framework: Optional[str] = Field(None, description="Backend framework hint")
    database: Optional[str] = Field(None, description="Database type hint")
    exclude_tech: Optional[List[str]] = Field(None, description="Technologies to exclude")
    target_cloud: Optional[str] = Field(None, description="Target cloud provider")


class GitConfig(BaseModel):
    provider: str = Field(..., description="Git provider: github, gitlab, bitbucket")
    org_or_user: str = Field(..., description="Organization or username")
    repo_name: Optional[str] = Field(None, description="Repository name, derived from project name if omitted")
    private: Optional[bool] = Field(True, description="Make repository private")


class CreateProjectRequest(BaseModel):
    name: str = Field(..., description="Project name")
    prompt: str = Field(..., description="Natural language prompt for project build")
    constraints: Optional[Constraints] = Field(None, description="Optional build constraints")
    git_config: Optional[GitConfig] = Field(None, description="Optional Git configuration")
    template_id: Optional[UUID] = Field(None, description="Optional template to apply")


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = Field(None, description="Project name")
    prompt: Optional[str] = Field(None, description="Project prompt")
    constraints: Optional[Constraints] = Field(None, description="Build constraints")


class JobInfo(BaseModel):
    job_id: UUID
    status: str
    created_at: datetime
    duration_seconds: Optional[int] = None


class AgentMetrics(BaseModel):
    status: str
    tokens_used: int
    duration_s: int


class AgentSummary(BaseModel):
    architecture: Optional[AgentMetrics] = None
    frontend: Optional[AgentMetrics] = None
    backend: Optional[AgentMetrics] = None
    database: Optional[AgentMetrics] = None
    testing: Optional[AgentMetrics] = None


class ProjectResponse(BaseModel):
    project_id: UUID
    name: str
    prompt: str
    status: str
    repo_url: Optional[str] = None
    blueprint: Optional[Dict[str, Any]] = None
    jobs: List[JobInfo] = []
    agent_summary: Optional[AgentSummary] = None
    created_at: datetime


class CreateProjectResponse(BaseModel):
    project_id: UUID
    job_id: UUID
    status: str
    ws_url: str
    created_at: datetime


class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse]
    total: int
    page: int
    page_size: int


class FileListResponse(BaseModel):
    files: List[Dict[str, Any]]
    project_id: UUID


class DiffResponse(BaseModel):
    project_id: UUID
    from_build: str
    to_build: str
    differences: List[Dict[str, Any]]


# ==================== ENDPOINTS ====================

@router.get("", response_model=ProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Page size"),
    status: Optional[str] = Query(None, description="Filter by status")
):
    """List all projects for current user"""
    return ProjectListResponse(
        projects=[],
        total=0,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=CreateProjectResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_project(
    request: CreateProjectRequest
):
    """
    Create a new project and trigger full pipeline.
    
    This is the corepoint. Accepts a natural language prompt and dispatches 
    the multi-agent build pipeline asynchronously.
    """
    pass


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID
):
    """
    Get project details including latest job status, generated repo URL, 
    and agent execution summary.
    """
    pass


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    request: UpdateProjectRequest
):
    """Update project metadata"""
    pass


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID
):
    """Delete project and all associated jobs"""
    pass


@router.get("/{project_id}/files", response_model=FileListResponse)
async def list_project_files(
    project_id: UUID,
    path: Optional[str] = Query(None, description="Optional path filter")
):
    """List generated files for a project"""
    pass


@router.get("/{project_id}/files/{file_path:path}")
async def download_project_file(
    project_id: UUID,
    file_path: str
):
    """Download specific generated file"""
    pass


@router.post("/{project_id}/rebuild", response_model=CreateProjectResponse, status_code=status.HTTP_202_ACCEPTED)
async def rebuild_project(
    project_id: UUID
):
    """Trigger a rebuild of the project"""
    pass


@router.get("/{project_id}/diff", response_model=DiffResponse)
async def get_project_diff(
    project_id: UUID,
    from_build: Optional[UUID] = Query(None, description="Source build ID"),
    to_build: Optional[UUID] = Query(None, description="Target build ID")
):
    """Show diff between two builds"""
    pass
