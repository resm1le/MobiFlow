import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TasksPage } from "../routes/tasks-page";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock("../lib/hooks", () => ({
  useTasksQuery: () => ({
    isPending: false,
    isError: false,
    data: [
      {
        taskId: "task-1",
        taskType: "demo.navigate",
        profilePackage: "com.google.android.apps.maps",
        status: "QUEUED",
        priority: 100,
        source: "console",
        createdAt: "2026-03-20T10:00:00Z",
        updatedAt: "2026-03-20T10:00:00Z",
        latestAttempt: null,
      },
    ],
  }),
  useCancelTaskMutation: () => ({
    isPending: false,
    isError: false,
    mutate: vi.fn(),
  }),
}));

describe("TasksPage", () => {
  it("renders a task row", () => {
    const view = render(<TasksPage />);

    expect(view.getByText("task-1")).toBeInTheDocument();
    expect(view.getByText("com.google.android.apps.maps")).toBeInTheDocument();
  });
});
