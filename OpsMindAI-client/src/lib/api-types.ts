/**
 * TypeScript interfaces for all API responses and requests
 */

// ==================== Auth Types ====================

export interface RegisterRequest {
  email?: string;
  password?: string;
  username?: string;
}

export interface LoginRequest {
  email?: string;
  password?: string;
  username?: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number;
}

export interface RegisterResponse extends TokenResponse {
  user_id: string;
}

export interface UserProfile {
  id: string;
  email: string;
  username?: string;
  created_at: string;
  updated_at?: string;
}

// ==================== Projects Types ====================

export interface Constraints {
  frontend_framework?: string;
  backend_framework?: string;
  database?: string;
  exclude_tech?: string[];
  target_cloud?: string;
}

export interface GitConfig {
  provider: string;
  org_or_user: string;
  repo_name?: string;
  private?: boolean;
}

export interface CreateProjectRequest {
  name: string;
  prompt: string;
  constraints?: Constraints;
  git_config?: GitConfig;
  template_id?: string;
}

export interface UpdateProjectRequest {
  name?: string;
  prompt?: string;
  constraints?: Constraints;
}

export interface JobInfo {
  job_id: string;
  status: string;
  created_at: string;
  duration_seconds?: number;
}

export interface AgentMetrics {
  status: string;
  tokens_used: number;
  duration_s: number;
}

export interface AgentSummary {
  architecture?: AgentMetrics;
  frontend?: AgentMetrics;
  backend?: AgentMetrics;
  database?: AgentMetrics;
  testing?: AgentMetrics;
}

export interface ProjectResponse {
  project_id: string;
  name: string;
  prompt: string;
  status: string;
  repo_url?: string;
  blueprint?: Record<string, any>;
  jobs: JobInfo[];
  agent_summary?: AgentSummary;
  created_at: string;
}

export interface CreateProjectResponse {
  project_id: string;
  job_id: string;
  status: string;
  ws_url: string;
  created_at: string;
}

export interface ProjectListResponse {
  projects: ProjectResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface FileListResponse {
  files: Array<Record<string, any>>;
  project_id: string;
}

export interface DiffResponse {
  project_id: string;
  from_build: string;
  to_build: string;
  differences: Array<Record<string, any>>;
}

// ==================== SRE / Incidents Types ====================

export enum AlertSource {
  PROMETHEUS = 'prometheus',
  GRAFANA = 'grafana',
  DATADOG = 'datadog',
  NEW_RELIC = 'newrelic',
  CLOUDWATCH = 'cloudwatch',
}

export enum IncidentSeverity {
  CRITICAL = 'critical',
  HIGH = 'high',
  MEDIUM = 'medium',
  LOW = 'low',
  INFO = 'info',
}

export enum IncidentStatus {
  OPEN = 'open',
  IN_PROGRESS = 'in_progress',
  RESOLVED = 'resolved',
  ACKNOWLEDGED = 'acknowledged',
  ESCALATED = 'escalated',
  CLOSED = 'closed',
}

export enum Playbook {
  AUTO = 'auto',
  MANUAL = 'manual',
  ESCALATE = 'escalate',
}

export interface AlertPayload {
  source: AlertSource;
  service: string;
  severity: IncidentSeverity;
  alert_name: string;
  labels?: Record<string, any>;
  annotations?: Record<string, any>;
  raw_payload?: Record<string, any>;
}

export interface IngestRequest extends AlertPayload {}

export interface RCARequest {
  incident_id: string;
}

export interface RemediateRequest {
  incident_id: string;
  playbook?: Playbook;
}

export interface JobSubmitResponse {
  job_id: string;
  incident_id?: string;
  message: string;
  status: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: string;
  phase?: string;
  incident_id?: string;
  error?: string;
  created_at?: string;
  completed_at?: string;
  duration_s?: number;
  confidence?: number;
  root_cause?: string;
  auto_remediable?: boolean;
  remediation_status?: string;
  actions_taken?: any[];
  normalised?: boolean;
}

export interface TimelineEvent {
  timestamp: string;
  event_type: string;
  description: string;
  data?: Record<string, any>;
}

export interface IncidentDetail {
  incident_id: string;
  status: IncidentStatus;
  severity: IncidentSeverity;
  service: string;
  alert_name: string;
  created_at: string;
  updated_at?: string;
  rca_result?: {
    confidence: number;
    root_cause: string;
    remediation_steps?: string[];
  };
  timeline: TimelineEvent[];
}

export interface IncidentHistory {
  incidents: IncidentDetail[];
  total: number;
  page: number;
  page_size: number;
}

// ==================== Testing Types ====================

export interface GenerateTestRequest {
  repo_url: string;
  file_path?: string;
  branch?: string;
  framework?: string;
  coverage_threshold?: number;
  pr_number?: number;
}

export interface SuiteRequest {
  generation_job_id: string;
  pr_number?: number;
}

export interface RegressionRequest {
  repo_url: string;
  branch?: string;
  trigger_event?: Record<string, any>;
}

export interface GeneratedFileSummary {
  source_file: string;
  output_file: string;
  functions_processed: number;
  tokens_used: number;
  model_used: string;
}

export interface CoverageBreakdown {
  coverage_pct: number;
  delta_pct: number;
  lines_covered: number;
  lines_total: number;
  gate_passed: boolean;
  threshold: number;
  previous_pct?: number;
}

export interface TestingJobStatus {
  job_id: string;
  status: string;
  phase?: string;
  error?: string;
  created_at?: string;
  completed_at?: string;
  duration_s?: number;
  generated_files?: GeneratedFileSummary[];
  warnings?: string[];
  coverage?: CoverageBreakdown;
}

export interface TestingHistory {
  jobs: TestingJobStatus[];
  total: number;
  page: number;
  page_size: number;
}

// ==================== Agent Types ====================

export interface AgentInfo {
  name: string;
  status: string;
  description?: string;
  version?: string;
  metrics?: {
    jobs_total?: number;
    jobs_success?: number;
    jobs_failed?: number;
    avg_duration_s?: number;
  };
}

export interface AgentListResponse {
  agents: AgentInfo[];
}

// ==================== Refactor Types ====================

export interface RefactorAnalyzeRequest {
  repo_url: string;
  branch?: string;
  file_paths?: string[];
  severity_threshold?: string;
  model?: string;
}

export interface RefactorSuggestRequest {
  repo_url: string;
  branch?: string;
  source_job_id: string;
  model?: string;
}

export interface RefactorApplyRequest {
  repo_url: string;
  branch?: string;
  source_job_id: string;
  pr_title?: string;
  pr_body?: string;
  draft?: boolean;
}

export interface RefactorRequest {
  repo_url: string;
  file_path?: string;
  smell_type?: string;
  branch?: string;
  pr_number?: number;
}

export interface RefactorSmell {
  smell_type: string;
  file_path: string;
  line_start?: number;
  line_end?: number;
  description: string;
  severity?: string;
  original_code?: string;
}

export interface RefactorSuggestion {
  smell_type: string;
  file_path: string;
  line_start?: number;
  line_end?: number;
  description: string;
  severity?: string;
  original_code?: string;
  refactored_code?: string;
  explanation?: string;
  patch?: string;
}

export interface RefactorJobStatus {
  job_id: string;
  status: string;
  phase?: string;
  error?: string;
  created_at?: string;
  completed_at?: string;
  duration_s?: number;
  pr_url?: string;
  smells?: RefactorSmell[];
  suggestions?: RefactorSuggestion[];
  changes_summary?: {
    files_modified: number;
    smells_detected: number;
    smells_fixed: number;
  };
}

export interface RefactorSuggestResponse {
  job_id: string;
  status: string;
  suggestions: RefactorSuggestion[];
  summary?: string;
  total_smells?: number;
  message?: string;
}

export interface RefactorApplyResponse {
  job_id: string;
  pr_url?: string;
  status: string;
  message: string;
}

export interface RefactorHistory {
  jobs: RefactorJobStatus[];
  total: number;
  page: number;
  page_size: number;
}

// ==================== Users Types ====================

export interface UserResponse {
  id: string;
  email: string;
  username?: string;
  role?: string;
  created_at: string;
}

export interface UserListResponse {
  users: UserResponse[];
  total: number;
  page: number;
  page_size: number;
}
