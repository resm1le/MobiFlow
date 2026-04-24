import { Link } from "@tanstack/react-router";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageShell,
  Panel,
  SuccessState,
} from "../components/ui";
import { formatDateTime } from "../lib/format";
import { useCancelTaskMutation, useTasksQuery } from "../lib/hooks";
import { formatMappedValue, useI18n } from "../lib/i18n";

export function TasksPage() {
  const { messages } = useI18n();
  const tasksQuery = useTasksQuery();
  const cancelMutation = useCancelTaskMutation();

  return (
    <PageShell
      title={messages.tasks.title}
      actions={
        <Link className="button-primary" to="/tasks/new">
          {messages.tasks.newTask}
        </Link>
      }
    >
      <Panel title={messages.tasks.panelTitle} subtitle={messages.tasks.panelSubtitle}>
        {tasksQuery.isPending ? <LoadingState /> : null}
        {tasksQuery.isError ? <ErrorState body={tasksQuery.error.message} /> : null}
        {cancelMutation.isError ? <ErrorState body={cancelMutation.error.message} /> : null}
        {cancelMutation.isSuccess ? <SuccessState body={messages.tasks.cancelAccepted} /> : null}
        {tasksQuery.data && tasksQuery.data.length === 0 ? (
          <EmptyState title={messages.tasks.emptyTitle} body={messages.tasks.emptyBody} />
        ) : null}
        {tasksQuery.data && tasksQuery.data.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{messages.tasks.headers.task}</th>
                  <th>{messages.tasks.headers.runId}</th>
                  <th>{messages.tasks.headers.type}</th>
                  <th>{messages.tasks.headers.profile}</th>
                  <th>{messages.tasks.headers.status}</th>
                  <th>{messages.tasks.headers.priority}</th>
                  <th>{messages.tasks.headers.source}</th>
                  <th>{messages.tasks.headers.created}</th>
                  <th>{messages.tasks.headers.latestAttempt}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {tasksQuery.data.map((task) => (
                  <tr key={task.taskId}>
                    <td>
                      <Link to="/tasks/$taskId" params={{ taskId: task.taskId }}>
                        {task.taskId}
                      </Link>
                    </td>
                    <td>
                      {task.runId ? (
                        <Link to="/runs/$runId" params={{ runId: task.runId }}>
                          {task.runId}
                        </Link>
                      ) : (
                        messages.common.notAvailable
                      )}
                    </td>
                    <td>{task.taskType}</td>
                    <td className="wrap-cell">{task.profilePackage}</td>
                    <td>
                      {formatMappedValue(
                        messages.enumLabels.taskStatus,
                        task.status,
                        messages.common.notAvailable,
                      )}
                    </td>
                    <td>{task.priority}</td>
                    <td>{task.source}</td>
                    <td>{formatDateTime(task.createdAt, messages.locale)}</td>
                    <td>
                      {task.latestAttempt ? (
                        <Link
                          to="/attempts/$attemptId"
                          params={{ attemptId: task.latestAttempt.attemptId }}
                        >
                          {formatMappedValue(
                            messages.enumLabels.attemptStatus,
                            task.latestAttempt.status,
                            messages.common.notAvailable,
                          )}
                        </Link>
                      ) : (
                        messages.common.notAvailable
                      )}
                    </td>
                    <td>
                      <button
                        className="button-secondary"
                        type="button"
                        onClick={() => cancelMutation.mutate(task.taskId)}
                        disabled={
                          cancelMutation.isPending ||
                          !["QUEUED", "RUNNING"].includes(task.status)
                        }
                      >
                        {messages.tasks.cancel}
                      </button>
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
