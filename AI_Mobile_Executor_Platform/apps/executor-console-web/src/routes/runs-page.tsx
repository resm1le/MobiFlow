import { Link } from "@tanstack/react-router";
import { EmptyState, ErrorState, LoadingState, PageShell, Panel } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { useRunsQuery } from "../lib/hooks";
import { formatMappedValue, useI18n } from "../lib/i18n";

function formatCounts(total: number, succeeded: number, failed: number, cancelled: number) {
  return `${total} / ${succeeded} / ${failed} / ${cancelled}`;
}

export function RunsPage() {
  const { messages } = useI18n();
  const runsQuery = useRunsQuery();

  return (
    <PageShell
      title={messages.runs.title}
      actions={
        <Link className="button-primary" to="/runs/new">
          {messages.runs.newRun}
        </Link>
      }
    >
      <Panel title={messages.runs.panelTitle} subtitle={messages.runs.panelSubtitle}>
        {runsQuery.isPending ? <LoadingState /> : null}
        {runsQuery.isError ? <ErrorState body={runsQuery.error.message} /> : null}
        {runsQuery.data && runsQuery.data.length === 0 ? (
          <EmptyState title={messages.runs.emptyTitle} body={messages.runs.emptyBody} />
        ) : null}
        {runsQuery.data && runsQuery.data.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{messages.runs.headers.run}</th>
                  <th>{messages.runs.headers.status}</th>
                  <th>{messages.runs.headers.finalState}</th>
                  <th>{messages.runs.headers.pool}</th>
                  <th>{messages.runs.headers.type}</th>
                  <th>{messages.runs.headers.profile}</th>
                  <th>{messages.runs.headers.priority}</th>
                  <th>{messages.runs.headers.counts}</th>
                  <th>{messages.runs.headers.created}</th>
                </tr>
              </thead>
              <tbody>
                {runsQuery.data.map((run) => (
                  <tr key={run.runId}>
                    <td className="wrap-cell">
                      <Link to="/runs/$runId" params={{ runId: run.runId }}>
                        {run.name}
                      </Link>
                      <div>{run.runId}</div>
                    </td>
                    <td>
                      {formatMappedValue(
                        messages.enumLabels.runStatus,
                        run.status,
                        messages.common.notAvailable,
                      )}
                    </td>
                    <td>
                      {run.finalState
                        ? formatMappedValue(
                            messages.enumLabels.runFinalState,
                            run.finalState,
                            messages.common.notAvailable,
                          )
                        : messages.common.notAvailable}
                    </td>
                    <td>{run.poolId}</td>
                    <td>{run.taskType}</td>
                    <td className="wrap-cell">{run.profilePackage}</td>
                    <td>{run.priority}</td>
                    <td>
                      {formatCounts(
                        run.counts.totalTargets,
                        run.counts.succeeded,
                        run.counts.failed,
                        run.counts.cancelled,
                      )}
                    </td>
                    <td>{formatDateTime(run.createdAt, messages.locale)}</td>
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
