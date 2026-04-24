import { beforeEach, describe, expect, it, vi } from "vitest";
import { controlApi } from "../lib/api";

describe("controlApi", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("loads devices", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve('[{"deviceId":"dev-1","status":"ONLINE"}]'),
      }),
    );

    const devices = await controlApi.listDevices();
    expect(devices[0]?.deviceId).toBe("dev-1");
  });

  it("creates a task", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      text: () =>
        Promise.resolve(
          '{"taskId":"task-1","taskType":"demo.navigate","profilePackage":"com.google.android.apps.maps","status":"QUEUED","priority":1,"source":"console","createdAt":"2026-03-20T12:00:00Z","updatedAt":"2026-03-20T12:00:00Z","latestAttempt":null,"idempotencyKey":null,"labels":[],"taskPayload":{},"runConfig":{},"artifactPolicy":{}}',
        ),
    });
    vi.stubGlobal("fetch", fetchSpy);

    const task = await controlApi.createTask({
      taskType: "demo.navigate",
      profilePackage: "com.google.android.apps.maps",
      priority: 1,
      source: "console",
      labels: [],
      taskPayload: {},
      runConfig: {},
      artifactPolicy: {},
      idempotencyKey: null,
    });

    expect(task.taskId).toBe("task-1");
    expect(fetchSpy).toHaveBeenCalledOnce();
  });

  it("creates an AI run plan", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      text: () =>
        Promise.resolve(
          JSON.stringify({
            requestId: "run-plan-1",
            runDraft: {
              name: "AI run",
              description: "navigate to ikea",
              devicePoolId: "pool-1",
              taskType: "PLUGIN_RUN",
              profilePackage: "com.google.android.apps.maps",
              taskPayload: { goal: "navigate to ikea" },
              runConfig: {},
              artifactPolicy: {},
              priority: 100,
              labels: ["ai", "run-draft"],
              maxRetriesPerDevice: 0,
              queueTimeoutMs: 300000,
            },
            warnings: [],
            reviewHints: [],
            validation: { materializable: true, errors: [], warnings: [] },
            modelMeta: { provider: "stub" },
          }),
        ),
    });
    vi.stubGlobal("fetch", fetchSpy);

    const plan = await controlApi.createAiRunPlan({
      goal: "navigate to ikea",
      constraints: {},
    });

    expect(plan.requestId).toBe("run-plan-1");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/ai/run-plans"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("materializes an AI run plan into a run", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      text: () =>
        Promise.resolve(
          JSON.stringify({
            run: {
              runId: "run-2",
              name: "AI run",
              description: "navigate to ikea",
              poolId: "pool-1",
              status: "QUEUED",
              finalState: null,
              taskType: "PLUGIN_RUN",
              profilePackage: "com.google.android.apps.maps",
              priority: 100,
              labels: ["ai", "run-draft"],
              source: "ai-run-planning",
              createdBy: "console-ai",
              maxRetriesPerDevice: 0,
              queueTimeoutMs: 300000,
              cancelRequested: false,
              createdAt: 1,
              updatedAt: 1,
              startedAt: null,
              finishedAt: null,
              counts: {
                totalTargets: 1,
                queued: 1,
                running: 0,
                retryPending: 0,
                succeeded: 0,
                failed: 0,
                cancelled: 0,
              },
            },
            taskPayload: {},
            runConfig: {},
            artifactPolicy: {},
            targets: [],
          }),
        ),
    });
    vi.stubGlobal("fetch", fetchSpy);

    const run = await controlApi.materializeAiRunPlan("run-plan-1", {
      createdBy: "console-ai",
    });

    expect(run.run.runId).toBe("run-2");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/ai/run-plans/run-plan-1/materialize"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("creates run-target failure triage", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      text: () =>
        Promise.resolve(
          JSON.stringify({
            triageResultId: "triage-1",
            runTargetId: "target-1",
            result: {
              failureCategory: "UI_NOT_FOUND",
              probableCause: "Target never appeared.",
              confidence: 0.8,
              retryRecommendation: "RETRY_SAME_DEVICE",
              suggestedNextAction: "INSPECT_ARTIFACTS",
              operatorReviewHints: ["check screenshot"],
              evidence: ["lastError:ui target not found"],
            },
            validation: { valid: true, errors: [], warnings: [] },
            modelMeta: { provider: "stub" },
            generatedAt: 1770000000000,
          }),
        ),
    });
    vi.stubGlobal("fetch", fetchSpy);

    const triage = await controlApi.createRunTargetFailureTriage("target-1");

    expect(triage.triageResultId).toBe("triage-1");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/run-targets/target-1/failure-triage"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("loads latest run-target failure triage", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      text: () =>
        Promise.resolve(
          JSON.stringify({
            triageResultId: "triage-1",
            runTargetId: "target-1",
            result: {
              failureCategory: "QUEUE_TIMEOUT",
              probableCause: "Task timed out in queue.",
              confidence: 0.7,
              retryRecommendation: "RETRY_SAME_DEVICE",
              suggestedNextAction: "CHECK_CONTROL_PLANE",
              operatorReviewHints: ["check queue pressure"],
              evidence: ["failureReason:QUEUE_TIMEOUT"],
            },
            validation: { valid: false, errors: ["manual review"], warnings: [] },
            modelMeta: { provider: "stub" },
            generatedAt: 1770000001000,
          }),
        ),
    });
    vi.stubGlobal("fetch", fetchSpy);

    const triage = await controlApi.getLatestRunTargetFailureTriage("target-1");

    expect(triage.result.failureCategory).toBe("QUEUE_TIMEOUT");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/run-targets/target-1/failure-triage/latest"),
      expect.anything(),
    );
  });

  it("creates a run summary", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      text: () =>
        Promise.resolve(
          JSON.stringify({
            summaryId: "summary-1",
            runId: "run-1",
            result: {
              summaryText: "Run completed successfully.",
              keyMoments: [{ title: "Launch", eventType: "STEP", stepIndex: 1, message: "search" }],
              finalJudgement: "Healthy run.",
              evidence: ["targets:succeeded=1"],
            },
            validation: { valid: true, errors: [], warnings: [] },
            modelMeta: { provider: "stub" },
            generatedAt: 1770000002000,
          }),
        ),
    });
    vi.stubGlobal("fetch", fetchSpy);

    const summary = await controlApi.createRunSummary("run-1");

    expect(summary.summaryId).toBe("summary-1");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/runs/run-1/summary"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("resumes a quiesced device", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      text: () =>
        Promise.resolve(
          '{"deviceId":"dev-1","status":"ONLINE","online":true,"busy":false,"protocolVersion":"v1","executorVersion":"1.0","brand":"google","model":"Pixel 6","androidVersion":"13","screenWidth":1080,"screenHeight":2400,"hostGroup":"default","tags":[],"installedProfiles":[],"lastHeartbeatAt":0,"currentTaskId":null,"currentAttemptId":null,"currentTaskType":null,"configVersion":"cfg-v1","leaseExpireAt":null,"lastCommand":"QUIESCE","authConfigured":true,"health":{},"updatedAt":0,"registered":true}',
        ),
    });
    vi.stubGlobal("fetch", fetchSpy);

    const device = await controlApi.resumeDevice("dev-1");

    expect(device.status).toBe("ONLINE");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/devices/dev-1/resume"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("injects bearer token when configured", async () => {
    vi.stubEnv("VITE_CONTROL_API_BEARER_TOKEN", "secret-token");
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('[{"deviceId":"dev-1","status":"ONLINE"}]'),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await controlApi.listDevices();

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/devices"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer secret-token",
        }),
      }),
    );
  });

  it("loads runs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        text: () =>
          Promise.resolve(
            '[{"runId":"run-1","name":"Maps batch","description":null,"poolId":"pool-1","status":"QUEUED","finalState":null,"taskType":"demo.navigate","profilePackage":"com.google.android.apps.maps","priority":100,"labels":[],"source":"console-run","createdBy":"console","maxRetriesPerDevice":0,"queueTimeoutMs":300000,"cancelRequested":false,"createdAt":1,"updatedAt":1,"startedAt":null,"finishedAt":null,"counts":{"totalTargets":2,"queued":2,"running":0,"retryPending":0,"succeeded":0,"failed":0,"cancelled":0}}]',
          ),
      }),
    );

    const runs = await controlApi.listRuns();
    expect(runs[0]?.runId).toBe("run-1");
  });

  it("creates a device pool", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      text: () =>
        Promise.resolve(
          '{"poolId":"pool-1","name":"Lab pool","description":null,"hostGroup":"default","deviceIds":[],"requiredTags":["lab"],"excludedTags":[],"createdBy":"console","createdAt":1,"updatedAt":1}',
        ),
    });
    vi.stubGlobal("fetch", fetchSpy);

    const pool = await controlApi.createDevicePool({
      name: "Lab pool",
      description: null,
      hostGroup: "default",
      deviceIds: [],
      requiredTags: ["lab"],
      excludedTags: [],
      createdBy: "console",
    });

    expect(pool.poolId).toBe("pool-1");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/device-pools"),
      expect.objectContaining({ method: "POST" }),
    );
  });
});
