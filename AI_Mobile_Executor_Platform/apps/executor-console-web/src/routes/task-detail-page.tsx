import { Link, useParams } from "@tanstack/react-router";
import {
  ErrorState,
  JsonBlock,
  KeyValueTable,
  LoadingState,
  PageShell,
  Panel,
} from "../components/ui";
import { formatDateTime } from "../lib/format";
import { useTaskQuery } from "../lib/hooks";
import { formatMappedValue, useI18n } from "../lib/i18n";

export function TaskDetailPage() {
  const { taskId } = useParams({ from: "/tasks/$taskId" });
  const { messages } = useI18n();
  const query = useTaskQuery(taskId);

  return (
    <PageShell title={messages.taskDetail.title(taskId)}>
      {query.isPending ? <LoadingState /> : null}
      {query.isError ? <ErrorState body={query.error.message} /> : null}
      {query.data ? (
        <div className="grid-two">
          <Panel title={messages.taskDetail.summary}>
            <KeyValueTable
              rows={[
                {
                  label: messages.taskDetail.fields.status,
                  value: formatMappedValue(
                    messages.enumLabels.taskStatus,
                    query.data.status,
                    messages.common.notAvailable,
                  ),
                },
                {
                  label: messages.taskDetail.fields.runId,
                  value: query.data.runId ? (
                    <Link to="/runs/$runId" params={{ runId: query.data.runId }}>
                      {query.data.runId}
                    </Link>
                  ) : (
                    messages.common.notAvailable
                  ),
                },
                {
                  label: messages.taskDetail.fields.runTargetId,
                  value: query.data.runTargetId ?? messages.common.notAvailable,
                },
                {
                  label: messages.taskDetail.fields.targetDeviceId,
                  value: query.data.targetDeviceId ?? messages.common.notAvailable,
                },
                { label: messages.taskDetail.fields.taskType, value: query.data.taskType },
                { label: messages.taskDetail.fields.profile, value: query.data.profilePackage },
                { label: messages.taskDetail.fields.priority, value: String(query.data.priority) },
                { label: messages.taskDetail.fields.source, value: query.data.source },
                {
                  label: messages.taskDetail.fields.created,
                  value: formatDateTime(query.data.createdAt, messages.locale),
                },
                {
                  label: messages.taskDetail.fields.updated,
                  value: formatDateTime(query.data.updatedAt, messages.locale),
                },
                {
                  label: messages.taskDetail.fields.idempotencyKey,
                  value: query.data.idempotencyKey ?? messages.common.notAvailable,
                },
              ]}
            />
          </Panel>
          <Panel title={messages.taskDetail.latestAttempt}>
            {query.data.latestAttempt ? (
              <KeyValueTable
                rows={[
                  {
                    label: messages.taskDetail.fields.attemptId,
                    value: (
                      <Link
                        to="/attempts/$attemptId"
                        params={{ attemptId: query.data.latestAttempt.attemptId }}
                      >
                        {query.data.latestAttempt.attemptId}
                      </Link>
                    ),
                  },
                  {
                    label: messages.taskDetail.fields.status,
                    value: formatMappedValue(
                      messages.enumLabels.attemptStatus,
                      query.data.latestAttempt.status,
                      messages.common.notAvailable,
                    ),
                  },
                  {
                    label: messages.taskDetail.fields.finalState,
                    value: query.data.latestAttempt.finalState
                      ? formatMappedValue(
                          messages.enumLabels.attemptStatus,
                          query.data.latestAttempt.finalState,
                          messages.common.notAvailable,
                        )
                      : messages.common.notAvailable,
                  },
                  {
                    label: messages.taskDetail.fields.failureReason,
                    value: query.data.latestAttempt.failureReason ?? messages.common.notAvailable,
                  },
                  {
                    label: messages.taskDetail.fields.leaseExpire,
                    value: formatDateTime(query.data.latestAttempt.leaseExpireAt, messages.locale),
                  },
                ]}
              />
            ) : (
              <p>{messages.taskDetail.noAttempt}</p>
            )}
          </Panel>
          <Panel title={messages.taskDetail.taskPayload}>
            <JsonBlock value={query.data.taskPayload} />
          </Panel>
          <Panel title={messages.taskDetail.runConfig}>
            <JsonBlock value={query.data.runConfig} />
          </Panel>
          <Panel title={messages.taskDetail.artifactPolicy}>
            <JsonBlock value={query.data.artifactPolicy} />
          </Panel>
          <Panel title={messages.taskDetail.labels}>
            <div className="chip-row">
              {query.data.labels.map((label) => (
                <span className="badge badge-neutral" key={label}>
                  {label}
                </span>
              ))}
            </div>
          </Panel>
        </div>
      ) : null}
    </PageShell>
  );
}
