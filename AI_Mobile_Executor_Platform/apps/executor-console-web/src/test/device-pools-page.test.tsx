import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DevicePoolsPage } from "../routes/device-pools-page";

vi.mock("../lib/hooks", () => ({
  useDevicePoolsQuery: () => ({
    isPending: false,
    isError: false,
    data: [
      {
        poolId: "pool-1",
        name: "Shanghai Android",
        description: "Tagged Shanghai devices",
        hostGroup: "default",
        deviceIds: ["device-1", "device-2"],
        requiredTags: ["shanghai"],
        excludedTags: ["busy-lab"],
        createdBy: "console",
        createdAt: 1710928800000,
        updatedAt: 1710929100000,
      },
    ],
  }),
  useCreateDevicePoolMutation: () => ({
    isPending: false,
    isError: false,
    isSuccess: false,
    mutate: vi.fn(),
  }),
}));

describe("DevicePoolsPage", () => {
  it("renders device pool data", () => {
    const view = render(<DevicePoolsPage />);

    expect(view.getByText("Shanghai Android")).toBeInTheDocument();
    expect(view.getByText("device-1, device-2")).toBeInTheDocument();
    expect(view.getByText("shanghai")).toBeInTheDocument();
  });
});
