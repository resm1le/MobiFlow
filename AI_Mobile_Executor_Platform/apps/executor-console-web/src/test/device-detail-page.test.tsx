import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DeviceDetailPage } from "../routes/device-detail-page";

const mutate = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  useParams: () => ({ deviceId: "device-1" }),
}));

vi.mock("../components/device-command-form", () => ({
  DeviceCommandForm: () => <div>DeviceCommandForm</div>,
}));

vi.mock("../lib/hooks", () => ({
  useDeviceQuery: () => ({
    isPending: false,
    isError: false,
    data: {
      deviceId: "device-1",
      protocolVersion: "v1",
      executorVersion: "1.0",
      brand: "google",
      model: "Pixel 6",
      androidVersion: "13",
      screenWidth: 1080,
      screenHeight: 2400,
      status: "QUIESCED",
      registered: true,
      online: true,
      busy: false,
      hostGroup: "default",
      tags: [],
      installedProfiles: ["com.google.android.apps.maps"],
      lastHeartbeatAt: 0,
      currentTaskId: null,
      currentAttemptId: null,
      currentTaskType: null,
      configVersion: "cfg-v1",
      leaseExpireAt: null,
      lastCommand: "QUIESCE",
      authConfigured: true,
      health: { capabilities: {} },
      updatedAt: 0,
    },
  }),
  useDeviceAttemptsQuery: () => ({
    isPending: false,
    isError: false,
    data: [],
  }),
  useResumeDeviceMutation: () => ({
    isPending: false,
    isError: false,
    isSuccess: false,
    mutate,
  }),
}));

describe("DeviceDetailPage", () => {
  it("shows resume action for a quiesced device detail view", async () => {
    const user = userEvent.setup();
    const view = render(<DeviceDetailPage />);

    await user.click(view.getByRole("button", { name: "Resume" }));

    expect(mutate).toHaveBeenCalledWith("device-1");
  });
});
