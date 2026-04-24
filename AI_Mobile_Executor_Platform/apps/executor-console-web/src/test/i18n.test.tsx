import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LanguageSwitcher } from "../components/language-switcher";
import { I18nProvider } from "../lib/i18n";
import { DevicesPage } from "../routes/devices-page";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock("../lib/hooks", () => ({
  useDevicesQuery: () => ({
    isPending: false,
    isError: false,
    data: [
      {
        deviceId: "device-1",
        protocolVersion: "v1",
        executorVersion: "1.0",
        brand: "google",
        model: "Pixel 6",
        androidVersion: "13",
        screenWidth: 1080,
        screenHeight: 2400,
        status: "ONLINE",
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
        lastCommand: null,
        authConfigured: true,
        health: {},
        updatedAt: 0,
      },
    ],
  }),
  useResumeDeviceMutation: () => ({
    isPending: false,
    isError: false,
    isSuccess: false,
    mutate: vi.fn(),
  }),
}));

describe("I18nProvider", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("defaults to Chinese when the browser language is zh-CN", () => {
    const original = window.navigator.language;
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: "zh-CN",
    });

    const view = render(
      <I18nProvider>
        <DevicesPage />
      </I18nProvider>,
    );

    expect(view.getByRole("heading", { name: "\u8bbe\u5907" })).toBeInTheDocument();
    expect(view.getByText("\u5728\u7ebf | ONLINE")).toBeInTheDocument();

    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: original,
    });
  });

  it("switches from English to Chinese and persists the choice", async () => {
    const user = userEvent.setup();

    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: "en-US",
    });

    const view = render(
      <I18nProvider>
        <LanguageSwitcher />
        <DevicesPage />
      </I18nProvider>,
    );

    expect(view.getByRole("heading", { name: "Devices" })).toBeInTheDocument();

    await user.click(view.getByRole("button", { name: "Chinese" }));

    expect(view.getByRole("heading", { name: "\u8bbe\u5907" })).toBeInTheDocument();
    expect(window.localStorage.getItem("executor-console-language")).toBe("zh");
  });
});
