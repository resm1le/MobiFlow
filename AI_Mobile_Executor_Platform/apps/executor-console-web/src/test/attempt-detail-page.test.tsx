import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AttemptDetailPage } from "../routes/attempt-detail-page";
import { controlApi } from "../lib/api";

vi.mock("@tanstack/react-router", async () => {
  return {
    Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
    useParams: () => ({ attemptId: "attempt-1" }),
  };
});

vi.mock("../lib/hooks", () => ({
  useAttemptQuery: () => ({
    isPending: false,
    isError: false,
    data: {
      attempt: {
        attemptId: "attempt-1",
        taskId: "task-1",
        deviceId: "dev-1",
        status: "RUNNING",
        finalState: null,
        failureReason: null,
        runId: "run-1",
        leaseExpireAt: 1710932400000,
        startedAt: 1710928860000,
        finishedAt: null,
        createdAt: 1710928800000,
        updatedAt: 1710929100000,
      },
      events: [],
      artifacts: [],
    },
  }),
  useAttemptEventsQuery: () => ({
    isPending: false,
    isError: false,
    data: [
      {
        id: 1,
        attemptId: "attempt-1",
        taskId: "task-1",
        deviceId: "dev-1",
        runId: "run-1",
        scenarioId: "scenario-1",
        stepIndex: 1,
        actionIndex: 1,
        eventType: "STEP",
        state: "RUNNING",
        code: null,
        message: "search",
        ts: 1710928920000,
      },
    ],
  }),
  useAttemptArtifactsQuery: () => ({
    isPending: false,
    isError: false,
    data: [
      {
        artifactId: "artifact-1",
        attemptId: "attempt-1",
        taskId: "task-1",
        runId: "run-1",
        artifactType: "SCREENSHOT",
        fileName: "screen.png",
        mimeType: "image/png",
        objectKey: "attempt-1/screen.png",
        downloadPath: "/api/attempts/attempt-1/artifacts/artifact-1/download",
        sizeBytes: 1234,
        createdAt: 1710928980000,
      },
    ],
  }),
}));

describe("AttemptDetailPage", () => {
  it("renders event and artifact metadata with download button", () => {
    const view = render(<AttemptDetailPage />);

    expect(view.getByText("attempt-1/screen.png")).toBeInTheDocument();
    expect(view.getByText("STEP")).toBeInTheDocument();
    expect(view.getByRole("button", { name: "Download" })).toBeInTheDocument();
  });

  it("points run-backed attempts to run diagnostics", async () => {
    const view = render(<AttemptDetailPage />);

    expect(view.getByText("AI diagnostics moved to run detail")).toBeInTheDocument();
    expect(view.getByText("View Run Diagnostics")).toBeInTheDocument();
  });

  it("downloads artifact through authenticated api request", async () => {
    const user = userEvent.setup();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(() => "blob:artifact"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
    const downloadSpy = vi.spyOn(controlApi, "downloadAttemptArtifact").mockResolvedValue(
      new Blob(["artifact"], { type: "image/png" }),
    );
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    const view = render(<AttemptDetailPage />);

    await user.click(view.getByRole("button", { name: "Download" }));

    expect(downloadSpy).toHaveBeenCalledWith("attempt-1", "artifact-1");
    expect(clickSpy).toHaveBeenCalled();

    downloadSpy.mockRestore();
    clickSpy.mockRestore();
  });
});
