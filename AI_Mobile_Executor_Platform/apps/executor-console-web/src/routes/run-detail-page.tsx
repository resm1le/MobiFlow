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
} from "../components/ui";
import { formatDateTime } from "../lib/format";
import {
  useCancelRunMutation,
  useRunQuery,
  useRunSummaryLatestQuery,
  useRunSummaryMutation,
  useRunTargetFailureTriageLatestQuery,
  useRunTargetFailureTriageMutation,
} from "../lib/hooks";
import { formatMappedValue, useI18n } from "../lib/i18n";
import type { ExperimentRunTarget } from "../lib/types";

export function RunDetailPage() {
  const { runId } = useParams({ from: "/runs/$runId" });
  const { messages } = useI18n();
  const query = useRunQuery(runId);
  const cancelMutation = useCancelRunMutation();
  const latestSummaryQuery = useRunSummaryLatestQuery(runId, Boolean(runId));
  const summaryMutation = useRunSummaryMutation();
  const detail = query.data;
  const run = query.data?.run;
  const summary = summaryMutation.data ?? latestSummaryQuery.data;

  return (
    <PageShell
      title={messages.runDetail.title(runId)}
      actions={
        <button
          className="button-secondary"
          type="button"
          disabled={
            cancelMutation.isPending ||
            !run ||
            ["TERMINAL", "CANCELLING"].includes(run.status)
          }
          onClick={() => cancelMutation.mutate(runId)}
        >
          {cancelMutation.isPending
            ? messages.runDetail.cancelling
            : messages.runDetail.cancel}
        </button>
      }
    >
      {query.isPending ? <LoadingState /> : null}
      {query.isError ? <ErrorState body={query.error.message} /> : null}
      {cancelMutation.isError ? <ErrorState body={cancelMutation.error.message} /> : null}
      {run && detail ? (
        <div className="grid-two">
          <Panel title={messages.runDetail.summary}>
            <KeyValueTable
              rows={[
                { label: messages.runDetail.fields.name, value: run.name },
                {
                  label: messages.runDetail.fields.status,
                  value: formatMappedValue(
                    messages.enumLabels.runStatus,
                    run.status,
                    messages.common.notAvailable,
                  ),
                },
                {
                  label: messages.runDetail.fields.finalState,
                  value: run.finalState
                    ? formatMappedValue(
                        messages.enumLabels.runFinalState,
                        run.finalState,
                        messages.common.notAvailable,
                      )
                    : messages.common.notAvailable,
                },
                { label: messages.runDetail.fields.poolId, value: run.poolId ?? "—" },
                { label: messages.runDetail.fields.taskType, value: run.taskType },
                {
                  label: messages.runDetail.fields.profilePackage,
                  value: run.profilePackage ?? "—",
                },
                { label: messages.runDetail.fields.priority, value: String(run.priority) },
                { label: messages.runDetail.fields.source, value: run.source },
                { label: messages.runDetail.fields.createdBy, value: run.createdBy },
                {
                  label: messages.runDetail.fields.maxRetriesPerDevice,
                  value: String(run.maxRetriesPerDevice),
                },
                {
                  label: messages.runDetail.fields.queueTimeoutMs,
                  value: String(run.queueTimeoutMs),
                },
                {
                  label: messages.runDetail.fields.created,
                  value: formatDateTime(run.createdAt, messages.locale),
                },
                {
                  label: messages.runDetail.fields.started,
                  value: formatDateTime(run.startedAt, messages.locale),
                },
                {
                  label: messages.runDetail.fields.finished,
                  value: formatDateTime(run.finishedAt, messages.locale),
                },
              ]}
            />
          </Panel>
          <Panel title={messages.runDetail.counts}>
            <KeyValueTable
              rows={[
                {
                  label: messages.runDetail.fields.totalTargets,
                  value: String(run.counts.totalTargets),
                },
                { label: messages.runDetail.fields.queued, value: String(run.counts.queued) },
                { label: messages.runDetail.fields.running, value: String(run.counts.running) },
                {
                  label: messages.runDetail.fields.retryPending,
                  value: String(run.counts.retryPending),
                },
                {
                  label: messages.runDetail.fields.succeeded,
                  value: String(run.counts.succeeded),
                },
                { label: messages.runDetail.fields.failed, value: String(run.counts.failed) },
                {
                  label: messages.runDetail.fields.cancelled,
                  value: String(run.counts.cancelled),
                },
              ]}
            />
          </Panel>
          <Panel title={messages.runDetail.taskPayload}>
            <JsonBlock value={detail.taskPayload} />
          </Panel>
          <Panel title={messages.runDetail.runConfig}>
            <JsonBlock value={detail.runConfig} />
          </Panel>
          <Panel title={messages.runDetail.artifactPolicy}>
            <JsonBlock value={detail.artifactPolicy} />
          </Panel>
          <Panel
            title={messages.runDetail.aiSummary}
            subtitle={messages.runDetail.aiSummarySubtitle}
          >
            <div className="stack-sm">
              {summaryMutation.isError ? <ErrorState body={summaryMutation.error.message} /> : null}
              {latestSummaryQuery.isError ? <ErrorState body={latestSummaryQuery.error.message} /> : null}
              {summaryMutation.isPending || latestSummaryQuery.isPending ? <LoadingState /> : null}
              {!summary && !summaryMutation.isPending && !latestSummaryQuery.isPending ? (
                <EmptyState
                  title={messages.runDetail.summaryPanel.emptyTitle}
                  body={messages.runDetail.summaryPanel.emptyBody}
                />
              ) : null}
              {summary ? (
                <>
                  <KeyValueTable
                    rows={[
                      {
                        label: messages.runDetail.summaryPanel.fields.summaryText,
                        value: summary.result.summaryText,
                      },
                      {
                        label: messages.runDetail.summaryPanel.fields.finalJudgement,
                        value: summary.result.finalJudgement,
                      },
                      {
                        label: messages.runDetail.summaryPanel.fields.evidence,
                        value:
                          summary.result.evidence.join(", ") || messages.common.notAvailable,
                      },
                      {
                        label: messages.runDetail.summaryPanel.fields.validation,
                        value: summary.validation.valid
                          ? messages.runDetail.summaryPanel.statusReady
                          : messages.runDetail.summaryPanel.statusNeedsReview,
                      },
                      {
                        label: messages.runDetail.summaryPanel.fields.generatedAt,
                        value: formatDateTime(summary.generatedAt, messages.locale),
                      },
                    ]}
                  />
                  <JsonBlock
                    value={{
                      keyMoments: summary.result.keyMoments,
                      validation: summary.validation,
                      modelMeta: summary.modelMeta,
                    }}
                  />
                </>
              ) : null}
              <div className="stack-sm">
                <button
                  className="button-secondary"
                  type="button"
                  disabled={summaryMutation.isPending}
                  onClick={() => summaryMutation.mutate(runId)}
                >
                  {summaryMutation.isPending
                    ? messages.runDetail.summaryPanel.generating
                    : messages.runDetail.summaryPanel.generate}
                </button>
                <button
                  className="button-secondary"
                  type="button"
                  onClick={() => {
                    void latestSummaryQuery.refetch();
                  }}
                >
                  {messages.runDetail.summaryPanel.viewLatest}
                </button>
              </div>
            </div>
          </Panel>
          <Panel title={messages.runDetail.targets} subtitle={messages.runDetail.targetsSubtitle}>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{messages.runDetail.headers.device}</th>
                    <th>{messages.runDetail.headers.status}</th>
                    <th>{messages.runDetail.headers.attempts}</th>
                    <th>{messages.runDetail.headers.task}</th>
                    <th>{messages.runDetail.headers.attempt}</th>
                    <th>{messages.runDetail.headers.failureReason}</th>
                    <th>{messages.runDetail.headers.triage}</th>
                    <th>{messages.runDetail.headers.actions}</th>
                    <th>{messages.runDetail.headers.started}</th>
                    <th>{messages.runDetail.headers.finished}</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.targets.map((target) => (
                    <RunTargetRow key={target.runTargetId} target={target} />
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      ) : null}
    </PageShell>
  );
}

function RunTargetRow({ target }: { target: ExperimentRunTarget }) {
  const { messages } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const eligible =
    Boolean(target.latestAttemptId) &&
    ["FAILED", "CANCELLED"].includes(target.status);
  const latestTriageQuery = useRunTargetFailureTriageLatestQuery(target.runTargetId, eligible);
  const triageMutation = useRunTargetFailureTriageMutation();
  const triage = triageMutation.data ?? latestTriageQuery.data;

  const triageStatus = !eligible
    ? messages.runDetail.triage.statusNotEligible
    : triageMutation.isPending || latestTriageQuery.isPending
      ? messages.runDetail.triage.statusLoading
      : triage
        ? triage.validation.valid
          ? messages.runDetail.triage.statusReady
          : messages.runDetail.triage.statusNeedsReview
        : messages.runDetail.triage.statusNotGenerated;

  return (
    <>
      <tr>
        <td>{target.deviceId}</td>
        <td>
          {formatMappedValue(
            messages.enumLabels.runTargetStatus,
            target.status,
            messages.common.notAvailable,
          )}
        </td>
        <td>{target.attemptCount}</td>
        <td>
          {target.task ? (
            <Link to="/tasks/$taskId" params={{ taskId: target.task.taskId }}>
              {target.task.taskId}
            </Link>
          ) : (
            target.currentTaskId ?? messages.common.notAvailable
          )}
        </td>
        <td>
          {target.latestAttempt ? (
            <Link
              to="/attempts/$attemptId"
              params={{ attemptId: target.latestAttempt.attemptId }}
            >
              {target.latestAttempt.attemptId}
            </Link>
          ) : (
            target.latestAttemptId ?? messages.common.notAvailable
          )}
        </td>
        <td className="wrap-cell">{target.failureReason ?? messages.common.notAvailable}</td>
        <td>{triageStatus}</td>
        <td>
          <div className="stack-sm">
            <button
              className="button-secondary"
              type="button"
              disabled={!eligible || triageMutation.isPending}
              onClick={() => {
                setExpanded(true);
                triageMutation.mutate(target.runTargetId);
              }}
            >
              {triageMutation.isPending
                ? messages.runDetail.triage.generating
                : messages.runDetail.triage.generate}
            </button>
            <button
              className="button-secondary"
              type="button"
              disabled={!eligible}
              onClick={() => {
                setExpanded(true);
                void latestTriageQuery.refetch();
              }}
            >
              {messages.runDetail.triage.viewLatest}
            </button>
          </div>
        </td>
        <td>{formatDateTime(target.startedAt, messages.locale)}</td>
        <td>{formatDateTime(target.finishedAt, messages.locale)}</td>
      </tr>
      {expanded ? (
        <tr>
          <td colSpan={10}>
            <div className="stack-sm">
              <strong>{messages.runDetail.triage.title}</strong>
              <span>{messages.runDetail.triage.subtitle(target.runTargetId)}</span>
              {triageMutation.isError ? <ErrorState body={triageMutation.error.message} /> : null}
              {latestTriageQuery.isError ? <ErrorState body={latestTriageQuery.error.message} /> : null}
              {triageMutation.isPending || latestTriageQuery.isPending ? <LoadingState /> : null}
              {!triage && !triageMutation.isPending && !latestTriageQuery.isPending ? (
                <EmptyState
                  title={messages.runDetail.triage.emptyTitle}
                  body={messages.runDetail.triage.emptyBody}
                />
              ) : null}
              {triage ? (
                <>
                  <KeyValueTable
                    rows={[
                      {
                        label: messages.runDetail.triage.fields.failureCategory,
                        value: triage.result.failureCategory,
                      },
                      {
                        label: messages.runDetail.triage.fields.probableCause,
                        value: triage.result.probableCause,
                      },
                      {
                        label: messages.runDetail.triage.fields.confidence,
                        value: triage.result.confidence.toFixed(2),
                      },
                      {
                        label: messages.runDetail.triage.fields.retryRecommendation,
                        value: triage.result.retryRecommendation,
                      },
                      {
                        label: messages.runDetail.triage.fields.suggestedNextAction,
                        value: triage.result.suggestedNextAction,
                      },
                      {
                        label: messages.runDetail.triage.fields.operatorReviewHints,
                        value:
                          triage.result.operatorReviewHints.join(", ") ||
                          messages.common.notAvailable,
                      },
                      {
                        label: messages.runDetail.triage.fields.evidence,
                        value: triage.result.evidence.join(", ") || messages.common.notAvailable,
                      },
                      {
                        label: messages.runDetail.triage.fields.validation,
                        value: triage.validation.valid
                          ? messages.runDetail.triage.statusReady
                          : messages.runDetail.triage.statusNeedsReview,
                      },
                      {
                        label: messages.runDetail.triage.fields.generatedAt,
                        value: formatDateTime(triage.generatedAt, messages.locale),
                      },
                    ]}
                  />
                  <JsonBlock
                    value={{
                      validation: triage.validation,
                      modelMeta: triage.modelMeta,
                    }}
                  />
                </>
              ) : null}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}
