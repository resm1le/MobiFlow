export type DeviceStatus = "ONLINE" | "OFFLINE" | "QUIESCED";
export type TaskStatus =
  | "DRAFT"
  | "QUEUED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED";
export type RunStatus = "QUEUED" | "RUNNING" | "CANCELLING" | "TERMINAL";
export type RunFinalState = "SUCCEEDED" | "FAILED" | "CANCELLED" | "PARTIAL";
export type RunTargetStatus =
  | "QUEUED"
  | "RUNNING"
  | "RETRY_PENDING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED";
export type AttemptStatus =
  | "CREATED"
  | "LEASED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED"
  | "PRECHECK_FAILED"
  | "SYSTEM_ABORTED"
  | "LEASE_EXPIRED";
export type DeviceCommandType =
  | "STOP_LOOP"
  | "CANCEL_ATTEMPT"
  | "FORCE_HEALTH_CHECK"
  | "REREGISTER"
  | "REFRESH_CONFIG"
  | "QUIESCE";

export interface DeviceSummary {
  deviceId: string;
  protocolVersion: string;
  executorVersion: string;
  brand: string;
  model: string;
  androidVersion: string;
  screenWidth: number;
  screenHeight: number;
  status: DeviceStatus;
  registered: boolean;
  online: boolean;
  busy: boolean;
  hostGroup: string;
  tags: string[];
  installedProfiles: string[];
  lastHeartbeatAt: number | null;
  currentTaskId: string | null;
  currentAttemptId: string | null;
  currentTaskType: string | null;
  configVersion: string | null;
  leaseExpireAt: number | null;
  lastCommand: string | null;
  authConfigured: boolean;
  health: Record<string, unknown>;
  updatedAt: number;
}

export type DeviceDetail = DeviceSummary;

export interface TaskAttemptSummary {
  attemptId: string;
  taskId: string;
  deviceId: string;
  status: AttemptStatus;
  finalState: string | null;
  failureReason: string | null;
  runId: string | null;
  leaseExpireAt: number | null;
  startedAt: number | null;
  finishedAt: number | null;
  createdAt: number;
  updatedAt: number;
}

export interface TaskSummary {
  taskId: string;
  runId: string | null;
  runTargetId: string | null;
  targetDeviceId: string | null;
  taskType: string;
  profilePackage: string;
  status: TaskStatus;
  priority: number;
  source: string;
  scheduleVersion?: string | null;
  createdBy?: string | null;
  createdAt: number;
  updatedAt: number;
  latestAttempt: TaskAttemptSummary | null;
}

export interface TaskDetail extends TaskSummary {
  idempotencyKey: string | null;
  labels: string[];
  taskPayload: Record<string, unknown>;
  runConfig: Record<string, unknown>;
  artifactPolicy: Record<string, unknown>;
}

export interface AttemptDetail extends TaskAttemptSummary {
  attempt: TaskAttemptSummary;
  events: AttemptEvent[];
  artifacts: AttemptArtifact[];
}

export interface AttemptEvent {
  id: number;
  attemptId: string;
  taskId: string;
  deviceId: string;
  runId: string | null;
  scenarioId: string | null;
  stepIndex: number | null;
  actionIndex: number | null;
  eventType: string;
  state: string | null;
  code: string | null;
  message: string | null;
  ts: number;
}

export interface AttemptArtifact {
  artifactId: string;
  attemptId: string;
  taskId: string;
  runId: string | null;
  artifactType: string;
  fileName: string;
  mimeType: string;
  objectKey: string;
  downloadPath: string;
  sizeBytes: number;
  createdAt: number;
}

export interface CreateTaskRequest {
  taskType: string;
  profilePackage: string;
  priority: number;
  source: string;
  labels: string[];
  taskPayload: Record<string, unknown>;
  runConfig: Record<string, unknown>;
  artifactPolicy: Record<string, unknown>;
  idempotencyKey?: string | null;
}

export interface AiRunDraft {
  name: string;
  description?: string | null;
  devicePoolId: string;
  taskType: string;
  profilePackage: string;
  taskPayload: Record<string, unknown>;
  runConfig: Record<string, unknown>;
  artifactPolicy: Record<string, unknown>;
  priority: number;
  labels: string[];
  maxRetriesPerDevice: number;
  queueTimeoutMs: number;
}

export interface CreateAiRunPlanRequest {
  goal: string;
  constraints: Record<string, unknown>;
}

export interface AiRunPlanValidation {
  materializable: boolean;
  errors: string[];
  warnings: string[];
}

export interface CreateAiRunPlanResponse {
  requestId: string;
  runDraft: AiRunDraft;
  warnings: string[];
  reviewHints: string[];
  validation: AiRunPlanValidation;
  modelMeta: Record<string, unknown>;
}

export interface MaterializeAiRunPlanRequest {
  createdBy: string;
}

export interface KeyMoment {
  title: string;
  eventType?: string | null;
  stepIndex?: number | null;
  message?: string | null;
}

export interface RunSummaryResponse {
  summaryText: string;
  keyMoments: KeyMoment[];
  finalJudgement: string;
  evidence: string[];
  warnings: string[];
  modelMeta: Record<string, unknown>;
}

export interface FailureAnalysisResponse {
  failureCategory: string;
  probableCause: string;
  suggestedAction: string;
  evidence: string[];
  warnings: string[];
  modelMeta: Record<string, unknown>;
}

export interface FailureTriageValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface FailureTriageResult {
  failureCategory: string;
  probableCause: string;
  confidence: number;
  retryRecommendation: string;
  suggestedNextAction: string;
  operatorReviewHints: string[];
  evidence: string[];
}

export interface RunTargetFailureTriage {
  triageResultId: string;
  runTargetId: string;
  result: FailureTriageResult;
  validation: FailureTriageValidation;
  modelMeta: Record<string, unknown>;
  generatedAt: number;
}

export interface AiRunSummaryValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface AiRunSummary {
  summaryId: string;
  runId: string;
  result: {
    summaryText: string;
    keyMoments: KeyMoment[];
    finalJudgement: string;
    evidence: string[];
  };
  validation: AiRunSummaryValidation;
  modelMeta: Record<string, unknown>;
  generatedAt: number;
}

export interface SendDeviceCommandRequest {
  type: DeviceCommandType;
  attemptId?: string | null;
  expireInMs?: number | null;
}

export interface DeviceCommandResponse {
  deviceId: string;
  type: DeviceCommandType;
  attemptId: string | null;
}

export interface DevicePool {
  poolId: string;
  name: string;
  description: string | null;
  hostGroup: string | null;
  deviceIds: string[];
  requiredTags: string[];
  excludedTags: string[];
  createdBy: string;
  createdAt: number;
  updatedAt: number;
}

export interface CreateDevicePoolRequest {
  name: string;
  description?: string | null;
  hostGroup?: string | null;
  deviceIds: string[];
  requiredTags: string[];
  excludedTags: string[];
  createdBy?: string | null;
}

export interface RunStatusCounts {
  totalTargets: number;
  queued: number;
  running: number;
  retryPending: number;
  succeeded: number;
  failed: number;
  cancelled: number;
}

export interface ExperimentRunSummary {
  runId: string;
  name: string;
  description: string | null;
  poolId: string;
  status: RunStatus;
  finalState: RunFinalState | null;
  taskType: string;
  profilePackage: string;
  priority: number;
  labels: string[];
  source: string;
  createdBy: string;
  maxRetriesPerDevice: number;
  queueTimeoutMs: number;
  cancelRequested: boolean;
  createdAt: number;
  updatedAt: number;
  startedAt: number | null;
  finishedAt: number | null;
  counts: RunStatusCounts;
}

export interface ExperimentRunTarget {
  runTargetId: string;
  deviceId: string;
  status: RunTargetStatus;
  attemptCount: number;
  currentTaskId: string | null;
  latestAttemptId: string | null;
  failureReason: string | null;
  startedAt: number | null;
  finishedAt: number | null;
  task: TaskDetail | null;
  latestAttempt: TaskAttemptSummary | null;
}

export interface ExperimentRunDetail {
  run: ExperimentRunSummary;
  taskPayload: Record<string, unknown>;
  runConfig: Record<string, unknown>;
  artifactPolicy: Record<string, unknown>;
  targets: ExperimentRunTarget[];
}

export interface CreateExperimentRunRequest {
  name: string;
  description?: string | null;
  devicePoolId: string;
  taskType: string;
  profilePackage: string;
  taskPayload: Record<string, unknown>;
  runConfig: Record<string, unknown>;
  artifactPolicy: Record<string, unknown>;
  priority: number;
  labels: string[];
  source: string;
  createdBy?: string | null;
  maxRetriesPerDevice?: number | null;
  queueTimeoutMs?: number | null;
}
