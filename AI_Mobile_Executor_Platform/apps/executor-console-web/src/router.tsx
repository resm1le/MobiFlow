import {
  Link,
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
  useNavigate,
} from "@tanstack/react-router";
import { useEffect } from "react";
import { LanguageSwitcher } from "./components/language-switcher";
import { useI18n } from "./lib/i18n";
import { AttemptsPage } from "./routes/attempts-page";
import { AttemptDetailPage } from "./routes/attempt-detail-page";
import { DeviceDetailPage } from "./routes/device-detail-page";
import { DevicePoolsPage } from "./routes/device-pools-page";
import { DevicesPage } from "./routes/devices-page";
import { AiRunPlanPage } from "./routes/ai-run-plan-page";
import { RunDetailPage } from "./routes/run-detail-page";
import { RunNewPage } from "./routes/run-new-page";
import { RunsPage } from "./routes/runs-page";
import { TaskDetailPage } from "./routes/task-detail-page";
import { TaskNewPage } from "./routes/task-new-page";
import { TasksPage } from "./routes/tasks-page";
import { API_BASE_URL } from "./lib/constants";

function RootLayout() {
  const { messages } = useI18n();

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand-block">
          <p>{messages.shell.brand}</p>
          <h1>{messages.shell.console}</h1>
        </div>
        <nav className="sidebar-nav">
          <Link className="nav-link" activeProps={{ className: "nav-link active" }} to="/devices">
            {messages.shell.navigation.devices}
          </Link>
          <Link className="nav-link" activeProps={{ className: "nav-link active" }} to="/tasks">
            {messages.shell.navigation.tasks}
          </Link>
          <Link
            className="nav-link"
            activeProps={{ className: "nav-link active" }}
            to="/device-pools"
          >
            {messages.shell.navigation.devicePools}
          </Link>
          <Link className="nav-link" activeProps={{ className: "nav-link active" }} to="/runs">
            {messages.shell.navigation.runs}
          </Link>
          <Link
            className="nav-link"
            activeProps={{ className: "nav-link active" }}
            to="/attempts"
          >
            {messages.shell.navigation.attempts}
          </Link>
          <Link
            className="nav-link"
            activeProps={{ className: "nav-link active" }}
            to="/ai/run-plans/new"
          >
            {messages.shell.navigation.aiRunPlanning}
          </Link>
        </nav>
        <LanguageSwitcher />
        <div className="env-card">
          <span>{messages.shell.controlApi}</span>
          <strong>{API_BASE_URL}</strong>
        </div>
      </aside>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

function IndexRedirect() {
  const navigate = useNavigate();
  useEffect(() => {
    void navigate({ to: "/devices" });
  }, [navigate]);
  return null;
}

function LegacyAiTaskPlanRedirect() {
  const navigate = useNavigate();
  useEffect(() => {
    void navigate({ to: "/ai/run-plans/new" });
  }, [navigate]);
  return null;
}

const rootRoute = createRootRoute({
  component: RootLayout,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: IndexRedirect,
});

const devicesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/devices",
  component: DevicesPage,
});

const deviceDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/devices/$deviceId",
  component: DeviceDetailPage,
});

const tasksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tasks",
  component: TasksPage,
});

const devicePoolsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/device-pools",
  component: DevicePoolsPage,
});

const runsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs",
  component: RunsPage,
});

const runNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs/new",
  component: RunNewPage,
});

const runDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs/$runId",
  component: RunDetailPage,
});

const attemptsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/attempts",
  component: AttemptsPage,
});

const taskNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tasks/new",
  component: TaskNewPage,
});

const taskDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tasks/$taskId",
  component: TaskDetailPage,
});

const attemptDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/attempts/$attemptId",
  component: AttemptDetailPage,
});

const aiPlaceholderRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/ai/new-plan",
  component: LegacyAiTaskPlanRedirect,
});

const aiRunPlanRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/ai/run-plans/new",
  component: AiRunPlanPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  devicesRoute,
  deviceDetailRoute,
  devicePoolsRoute,
  tasksRoute,
  runsRoute,
  runNewRoute,
  runDetailRoute,
  attemptsRoute,
  taskNewRoute,
  taskDetailRoute,
  attemptDetailRoute,
  aiRunPlanRoute,
  aiPlaceholderRoute,
]);

export const router = createRouter({
  routeTree,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
