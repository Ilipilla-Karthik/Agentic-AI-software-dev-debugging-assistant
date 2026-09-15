export interface TestCaseResult {
  name: string;
  outcome: "passed" | "failed" | "error" | "skipped";
  duration_ms?: number | null;
  description?: string;
}

export interface ExecutionResult {
  returncode?: number | null;
  passed: number;
  failed: number;
  error: number;
  skipped: number;
  duration_ms: number;
  output: string;
  cases: TestCaseResult[];
  timeout?: boolean;
}

export interface DiffEntry {
  path: string;
  diff: string;
  before?: string | null;
  after?: string | null;
  summary: string;
  applied_at: string;
}

export interface ReviewComment {
  severity: "critical" | "warning" | "info";
  file: string;
  line?: number | null;
  message: string;
}

export interface ReviewResult {
  score: number;
  passed: boolean;
  summary: string;
  comments: ReviewComment[];
}

export interface ProjectState {
  project_id: string;
  requirement: string;
  status: string;
  created_at?: string;
  completed_at?: string | null;
  analysis?: string;
  plan?: string[];
  architecture?: Record<string, unknown>;
  files?: Record<string, string>;
  test_results?: ExecutionResult;
  diffs?: DiffEntry[];
  errors?: string[];
  fixes?: Record<string, unknown>[];
  review?: ReviewResult;
  summary?: string;
  commits?: string[];
  logs?: string[];
  project_dir?: string;
  attempts?: number;
}

export interface ProjectListItem {
  project_id: string;
  requirement: string;
  status: string;
  created_at: string;
  completed_at?: string | null;
}

export interface LiveEvent {
  type: string;
  stage: string;
  message: string;
  payload?: unknown;
  ts: string;
}

export type WorkflowStage = "planning" | "coding" | "testing" | "debugging" | "reviewing" | "completed" | "failed";