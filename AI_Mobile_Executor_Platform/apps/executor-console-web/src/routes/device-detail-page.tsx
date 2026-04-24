import { Link, useParams } from "@tanstack/react-router";
import { DeviceCommandForm } from "../components/device-command-form";
import { ResumeDeviceButton } from "../components/resume-device-button";
import {
  EmptyState,
  ErrorState,
  JsonBlock,
  KeyValueTable,
  LoadingState,
  PageShell,
  Panel,
} from "../components/ui";
import { formatDateTime } from "../lib/format";
import { useDeviceAttemptsQuery, useDeviceQuery } from "../lib/hooks";
import { formatMappedValue, useI18n } from "../lib/i18n";

export function DeviceDetailPage() {
  const { deviceId } = useParams({ from: "/devices/$deviceId" });
  const { messages } = useI18n();
  const deviceQuery = useDeviceQuery(deviceId);
  const attemptsQuery = useDeviceAttemptsQuery(deviceId);

  return (
    <PageShell
      title={messages.deviceDetail.title(deviceId)}
      actions={
        deviceQuery.data?.status === "QUIESCED" ? (
          <ResumeDeviceButton deviceId={deviceId} />
        ) : null
      }
    >
      {deviceQuery.isPending ? <LoadingState /> : null}
      {deviceQuery.isError ? <ErrorState body={deviceQuery.error.message} /> : null}
      {deviceQuery.data ? (
        <div className="grid-two">
          <Panel title={messages.deviceDetail.runtime}>
            <KeyValueTable
              rows={[
                {
                  label: messages.deviceDetail.fields.status,
                  value: formatMappedValue(
                    messages.enumLabels.deviceStatus,
                    deviceQuery.data.status,
                    messages.common.notAvailable,
                  ),
                },
                {
                  label: messages.deviceDetail.fields.online,
                  value: deviceQuery.data.online ? messages.common.yes : messages.common.no,
                },
                {
                  label: messages.deviceDetail.fields.busy,
                  value: deviceQuery.data.busy ? messages.common.yes : messages.common.no,
                },
                {
                  label: messages.deviceDetail.fields.currentTask,
                  value: deviceQuery.data.currentTaskId ?? messages.common.notAvailable,
                },
                {
                  label: messages.deviceDetail.fields.currentAttempt,
                  value: deviceQuery.data.currentAttemptId ?? messages.common.notAvailable,
                },
                {
                  label: messages.deviceDetail.fields.lastHeartbeat,
                  value: formatDateTime(deviceQuery.data.lastHeartbeatAt, messages.locale),
                },
                {
                  label: messages.deviceDetail.fields.leaseExpire,
                  value: formatDateTime(deviceQuery.data.leaseExpireAt, messages.locale),
                },
                {
                  label: messages.deviceDetail.fields.lastCommand,
                  value: deviceQuery.data.lastCommand
                    ? formatMappedValue(
                        messages.enumLabels.commandType,
                        deviceQuery.data.lastCommand,
                        messages.common.notAvailable,
                      )
                    : messages.common.notAvailable,
                },
                {
                  label: messages.deviceDetail.fields.authConfigured,
                  value: deviceQuery.data.authConfigured ? messages.common.yes : messages.common.no,
                },
              ]}
            />
          </Panel>
          <Panel title={messages.deviceDetail.staticProfile}>
            <KeyValueTable
              rows={[
                {
                  label: messages.deviceDetail.fields.model,
                  value: `${deviceQuery.data.brand} ${deviceQuery.data.model}`,
                },
                { label: messages.deviceDetail.fields.android, value: deviceQuery.data.androidVersion },
                {
                  label: messages.deviceDetail.fields.display,
                  value: `${deviceQuery.data.screenWidth} x ${deviceQuery.data.screenHeight}`,
                },
                { label: messages.deviceDetail.fields.hostGroup, value: deviceQuery.data.hostGroup },
                {
                  label: messages.deviceDetail.fields.tags,
                  value: deviceQuery.data.tags.join(", ") || messages.common.notAvailable,
                },
                {
                  label: messages.deviceDetail.fields.profiles,
                  value:
                    deviceQuery.data.installedProfiles.join(", ") || messages.common.notAvailable,
                },
              ]}
            />
          </Panel>
          <Panel title={messages.deviceDetail.healthJson}>
            <JsonBlock value={deviceQuery.data.health} />
          </Panel>
          <Panel title={messages.deviceDetail.capabilitiesJson}>
            <JsonBlock value={deviceQuery.data.health?.capabilities ?? {}} />
          </Panel>
          <Panel
            title={messages.deviceDetail.deviceCommands}
            subtitle={messages.deviceDetail.deviceCommandsSubtitle}
          >
            <DeviceCommandForm
              deviceId={deviceId}
              currentAttemptId={deviceQuery.data.currentAttemptId}
            />
          </Panel>
          <Panel title={messages.deviceDetail.attempts}>
            {attemptsQuery.isPending ? <LoadingState /> : null}
            {attemptsQuery.isError ? <ErrorState body={attemptsQuery.error.message} /> : null}
            {attemptsQuery.data && attemptsQuery.data.length === 0 ? (
              <EmptyState
                title={messages.deviceDetail.emptyAttemptsTitle}
                body={messages.deviceDetail.emptyAttemptsBody}
              />
            ) : null}
            {attemptsQuery.data && attemptsQuery.data.length > 0 ? (
              <div className="stack-sm">
                {attemptsQuery.data.map((attempt) => (
                  <Link
                    key={attempt.attemptId}
                    className="list-card"
                    to="/attempts/$attemptId"
                    params={{ attemptId: attempt.attemptId }}
                  >
                    <strong>{attempt.attemptId}</strong>
                    <span>
                      {formatMappedValue(
                        messages.enumLabels.attemptStatus,
                        attempt.status,
                        messages.common.notAvailable,
                      )}
                    </span>
                    <span>{attempt.taskId}</span>
                    <span>{formatDateTime(attempt.updatedAt, messages.locale)}</span>
                  </Link>
                ))}
              </div>
            ) : null}
          </Panel>
        </div>
      ) : null}
    </PageShell>
  );
}
