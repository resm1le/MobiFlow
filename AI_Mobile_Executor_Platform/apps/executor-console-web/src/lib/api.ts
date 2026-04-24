import { API_BASE_URL } from "./constants";
import type {
  AiRunSummary,
  CreateAiRunPlanRequest,
  CreateAiRunPlanResponse,
  AttemptArtifact,
  AttemptDetail,
  AttemptEvent,
  CreateDevicePoolRequest,
  CreateExperimentRunRequest,
  CreateTaskRequest,
  DeviceCommandResponse,
  DevicePool,
  DeviceDetail,
  ExperimentRunDetail,
  ExperimentRunSummary,
  RunTargetFailureTriage,
  MaterializeAiRunPlanRequest,
  DeviceSummary,
  SendDeviceCommandRequest,
  TaskAttemptSummary,
  TaskDetail,
  TaskSummary,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const bearerToken = import.meta.env.VITE_CONTROL_API_BEARER_TOKEN ?? "";
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(bearerToken ? { Authorization: `Bearer ${bearerToken}` } : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  const text = await response.text();
  const payload = text ? (JSON.parse(text) as unknown) : null;

  if (!response.ok) {
    const message =
      typeof payload === "object" &&
      payload !== null &&
      "message" in payload &&
      typeof (payload as { message?: unknown }).message === "string"
        ? ((payload as { message: string }).message ?? response.statusText)
        : response.statusText;
    throw new ApiError(message, response.status, payload);
  }

  return payload as T;
}

async function requestBlob(path: string, init?: RequestInit): Promise<Blob> {
  const bearerToken = import.meta.env.VITE_CONTROL_API_BEARER_TOKEN ?? "";
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      ...(bearerToken ? { Authorization: `Bearer ${bearerToken}` } : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const text = await response.text();
    const payload = text ? (JSON.parse(text) as unknown) : null;
    const message =
      typeof payload === "object" &&
      payload !== null &&
      "message" in payload &&
      typeof (payload as { message?: unknown }).message === "string"
        ? ((payload as { message: string }).message ?? response.statusText)
        : response.statusText;
    throw new ApiError(message, response.status, payload);
  }

  return response.blob();
}

export const controlApi = {
  listDevices: () => request<DeviceSummary[]>("/api/devices"),
  getDevice: (deviceId: string) =>
    request<DeviceDetail>(`/api/devices/${encodeURIComponent(deviceId)}`),
  listDeviceAttempts: (deviceId: string) =>
    request<TaskAttemptSummary[]>(
      `/api/devices/${encodeURIComponent(deviceId)}/attempts`,
    ),
  resumeDevice: (deviceId: string) =>
    request<DeviceDetail>(`/api/devices/${encodeURIComponent(deviceId)}/resume`, {
      method: "POST",
    }),
  sendDeviceCommand: (deviceId: string, body: SendDeviceCommandRequest) =>
    request<DeviceCommandResponse>(
      `/api/devices/${encodeURIComponent(deviceId)}/commands`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
  listDevicePools: () => request<DevicePool[]>("/api/device-pools"),
  getDevicePool: (poolId: string) =>
    request<DevicePool>(`/api/device-pools/${encodeURIComponent(poolId)}`),
  createDevicePool: (body: CreateDevicePoolRequest) =>
    request<DevicePool>("/api/device-pools", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listTasks: () => request<TaskSummary[]>("/api/tasks"),
  getTask: (taskId: string) =>
    request<TaskDetail>(`/api/tasks/${encodeURIComponent(taskId)}`),
  createTask: (body: CreateTaskRequest) =>
    request<TaskDetail>("/api/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createAiRunPlan: (body: CreateAiRunPlanRequest) =>
    request<CreateAiRunPlanResponse>("/api/ai/run-plans", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  materializeAiRunPlan: (requestId: string, body: MaterializeAiRunPlanRequest) =>
    request<ExperimentRunDetail>(`/api/ai/run-plans/${encodeURIComponent(requestId)}/materialize`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  cancelTask: (taskId: string) =>
    request<void>(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, {
      method: "POST",
    }),
  listRuns: () => request<ExperimentRunSummary[]>("/api/runs"),
  getRun: (runId: string) =>
    request<ExperimentRunDetail>(`/api/runs/${encodeURIComponent(runId)}`),
  createRun: (body: CreateExperimentRunRequest) =>
    request<ExperimentRunDetail>("/api/runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  cancelRun: (runId: string) =>
    request<void>(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
    }),
  createRunSummary: (runId: string) =>
    request<AiRunSummary>(`/api/runs/${encodeURIComponent(runId)}/summary`, {
      method: "POST",
    }),
  getLatestRunSummary: (runId: string) =>
    request<AiRunSummary>(`/api/runs/${encodeURIComponent(runId)}/summary/latest`),
  listAttempts: () => request<TaskAttemptSummary[]>("/api/attempts"),
  getAttempt: (attemptId: string) =>
    request<AttemptDetail>(`/api/attempts/${encodeURIComponent(attemptId)}`),
  listAttemptEvents: (attemptId: string) =>
    request<AttemptEvent[]>(`/api/attempts/${encodeURIComponent(attemptId)}/events`),
  listAttemptArtifacts: (attemptId: string) =>
    request<AttemptArtifact[]>(
      `/api/attempts/${encodeURIComponent(attemptId)}/artifacts`,
    ),
  downloadAttemptArtifact: (attemptId: string, artifactId: string) =>
    requestBlob(
      `/api/attempts/${encodeURIComponent(attemptId)}/artifacts/${encodeURIComponent(artifactId)}/download`,
    ),
  createRunTargetFailureTriage: (runTargetId: string) =>
    request<RunTargetFailureTriage>(
      `/api/run-targets/${encodeURIComponent(runTargetId)}/failure-triage`,
      {
        method: "POST",
      },
    ),
  getLatestRunTargetFailureTriage: (runTargetId: string) =>
    request<RunTargetFailureTriage>(
      `/api/run-targets/${encodeURIComponent(runTargetId)}/failure-triage/latest`,
    ),
};
