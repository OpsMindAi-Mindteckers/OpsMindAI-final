from fastapi import APIRouter, HTTPException, Depends, status, Query, Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID

router = APIRouter(prefix="/agents", tags=["agents"])


# ==================== SCHEMAS ====================

class AgentMetrics(BaseModel):
    """Operational metrics for a specific agent"""
    agent_name: str = Field(..., description="Name of the agent")
    total_runs: int = Field(..., description="Total number of agent runs")
    success_rate: float = Field(..., ge=0, le=1, description="Success rate as decimal (0-1)")
    avg_duration_s: float = Field(..., description="Average duration in seconds")
    avg_tokens_used: int = Field(..., description="Average tokens used per run")
    revision_rate: float = Field(..., ge=0, le=1, description="Revision rate as decimal")
    cost_usd_total: float = Field(..., description="Total cost in USD")
    cost_usd_avg: float = Field(..., description="Average cost per run in USD")
    last_run_at: Optional[datetime] = Field(None, description="Timestamp of last run")


class AgentConfig(BaseModel):
    """Agent configuration parameters"""
    prompt: Optional[str] = Field(None, description="Agent system prompt")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens for generation")
    temperature: Optional[float] = Field(None, ge=0, le=2, description="Temperature parameter")
    top_p: Optional[float] = Field(None, ge=0, le=1, description="Top-p sampling parameter")
    retry_count: Optional[int] = Field(None, ge=0, description="Number of retries on failure")
    timeout_seconds: Optional[int] = Field(None, ge=1, description="Timeout in seconds")
    enabled: Optional[bool] = Field(None, description="Agent enabled status")


class UpdateAgentConfigRequest(BaseModel):
    """Request to update agent configuration"""
    prompt: Optional[str] = Field(None, description="Agent system prompt")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens for generation")
    temperature: Optional[float] = Field(None, ge=0, le=2, description="Temperature parameter")
    top_p: Optional[float] = Field(None, ge=0, le=1, description="Top-p sampling parameter")
    retry_count: Optional[int] = Field(None, ge=0, description="Number of retries on failure")
    timeout_seconds: Optional[int] = Field(None, ge=1, description="Timeout in seconds")
    enabled: Optional[bool] = Field(None, description="Agent enabled status")


class AgentStatus(BaseModel):
    """Status of an individual agent"""
    agent_name: str = Field(..., description="Name of the agent")
    status: str = Field(..., description="Current status: active, idle, error, disabled")
    version: str = Field(..., description="Agent version")
    enabled: bool = Field(..., description="Whether agent is enabled")
    last_error: Optional[str] = Field(None, description="Last error message if any")
    last_run_at: Optional[datetime] = Field(None, description="Last run timestamp")


class AgentStatusResponse(BaseModel):
    """Response containing list of all agents and their status"""
    agents: List[AgentStatus] = Field(..., description="List of registered agents")
    total: int = Field(..., description="Total number of agents")
    healthy_count: int = Field(..., description="Number of healthy agents")


class AgentDetailResponse(BaseModel):
    """Detailed information about a specific agent"""
    agent_name: str = Field(..., description="Name of the agent")
    status: str = Field(..., description="Current status")
    version: str = Field(..., description="Agent version")
    enabled: bool = Field(..., description="Whether agent is enabled")
    config: AgentConfig = Field(..., description="Agent configuration")
    metrics: Optional[AgentMetrics] = Field(None, description="Agent metrics")
    description: Optional[str] = Field(None, description="Agent description")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class AgentConfigResponse(BaseModel):
    """Response after updating agent configuration"""
    agent_name: str = Field(..., description="Name of the agent")
    config: AgentConfig = Field(..., description="Updated configuration")
    updated_at: datetime = Field(..., description="Update timestamp")
    message: str = Field(..., description="Status message")


# ==================== ENDPOINTS ====================

@router.get("", response_model=AgentStatusResponse)
async def list_agents(
    status_filter: Optional[str] = Query(None, description="Filter by status: active, idle, error, disabled")
):
    """
    List all registered agents and their status
    
    Returns a list of all agents in the system with their current status,
    health information, and basic metrics.
    
    **Auth Required:** Bearer token
    """
    pass


@router.get("/{agent_name}", response_model=AgentDetailResponse)
async def get_agent(
    agent_name: str = Path(..., description="Name of the agent", min_length=1)
):
    """
    Get agent configuration and metrics
    
    Returns detailed information about a specific agent including its configuration,
    current status, and operational metrics.
    
    **Auth Required:** Bearer token
    
    **Path Parameters:**
    - `agent_name`: The unique identifier of the agent
    """
    pass


@router.get("/{agent_name}/metrics", response_model=AgentMetrics)
async def get_agent_metrics(
    agent_name: str = Path(..., description="Name of the agent", min_length=1)
):
    """
    Get operational metrics for a specific agent
    
    Returns operational metrics including token usage, average duration, 
    success rate, and cost analysis. Useful for monitoring agent performance 
    and cost optimization.
    
    **Auth Required:** Bearer token
    
    **Path Parameters:**
    - `agent_name`: The unique identifier of the agent
    
    **Response (200):**
    ```json
    {
      "agent_name": "backend",
      "total_runs": 1482,
      "success_rate": 0.93,
      "avg_duration_s": 31.4,
      "avg_tokens_used": 11200,
      "revision_rate": 0.12,
      "cost_usd_total": 284.20,
      "cost_usd_avg": 0.19,
      "last_run_at": "2025-01-01T00:00:00Z"
    }
    ```
    """
    pass


@router.patch("/{agent_name}/config", response_model=AgentConfigResponse, status_code=status.HTTP_200_OK)
async def update_agent_config(
    agent_name: str = Path(..., description="Name of the agent", min_length=1),
    request: UpdateAgentConfigRequest = None
):
    """
    Update agent prompt or parameters
    
    Updates the configuration of a specific agent. Allows modifications to:
    - System prompt
    - Token limits
    - Sampling parameters (temperature, top_p)
    - Retry behavior
    - Timeout settings
    - Enable/disable status
    
    **Auth Required:** Bearer token with Admin role (Admin only)
    
    **Path Parameters:**
    - `agent_name`: The unique identifier of the agent
    
    **Request Body:**
    ```json
    {
      "prompt": "Updated system prompt...",
      "max_tokens": 4096,
      "temperature": 0.7,
      "top_p": 0.9,
      "retry_count": 3,
      "timeout_seconds": 60,
      "enabled": true
    }
    ```
    
    **Response (200):**
    ```json
    {
      "agent_name": "backend",
      "config": {
        "prompt": "Updated system prompt...",
        "max_tokens": 4096,
        "temperature": 0.7,
        "top_p": 0.9,
        "retry_count": 3,
        "timeout_seconds": 60,
        "enabled": true
      },
      "updated_at": "2025-01-01T00:00:00Z",
      "message": "Agent configuration updated successfully"
    }
    ```
    """
    pass
