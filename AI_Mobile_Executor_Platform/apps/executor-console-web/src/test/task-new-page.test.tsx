import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TaskNewPage } from "../routes/task-new-page";

const mutate = vi.fn();
const navigate = vi.fn();

vi.mock("@tanstack/react-router", async () => {
  return {
    Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
    useNavigate: () => navigate,
  };
});

vi.mock("../lib/hooks", () => ({
  useCreateTaskMutation: () => ({
    isPending: false,
    isError: false,
    mutate,
  }),
}));

describe("TaskNewPage", () => {
  it("submits a manual task", async () => {
    const user = userEvent.setup();
    const view = render(<TaskNewPage />);

    await user.clear(view.getByLabelText("Task Type"));
    await user.type(view.getByLabelText("Task Type"), "demo.navigate");
    await user.click(view.getByRole("button", { name: "Create Task" }));

    expect(mutate).toHaveBeenCalledOnce();
  });
});
