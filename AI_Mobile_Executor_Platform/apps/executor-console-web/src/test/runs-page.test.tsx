import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RunsPage } from "../routes/runs-page";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock("../lib/hooks", () => ({
  useRunsQuery: () => ({
    isPending: false,
    isError: false,
    data: [
      {
        runId: "run-1",
        name: "Maps batch",
        description: null,
        poolId: "pool-1",
        status: "RUNNING",
        finalState: null,
        taskType: "demo.navigate",
        profilePackage: "com.google.android.apps.maps",
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
    ],
  }),
}));

describe("RunsPage", () => {
  it("renders a run row", () => {
    const view = render(<RunsPage />);

    expect(view.getByText("Maps batch")).toBeInTheDocument();
    expect(view.getByText("run-1")).toBeInTheDocument();
    expect(view.getByText("com.google.android.apps.maps")).toBeInTheDocument();
  });
});
