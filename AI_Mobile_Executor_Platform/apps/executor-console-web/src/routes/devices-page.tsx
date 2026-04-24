import { Link } from "@tanstack/react-router";
import { ResumeDeviceButton } from "../components/resume-device-button";
import { Badge, EmptyState, ErrorState, LoadingState, PageShell, Panel } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { useDevicesQuery } from "../lib/hooks";
import { formatMappedValue, useI18n } from "../lib/i18n";

export function DevicesPage() {
  const { messages } = useI18n();
  const query = useDevicesQuery();

  return (
    <PageShell title={messages.devices.title}>
      <Panel title={messages.devices.panelTitle} subtitle={messages.devices.panelSubtitle}>
        {query.isPending ? <LoadingState /> : null}
        {query.isError ? <ErrorState body={query.error.message} /> : null}
        {query.data && query.data.length === 0 ? (
          <EmptyState title={messages.devices.emptyTitle} body={messages.devices.emptyBody} />
        ) : null}
        {query.data && query.data.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{messages.devices.headers.device}</th>
                  <th>{messages.devices.headers.status}</th>
                  <th>{messages.devices.headers.busy}</th>
                  <th>{messages.devices.headers.attempt}</th>
                  <th>{messages.devices.headers.auth}</th>
                  <th>{messages.devices.headers.heartbeat}</th>
                  <th>{messages.devices.headers.profiles}</th>
                  <th>{messages.devices.headers.actions}</th>
                </tr>
              </thead>
              <tbody>
                {query.data.map((device) => (
                  <tr key={device.deviceId}>
                    <td>
                      <Link to="/devices/$deviceId" params={{ deviceId: device.deviceId }}>
                        {device.deviceId}
                      </Link>
                    </td>
                    <td>
                      <Badge tone={device.online ? "success" : "warning"}>
                        {formatMappedValue(
                          messages.enumLabels.deviceStatus,
                          device.status,
                          messages.common.notAvailable,
                        )}
                      </Badge>
                    </td>
                    <td>{device.busy ? messages.common.yes : messages.common.no}</td>
                    <td>{device.currentAttemptId ?? messages.common.notAvailable}</td>
                    <td>
                      <Badge tone={device.authConfigured ? "success" : "warning"}>
                        {device.authConfigured
                          ? messages.devices.configured
                          : messages.devices.devMode}
                      </Badge>
                    </td>
                    <td>{formatDateTime(device.lastHeartbeatAt, messages.locale)}</td>
                    <td className="wrap-cell">{device.installedProfiles.join(", ")}</td>
                    <td>
                      {device.status === "QUIESCED" ? (
                        <ResumeDeviceButton deviceId={device.deviceId} compact />
                      ) : (
                        messages.common.notAvailable
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Panel>
    </PageShell>
  );
}
