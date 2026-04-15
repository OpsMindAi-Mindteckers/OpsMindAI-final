Supratim Dey --->>> # ================================
# SUMMARY OF 41 ENDPOINTS 
# ================================
# GROUP 1: Authentication (6 endpoints)
#   - POST /auth/register
#   - POST /auth/login
#   - POST /auth/logout
#   - POST /auth/refresh
#   - POST /auth/api-key
#   - DELETE /auth/api-key/{key_id}
#
# GROUP 2: User Account (6 endpoints)
#   - GET /users/me
#   - PATCH /users/me
#   - POST /users/me/change-password
#   - DELETE /users/me
#   - GET /users/me/api-keys
#   - GET /users/me/usage
#
# GROUP 3: Projects (9 endpoints)
#   - GET /projects
#   - POST /projects (PRIMARY ENDPOINT)
#   - GET /projects/{project_id}
#   - PATCH /projects/{project_id}
#   - DELETE /projects/{project_id}
#   - GET /projects/{project_id}/files
#   - GET /projects/{project_id}/files/{path}
#   - POST /projects/{project_id}/rebuild
#   - GET /projects/{project_id}/diff
#
# GROUP 4: Jobs (7 endpoints)
#   - GET /jobs
#   - GET /jobs/{job_id}
#   - GET /jobs/{job_id}/logs
#   - GET /jobs/{job_id}/agents
#   - GET /jobs/{job_id}/test-report
#   - POST /jobs/{job_id}/cancel
#   - GET /jobs/{job_id}/artifacts
#
# GROUP 5: Agents (4 endpoints)
#   - GET /agents
#   - GET /agents/{agent_name}
#   - GET /agents/{agent_name}/metrics
#   - PATCH /agents/{agent_name}/config
#
# GROUP 6: Templates (4 endpoints)
#   - GET /templates
#   - POST /templates
#   - GET /templates/{template_id}
#   - DELETE /templates/{template_id}
#
# GROUP 7: Health & Observability (4 endpoints)
#   - GET /health
#   - GET /ready
#   - GET /metrics
#   - GET /version
#
# GROUP 8: WebSocket (1 endpoint)
#   - WS /ws/{job_id}
#
# TOTAL: 41 endpoints (36 REST + 4 Health + 1 WebSocket)
