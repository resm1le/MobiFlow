import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AttemptsPage } from "../routes/attempts-page";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock("../lib/hooks", () => ({
  useAttemptsQuery: () => ({
    isPending: false,
    isError: false,
    data: [
      {
        attemptId: "attempt-1",
        taskId: "task-1",
        deviceId: "dev-1",
        status: "RUNNING",
        finalState: null,
        failureReason: null,
        runId: "run-1",
        leaseExpireAt: "2026-03-20T11:00:00Z",
        claimedAt: "2026-03-20T10:00:00Z",
        startedAt: "2026-03-20T10:01:00Z",
        finishedAt: null,
        createdAt: "2026-03-20T10:00:00Z",
        updatedAt: "2026-03-20T10:05:00Z",
      },
    ],
  }),
}));

describe("AttemptsPage", () => {
  it("renders the attempts list", () => {
    const view = render(<AttemptsPage />);

    expect(view.getByText("attempt-1")).toBeInTheDocument();
    expect(view.getByText("task-1")).toBeInTheDocument();
    expect(view.getByText("dev-1")).toBeInTheDocument();
  });
});
