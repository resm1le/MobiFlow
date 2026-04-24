import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AiRunPlanPage } from "../routes/ai-run-plan-page";

const createRunPlanMutate = vi.fn();
const materializeRunPlanMutate = vi.fn();
const navigate = vi.fn();

const createRunPlanState = {
  isPending: false,
  isError: false,
  error: null,
  reset: vi.fn(),
};

const materializeRunPlanState = {
  isPending: false,
  isError: false,
  error: null,
  reset: vi.fn(),
};

vi.mock("@tanstack/react-router", async () => {
  return {
    Link: ({ children }: { children: ReactNode }) => <span>{children}</span>,
    useNavigate: () => navigate,
  };
});

vi.mock("../lib/hooks", () => ({
  useCreateAiRunPlanMutation: () => ({
    ...createRunPlanState,
    mutate: createRunPlanMutate,
  }),
  useMaterializeAiRunPlanMutation: () => ({
    ...materializeRunPlanState,
    mutate: materializeRunPlanMutate,
  }),
}));

describe("AiRunPlanPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createRunPlanState.isPending = false;
    createRunPlanState.isError = false;
    createRunPlanState.error = null;
    materializeRunPlanState.isPending = false;
    materializeRunPlanState.isError = false;
    materializeRunPlanState.error = null;
  });

  it("renders the run-planning form", () => {
    const view = render(<AiRunPlanPage />);

    expect(view.getByLabelText("Goal")).toBeInTheDocument();
    expect(view.getByLabelText("Constraints JSON")).toBeInTheDocument();
    expect(view.getByRole("button", { name: "Create Run Plan" })).toBeInTheDocument();
  });

  it("shows run-plan review after create succeeds", async () => {
    const user = userEvent.setup();
    createRunPlanMutate.mockImplementation((_variables, options) => {
      options?.onSuccess?.({
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
        warnings: ["soft warning"],
        reviewHints: ["review pool"],
        validation: { materializable: true, errors: [], warnings: ["validation warning"] },
        modelMeta: { provider: "stub" },
      });
    });

    const view = render(<AiRunPlanPage />);

    await user.type(view.getByLabelText("Goal"), "navigate to ikea");
    await user.click(view.getByRole("button", { name: "Create Run Plan" }));

    expect(createRunPlanMutate).toHaveBeenCalledOnce();
    expect(view.getByText("Run-plan review")).toBeInTheDocument();
    expect(view.getByText("run-plan-1")).toBeInTheDocument();
    expect(view.getByText("pool-1")).toBeInTheDocument();
    expect(view.getByText(/review pool/i)).toBeInTheDocument();
    expect(view.getByRole("button", { name: "Materialize Run" })).toBeEnabled();
  });

  it("disables run materialization when validation blocks it", async () => {
    const user = userEvent.setup();
    createRunPlanMutate.mockImplementation((_variables, options) => {
      options?.onSuccess?.({
        requestId: "run-plan-2",
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
          labels: ["ai"],
          maxRetriesPerDevice: 0,
          queueTimeoutMs: 300000,
        },
        warnings: [],
        reviewHints: [],
        validation: { materializable: false, errors: ["profile drift"], warnings: [] },
        modelMeta: { provider: "stub" },
      });
    });

    const view = render(<AiRunPlanPage />);

    await user.type(view.getByLabelText("Goal"), "navigate to ikea");
    await user.click(view.getByRole("button", { name: "Create Run Plan" }));

    expect(view.getByRole("button", { name: "Materialize Run" })).toBeDisabled();
    expect(view.getByText(/profile drift/i)).toBeInTheDocument();
  });

  it("materializes through the fixed control-plane actor and navigates to run detail", async () => {
    const user = userEvent.setup();
    createRunPlanMutate.mockImplementation((_variables, options) => {
      options?.onSuccess?.({
        requestId: "run-plan-3",
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
      });
    });
    materializeRunPlanMutate.mockImplementation((_variables, options) => {
      options?.onSuccess?.({
        run: { runId: "run-3" },
      });
    });

    const view = render(<AiRunPlanPage />);

    await user.type(view.getByLabelText("Goal"), "navigate to ikea");
    await user.click(view.getByRole("button", { name: "Create Run Plan" }));
    await user.click(view.getByRole("button", { name: "Materialize Run" }));

    expect(materializeRunPlanMutate).toHaveBeenCalledWith(
      {
        requestId: "run-plan-3",
        body: { createdBy: "console-ai" },
      },
      expect.any(Object),
    );
    expect(navigate).toHaveBeenCalledWith({
      to: "/runs/$runId",
      params: { runId: "run-3" },
    });
  });
});
