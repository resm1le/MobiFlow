import type { CreateTaskRequest } from "./types";

export const API_BASE_URL =
  import.meta.env.VITE_CONTROL_API_BASE_URL ?? "http://127.0.0.1:8080";

export const DEFAULT_QUERY_INTERVAL_MS = 15_000;
export const AI_PLAN_CREATED_BY = "console-ai";

export const PROFILE_OPTIONS = [
  "com.google.android.apps.maps",
  "com.zhiliaoapp.musically",
  "com.zzkko",
] as const;

export const DEFAULT_TASK_FORM: CreateTaskRequest = {
  taskType: "demo.navigate",
  profilePackage: "com.google.android.apps.maps",
  priority: 100,
  source: "console",
  labels: ["demo", "manual"],
  taskPayload: {
    target: "Shanghai Tower",
    mode: "driving",
  },
  runConfig: {
    loopCount: 1,
    budgetMs: 240000,
    loopIntervalMs: 0,
    networkIsolationEnabled: false,
    pollIntervalMs: 15000,
    heartbeatIntervalMs: 30000,
  },
  artifactPolicy: {
    uploadLog: true,
    uploadScreenshot: true,
    uploadDump: true,
  },
  idempotencyKey: null,
};

export const DEFAULT_AI_CONSTRAINTS = {};
