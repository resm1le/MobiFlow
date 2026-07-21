import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RunDetailPage } from "../routes/run-detail-page";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  useParams: () => ({ runId: "run-1" }),
}));

vi.mock("../lib/hooks", () => ({
  useRunQuery: () => ({
    isPending: false,
    isError: false,
    data: {
      run: {
        runId: "run-1",
        name: "Maps batch",
        description: "Batch run",
        poolId: null,
        status: "RUNNING",
        finalState: null,
        taskType: "demo.navigate",
        profilePackage: null,
        priority: 100,
        labels: ["demo"],
        source: "console-run",
        createdBy: "console",
        maxRetriesPerDevice: 1,
        queueTimeoutMs: 300000,
        cancelRequested: false,
        createdAt: 1710928800000,
        updatedAt: 1710929100000,
        startedAt: 1710928860000,
        finishedAt: null,
        counts: {
          totalTargets: 2,
          queued: 0,
          running: 1,
          retryPending: 0,
          succeeded: 1,
          failed: 0,
          cancelled: 0,
        },
      },
      taskPayload: { target: "Shanghai Tower" },
      runConfig: { loopCount: 1 },
      artifactPolicy: { uploadLog: true },
      targets: [
        {
          runTargetId: "target-1",
          sequenceId: null,
          deviceId: "device-1",
          status: "RUNNING",
          attemptCount: 1,
          currentTaskId: "task-1",
          latestAttemptId: "attempt-1",
          failureReason: null,
          startedAt: 1710928860000,
          finishedAt: null,
          task: {
            taskId: "task-1",
            runId: "run-1",
            runTargetId: "target-1",
            targetDeviceId: "device-1",
            taskType: "demo.navigate",
            profilePackage: "com.google.android.apps.maps",
            status: "RUNNING",
            priority: 100,
            source: "console-run",
            createdAt: 1710928800000,
            updatedAt: 1710929100000,
            latestAttempt: null,
            idempotencyKey: "idem-1",
            labels: ["demo"],
            taskPayload: {},
            runConfig: {},
            artifactPolicy: {},
          },
          latestAttempt: {
            attemptId: "attempt-1",
            taskId: "task-1",
            deviceId: "device-1",
            status: "RUNNING",
            finalState: null,
            failureReason: null,
            runId: "run-1",
            leaseExpireAt: 1710929400000,
            startedAt: 1710928860000,
            finishedAt: null,
            createdAt: 1710928800000,
            updatedAt: 1710929100000,
          },
        },
      ],
    },
  }),
  useCancelRunMutation: () => ({
    isPending: false,
    isError: false,
    mutate: vi.fn(),
  }),
  useRunSummaryLatestQuery: () => ({
    isPending: false,
    isError: false,
    data: {
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
      generatedAt: 1710929200000,
    },
    error: null,
    refetch: vi.fn(),
  }),
  useRunSummaryMutation: () => ({
    isPending: false,
    isError: false,
    data: null,
    error: null,
    mutate: vi.fn(),
  }),
  useRunTargetFailureTriageLatestQuery: () => ({
    isPending: false,
    isError: false,
    data: null,
    error: null,
    refetch: vi.fn(),
  }),
  useRunTargetFailureTriageMutation: () => ({
    isPending: false,
    isError: false,
    data: null,
    error: null,
    mutate: vi.fn(),
  }),
}));

describe("RunDetailPage", () => {
  it("renders target rows", () => {
    const view = render(<RunDetailPage />);

    expect(view.getByText("Maps batch")).toBeInTheDocument();
    expect(view.getByText("AI Run Summary")).toBeInTheDocument();
    expect(view.getByText("Run completed successfully.")).toBeInTheDocument();
    expect(view.getByText("device-1")).toBeInTheDocument();
    expect(view.getByText("task-1")).toBeInTheDocument();
    expect(view.getByText("attempt-1")).toBeInTheDocument();
    expect(view.getByText("Triage")).toBeInTheDocument();
    expect(view.getAllByText("—")).toHaveLength(2);
  });
});
