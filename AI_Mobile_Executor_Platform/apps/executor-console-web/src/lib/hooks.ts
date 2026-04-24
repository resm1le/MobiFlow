import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";
import { ApiError, controlApi } from "./api";
import { DEFAULT_QUERY_INTERVAL_MS } from "./constants";
import type {
  AiRunSummary,
  CreateAiRunPlanRequest,
  CreateAiRunPlanResponse,
  CreateDevicePoolRequest,
  CreateExperimentRunRequest,
  CreateTaskRequest,
  DeviceCommandResponse,
  DevicePool,
  DeviceDetail,
  ExperimentRunDetail,
  RunTargetFailureTriage,
  MaterializeAiRunPlanRequest,
  SendDeviceCommandRequest,
  TaskDetail,
} from "./types";

export const queryKeys = {
  devices: ["devices"] as const,
  device: (deviceId: string) => ["devices", deviceId] as const,
  deviceAttempts: (deviceId: string) => ["devices", deviceId, "attempts"] as const,
  devicePools: ["device-pools"] as const,
  tasks: ["tasks"] as const,
  task: (taskId: string) => ["tasks", taskId] as const,
  runs: ["runs"] as const,
  run: (runId: string) => ["runs", runId] as const,
  runSummaryLatest: (runId: string) => ["runs", runId, "summary", "latest"] as const,
  runTargetFailureTriageLatest: (runTargetId: string) =>
    ["run-targets", runTargetId, "failure-triage", "latest"] as const,
  attempts: ["attempts"] as const,
  attempt: (attemptId: string) => ["attempts", attemptId] as const,
  attemptEvents: (attemptId: string) => ["attempts", attemptId, "events"] as const,
  attemptArtifacts: (attemptId: string) =>
    ["attempts", attemptId, "artifacts"] as const,
};

export function useDevicesQuery() {
  return useQuery({
    queryKey: queryKeys.devices,
    queryFn: controlApi.listDevices,
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useDeviceQuery(deviceId: string) {
  return useQuery({
    queryKey: queryKeys.device(deviceId),
    queryFn: () => controlApi.getDevice(deviceId),
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useDeviceAttemptsQuery(deviceId: string) {
  return useQuery({
    queryKey: queryKeys.deviceAttempts(deviceId),
    queryFn: () => controlApi.listDeviceAttempts(deviceId),
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useDevicePoolsQuery() {
  return useQuery({
    queryKey: queryKeys.devicePools,
    queryFn: controlApi.listDevicePools,
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useTasksQuery() {
  return useQuery({
    queryKey: queryKeys.tasks,
    queryFn: controlApi.listTasks,
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useTaskQuery(taskId: string) {
  return useQuery({
    queryKey: queryKeys.task(taskId),
    queryFn: () => controlApi.getTask(taskId),
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useRunsQuery() {
  return useQuery({
    queryKey: queryKeys.runs,
    queryFn: controlApi.listRuns,
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useRunQuery(runId: string) {
  return useQuery({
    queryKey: queryKeys.run(runId),
    queryFn: () => controlApi.getRun(runId),
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useRunSummaryLatestQuery(runId: string, enabled = true) {
  return useQuery<AiRunSummary | null>({
    queryKey: queryKeys.runSummaryLatest(runId),
    queryFn: async () => {
      try {
        return await controlApi.getLatestRunSummary(runId);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          return null;
        }
        throw error;
      }
    },
    enabled,
    retry: false,
    refetchInterval: enabled ? DEFAULT_QUERY_INTERVAL_MS : false,
  });
}

export function useRunTargetFailureTriageLatestQuery(runTargetId: string, enabled = true) {
  return useQuery<RunTargetFailureTriage | null>({
    queryKey: queryKeys.runTargetFailureTriageLatest(runTargetId),
    queryFn: async () => {
      try {
        return await controlApi.getLatestRunTargetFailureTriage(runTargetId);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          return null;
        }
        throw error;
      }
    },
    enabled,
    retry: false,
    refetchInterval: enabled ? DEFAULT_QUERY_INTERVAL_MS : false,
  });
}

export function useAttemptsQuery() {
  return useQuery({
    queryKey: queryKeys.attempts,
    queryFn: controlApi.listAttempts,
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useAttemptQuery(attemptId: string) {
  return useQuery({
    queryKey: queryKeys.attempt(attemptId),
    queryFn: () => controlApi.getAttempt(attemptId),
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useAttemptEventsQuery(attemptId: string) {
  return useQuery({
    queryKey: queryKeys.attemptEvents(attemptId),
    queryFn: () => controlApi.listAttemptEvents(attemptId),
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useAttemptArtifactsQuery(attemptId: string) {
  return useQuery({
    queryKey: queryKeys.attemptArtifacts(attemptId),
    queryFn: () => controlApi.listAttemptArtifacts(attemptId),
    refetchInterval: DEFAULT_QUERY_INTERVAL_MS,
  });
}

export function useRunTargetFailureTriageMutation(): UseMutationResult<
  RunTargetFailureTriage,
  Error,
  string
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: controlApi.createRunTargetFailureTriage,
    onSuccess: async (triage, runTargetId) => {
      await queryClient.setQueryData(
        queryKeys.runTargetFailureTriageLatest(runTargetId),
        triage,
      );
    },
  });
}

export function useRunSummaryMutation(): UseMutationResult<
  AiRunSummary,
  Error,
  string
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: controlApi.createRunSummary,
    onSuccess: async (summary, runId) => {
      await queryClient.setQueryData(queryKeys.runSummaryLatest(runId), summary);
    },
  });
}

export function useCreateTaskMutation(): UseMutationResult<
  TaskDetail,
  Error,
  CreateTaskRequest
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: controlApi.createTask,
    onSuccess: (task) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tasks });
      void queryClient.setQueryData(queryKeys.task(task.taskId), task);
    },
  });
}

export function useCreateDevicePoolMutation(): UseMutationResult<
  DevicePool,
  Error,
  CreateDevicePoolRequest
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: controlApi.createDevicePool,
    onSuccess: async (pool) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.devicePools });
      queryClient.setQueryData(queryKeys.devicePools, (current: DevicePool[] | undefined) =>
        current ? [pool, ...current] : [pool],
      );
    },
  });
}

export function useCreateRunMutation(): UseMutationResult<
  ExperimentRunDetail,
  Error,
  CreateExperimentRunRequest
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: controlApi.createRun,
    onSuccess: async (run) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.runs });
      queryClient.setQueryData(queryKeys.run(run.run.runId), run);
    },
  });
}

export function useCreateAiRunPlanMutation(): UseMutationResult<
  CreateAiRunPlanResponse,
  Error,
  CreateAiRunPlanRequest
> {
  return useMutation({
    mutationFn: controlApi.createAiRunPlan,
  });
}

export function useMaterializeAiRunPlanMutation(): UseMutationResult<
  ExperimentRunDetail,
  Error,
  { requestId: string; body: MaterializeAiRunPlanRequest }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, body }) =>
      controlApi.materializeAiRunPlan(requestId, body),
    onSuccess: async (run) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.runs }),
        queryClient.setQueryData(queryKeys.run(run.run.runId), run),
      ]);
    },
  });
}

export function useCancelTaskMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: controlApi.cancelTask,
    onSuccess: async (_, taskId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks }),
        queryClient.invalidateQueries({ queryKey: queryKeys.task(taskId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.attempts }),
      ]);
    },
  });
}

export function useCancelRunMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: controlApi.cancelRun,
    onSuccess: async (_, runId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.runs }),
        queryClient.invalidateQueries({ queryKey: queryKeys.run(runId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks }),
        queryClient.invalidateQueries({ queryKey: queryKeys.attempts }),
      ]);
    },
  });
}

export function useSendDeviceCommandMutation(): UseMutationResult<
  DeviceCommandResponse,
  Error,
  { deviceId: string; body: SendDeviceCommandRequest }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId, body }) =>
      controlApi.sendDeviceCommand(deviceId, body),
    onSuccess: async (_, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.device(variables.deviceId),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.devices,
        }),
      ]);
    },
  });
}

export function useResumeDeviceMutation(): UseMutationResult<
  DeviceDetail,
  Error,
  string
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: controlApi.resumeDevice,
    onSuccess: async (_, deviceId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.devices }),
        queryClient.invalidateQueries({ queryKey: queryKeys.device(deviceId) }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.deviceAttempts(deviceId),
        }),
      ]);
    },
  });
}
