import { Link } from "@tanstack/react-router";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageShell,
  Panel,
} from "../components/ui";
import { formatDateTime } from "../lib/format";
import { useAttemptsQuery } from "../lib/hooks";
import { formatMappedValue, useI18n } from "../lib/i18n";

export function AttemptsPage() {
  const { messages } = useI18n();
  const attemptsQuery = useAttemptsQuery();

  return (
    <PageShell title={messages.attempts.title}>
      <Panel title={messages.attempts.panelTitle} subtitle={messages.attempts.panelSubtitle}>
        {attemptsQuery.isPending ? <LoadingState /> : null}
        {attemptsQuery.isError ? <ErrorState body={attemptsQuery.error.message} /> : null}
        {attemptsQuery.data && attemptsQuery.data.length === 0 ? (
          <EmptyState title={messages.attempts.emptyTitle} body={messages.attempts.emptyBody} />
        ) : null}
        {attemptsQuery.data && attemptsQuery.data.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{messages.attempts.headers.attempt}</th>
                  <th>{messages.attempts.headers.task}</th>
                  <th>{messages.attempts.headers.device}</th>
                  <th>{messages.attempts.headers.status}</th>
                  <th>{messages.attempts.headers.finalState}</th>
                  <th>{messages.attempts.headers.failure}</th>
                  <th>{messages.attempts.headers.runId}</th>
                  <th>{messages.attempts.headers.updated}</th>
                </tr>
              </thead>
              <tbody>
                {attemptsQuery.data.map((attempt) => (
                  <tr key={attempt.attemptId}>
                    <td>
                      <Link
                        to="/attempts/$attemptId"
                        params={{ attemptId: attempt.attemptId }}
                      >
                        {attempt.attemptId}
                      </Link>
                    </td>
                    <td>
                      <Link to="/tasks/$taskId" params={{ taskId: attempt.taskId }}>
                        {attempt.taskId}
                      </Link>
                    </td>
                    <td>
                      <Link
                        to="/devices/$deviceId"
                        params={{ deviceId: attempt.deviceId }}
                      >
                        {attempt.deviceId}
                      </Link>
                    </td>
                    <td>
                      {formatMappedValue(
                        messages.enumLabels.attemptStatus,
                        attempt.status,
                        messages.common.notAvailable,
                      )}
                    </td>
                    <td>
                      {attempt.finalState
                        ? formatMappedValue(
                            messages.enumLabels.attemptStatus,
                            attempt.finalState,
                            messages.common.notAvailable,
                          )
                        : messages.common.notAvailable}
                    </td>
                    <td className="wrap-cell">
                      {attempt.failureReason ?? messages.common.notAvailable}
                    </td>
                    <td>
                      {attempt.runId ? (
                        <Link to="/runs/$runId" params={{ runId: attempt.runId }}>
                          {attempt.runId}
                        </Link>
                      ) : (
                        messages.common.notAvailable
                      )}
                    </td>
                    <td>{formatDateTime(attempt.updatedAt, messages.locale)}</td>
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
