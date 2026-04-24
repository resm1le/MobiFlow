import { useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import {
  EmptyState,
  ErrorState,
  JsonBlock,
  KeyValueTable,
  LoadingState,
  PageShell,
  Panel,
  SuccessState,
} from "../components/ui";
import { formatDateTime } from "../lib/format";
import {
  useAttemptArtifactsQuery,
  useAttemptEventsQuery,
  useAttemptQuery,
} from "../lib/hooks";
import { ApiError, controlApi } from "../lib/api";
import { formatMappedValue, useI18n } from "../lib/i18n";

export function AttemptDetailPage() {
  const { attemptId } = useParams({ from: "/attempts/$attemptId" });
  const { messages } = useI18n();
  const attemptQuery = useAttemptQuery(attemptId);
  const eventsQuery = useAttemptEventsQuery(attemptId);
  const artifactsQuery = useAttemptArtifactsQuery(attemptId);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const attempt = attemptQuery.data?.attempt;
  const sortedEvents = [...(eventsQuery.data ?? [])].sort((left, right) => {
    const leftSequence = left.stepIndex ?? 0;
    const rightSequence = right.stepIndex ?? 0;
    if (leftSequence !== rightSequence) {
      return leftSequence - rightSequence;
    }
    return left.ts - right.ts;
  });

  return (
    <PageShell title={messages.attemptDetail.title(attemptId)}>
      {attemptQuery.isPending ? <LoadingState /> : null}
      {attemptQuery.isError ? <ErrorState body={attemptQuery.error.message} /> : null}
      {attempt ? (
        <div className="grid-two">
          <Panel title={messages.attemptDetail.summary}>
            <KeyValueTable
              rows={[
                {
                  label: messages.attemptDetail.fields.status,
                  value: formatMappedValue(
                    messages.enumLabels.attemptStatus,
                    attempt.status,
                    messages.common.notAvailable,
                  ),
                },
                {
                  label: messages.attemptDetail.fields.finalState,
                  value: attempt.finalState
                    ? formatMappedValue(
                        messages.enumLabels.attemptStatus,
                        attempt.finalState,
                        messages.common.notAvailable,
                      )
                    : messages.common.notAvailable,
                },
                {
                  label: messages.attemptDetail.fields.failureReason,
                  value: attempt.failureReason ?? messages.common.notAvailable,
                },
                {
                  label: messages.attemptDetail.fields.task,
                  value: (
                    <Link to="/tasks/$taskId" params={{ taskId: attempt.taskId }}>
                      {attempt.taskId}
                    </Link>
                  ),
                },
                {
                  label: messages.attemptDetail.fields.device,
                  value: (
                    <Link to="/devices/$deviceId" params={{ deviceId: attempt.deviceId }}>
                      {attempt.deviceId}
                    </Link>
                  ),
                },
                {
                  label: messages.attemptDetail.fields.runId,
                  value: attempt.runId ? (
                    <Link to="/runs/$runId" params={{ runId: attempt.runId }}>
                      {attempt.runId}
                    </Link>
                  ) : (
                    messages.common.notAvailable
                  ),
                },
                {
                  label: messages.attemptDetail.fields.leaseExpire,
                  value: formatDateTime(attempt.leaseExpireAt, messages.locale),
                },
                {
                  label: messages.attemptDetail.fields.started,
                  value: formatDateTime(attempt.startedAt, messages.locale),
                },
                {
                  label: messages.attemptDetail.fields.finished,
                  value: formatDateTime(attempt.finishedAt, messages.locale),
                },
              ]}
            />
          </Panel>
          <Panel title={messages.attemptDetail.taskContext}>
            <KeyValueTable
              rows={[
                { label: messages.attemptDetail.fields.taskId, value: attempt.taskId },
                { label: messages.attemptDetail.fields.deviceId, value: attempt.deviceId },
                {
                  label: messages.attemptDetail.fields.updated,
                  value: formatDateTime(attempt.updatedAt, messages.locale),
                },
                {
                  label: messages.attemptDetail.fields.created,
                  value: formatDateTime(attempt.createdAt, messages.locale),
                },
              ]}
            />
          </Panel>
          <Panel title={messages.attemptDetail.attemptJson}>
            <JsonBlock value={attempt} />
          </Panel>
          <Panel title={messages.attemptDetail.detailPayload}>
            <JsonBlock value={attemptQuery.data} />
          </Panel>
          <Panel
            title={messages.attemptDetail.aiDiagnostics}
            subtitle={messages.attemptDetail.aiDiagnosticsSubtitle}
          >
            {attempt.runId ? (
              <div className="stack-sm">
                <SuccessState
                  title={messages.attemptDetail.aiMovedTitle}
                  body={messages.attemptDetail.aiMovedBody}
                />
                <div>
                  <Link to="/runs/$runId" params={{ runId: attempt.runId }}>
                    {messages.attemptDetail.viewRunDiagnostics}
                  </Link>
                </div>
              </div>
            ) : (
              <EmptyState
                title={messages.attemptDetail.aiRetiredTitle}
                body={messages.attemptDetail.aiRetiredBody}
              />
            )}
          </Panel>
          <Panel
            title={messages.attemptDetail.artifacts}
            subtitle={messages.attemptDetail.artifactsSubtitle}
          >
            {artifactsQuery.isPending ? <LoadingState /> : null}
            {artifactsQuery.isError ? <ErrorState body={artifactsQuery.error.message} /> : null}
            {artifactsQuery.data && artifactsQuery.data.length === 0 ? (
              <EmptyState
                title={messages.attemptDetail.emptyArtifactsTitle}
                body={messages.attemptDetail.emptyArtifactsBody}
              />
            ) : null}
            {artifactsQuery.data && artifactsQuery.data.length > 0 ? (
              <div className="stack-sm">
                {artifactsQuery.data.map((artifact) => (
                  <article className="list-card" key={artifact.artifactId}>
                    <strong>{artifact.fileName}</strong>
                    <span>{artifact.artifactType}</span>
                    <span>{artifact.mimeType}</span>
                    <span>{messages.attemptDetail.fields.sizeBytes}: {artifact.sizeBytes}</span>
                    <span>{artifact.objectKey}</span>
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={async () => {
                        try {
                          setArtifactError(null);
                          const blob = await controlApi.downloadAttemptArtifact(
                            attemptId,
                            artifact.artifactId,
                          );
                          const objectUrl = window.URL.createObjectURL(blob);
                          const link = document.createElement("a");
                          link.href = objectUrl;
                          link.download = artifact.fileName;
                          document.body.append(link);
                          link.click();
                          link.remove();
                          window.URL.revokeObjectURL(objectUrl);
                        } catch (error) {
                          setArtifactError(
                            error instanceof ApiError
                              ? error.message
                              : error instanceof Error
                                ? error.message
                                : messages.common.requestFailed,
                          );
                        }
                      }}
                    >
                      {messages.attemptDetail.download}
                    </button>
                  </article>
                ))}
                {artifactError ? <ErrorState body={artifactError} /> : null}
              </div>
            ) : null}
          </Panel>
          <Panel title={messages.attemptDetail.eventsTimeline}>
            {eventsQuery.isPending ? <LoadingState /> : null}
            {eventsQuery.isError ? <ErrorState body={eventsQuery.error.message} /> : null}
            {eventsQuery.data && eventsQuery.data.length === 0 ? (
              <EmptyState
                title={messages.attemptDetail.emptyEventsTitle}
                body={messages.attemptDetail.emptyEventsBody}
              />
            ) : null}
            {sortedEvents.length > 0 ? (
              <div className="stack-sm">
                {sortedEvents.map((event) => (
                  <article className="list-card" key={event.id}>
                    <div className="list-header">
                      <strong>{event.eventType}</strong>
                      <span>
                        {messages.attemptDetail.stepAction(
                          String(event.stepIndex ?? messages.common.notAvailable),
                          String(event.actionIndex ?? messages.common.notAvailable),
                        )}
                      </span>
                    </div>
                    <span>{formatDateTime(event.ts, messages.locale)}</span>
                    <JsonBlock value={event} />
                  </article>
                ))}
              </div>
            ) : null}
          </Panel>
        </div>
      ) : null}
    </PageShell>
  );
}
