import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { AI_PLAN_CREATED_BY, DEFAULT_AI_CONSTRAINTS } from "../lib/constants";
import { formatJson, parseJsonInput } from "../lib/format";
import { useCreateAiRunPlanMutation, useMaterializeAiRunPlanMutation } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import type { CreateAiRunPlanResponse } from "../lib/types";
import {
  Badge,
  ErrorState,
  JsonBlock,
  KeyValueTable,
  PageShell,
  Panel,
  SuccessState,
} from "../components/ui";

export function AiRunPlanPage() {
  const navigate = useNavigate();
  const { messages } = useI18n();
  const runPlanningMessages = messages.aiRunPlanning;
  const createPlanMutation = useCreateAiRunPlanMutation();
  const materializeMutation = useMaterializeAiRunPlanMutation();
  const [goal, setGoal] = useState("");
  const [constraints, setConstraints] = useState(formatJson(DEFAULT_AI_CONSTRAINTS));
  const [formError, setFormError] = useState<string | null>(null);
  const [plan, setPlan] = useState<CreateAiRunPlanResponse | null>(null);

  const validationTone = plan?.validation.materializable ? "success" : "danger";

  return (
    <PageShell title={runPlanningMessages.title}>
      <Panel title={runPlanningMessages.panelTitle} subtitle={runPlanningMessages.panelSubtitle}>
        <form
          className="stack-lg"
          onSubmit={(event) => {
            event.preventDefault();
            try {
              setFormError(null);
              createPlanMutation.reset();
              materializeMutation.reset();
              setPlan(null);
              createPlanMutation.mutate(
                {
                  goal: goal.trim(),
                  constraints: parseJsonInput(constraints),
                },
                {
                  onSuccess: (response) => setPlan(response),
                },
              );
            } catch (error) {
              setFormError(
                error instanceof Error ? error.message : runPlanningMessages.invalidInput,
              );
            }
          }}
        >
          <div className="grid-two">
            <label className="field field-full">
              <span>{runPlanningMessages.fields.goal}</span>
              <textarea rows={4} value={goal} onChange={(event) => setGoal(event.target.value)} />
            </label>
            <label className="field field-full">
              <span>{runPlanningMessages.fields.constraints}</span>
              <textarea
                rows={8}
                value={constraints}
                onChange={(event) => setConstraints(event.target.value)}
              />
            </label>
          </div>
          {formError ? <ErrorState body={formError} /> : null}
          {createPlanMutation.isError ? <ErrorState body={createPlanMutation.error.message} /> : null}
          <button className="button-primary" type="submit" disabled={createPlanMutation.isPending}>
            {createPlanMutation.isPending
              ? runPlanningMessages.creatingPlan
              : runPlanningMessages.createPlan}
          </button>
        </form>
      </Panel>

      {plan ? (
        <Panel title={runPlanningMessages.reviewTitle} subtitle={runPlanningMessages.reviewSubtitle}>
          <div className="stack-lg">
            <SuccessState
              title={runPlanningMessages.planReadyTitle}
              body={runPlanningMessages.planReadyBody(plan.requestId)}
            />
            <KeyValueTable
              rows={[
                { label: runPlanningMessages.fields.requestId, value: plan.requestId },
                { label: runPlanningMessages.fields.name, value: plan.runDraft.name },
                {
                  label: runPlanningMessages.fields.description,
                  value: plan.runDraft.description ?? messages.common.notAvailable,
                },
                { label: runPlanningMessages.fields.devicePoolId, value: plan.runDraft.devicePoolId },
                { label: runPlanningMessages.fields.taskType, value: plan.runDraft.taskType },
                { label: runPlanningMessages.fields.profilePackage, value: plan.runDraft.profilePackage },
                { label: runPlanningMessages.fields.priority, value: plan.runDraft.priority },
                {
                  label: runPlanningMessages.fields.labels,
                  value: plan.runDraft.labels.join(", ") || messages.common.notAvailable,
                },
                {
                  label: runPlanningMessages.fields.maxRetriesPerDevice,
                  value: plan.runDraft.maxRetriesPerDevice,
                },
                {
                  label: runPlanningMessages.fields.queueTimeoutMs,
                  value: plan.runDraft.queueTimeoutMs,
                },
                {
                  label: runPlanningMessages.fields.validation,
                  value: (
                    <Badge tone={validationTone}>
                      {plan.validation.materializable
                        ? runPlanningMessages.validationPass
                        : runPlanningMessages.validationFail}
                    </Badge>
                  ),
                },
                {
                  label: runPlanningMessages.fields.createdBy,
                  value: AI_PLAN_CREATED_BY,
                },
              ]}
            />

            {plan.validation.errors.length > 0 ? (
              <ErrorState
                title={runPlanningMessages.validationErrorTitle}
                body={plan.validation.errors.join(" | ")}
              />
            ) : null}

            {materializeMutation.isError ? <ErrorState body={materializeMutation.error.message} /> : null}

            <div className="stack-sm">
              <strong>{runPlanningMessages.fields.taskPayload}</strong>
              <JsonBlock value={plan.runDraft.taskPayload} />
            </div>
            <div className="stack-sm">
              <strong>{runPlanningMessages.fields.runConfig}</strong>
              <JsonBlock value={plan.runDraft.runConfig} />
            </div>
            <div className="stack-sm">
              <strong>{runPlanningMessages.fields.artifactPolicy}</strong>
              <JsonBlock value={plan.runDraft.artifactPolicy} />
            </div>
            <div className="stack-sm">
              <strong>{runPlanningMessages.fields.warnings}</strong>
              <JsonBlock value={plan.warnings} />
            </div>
            <div className="stack-sm">
              <strong>{runPlanningMessages.fields.reviewHints}</strong>
              <JsonBlock value={plan.reviewHints} />
            </div>
            <div className="stack-sm">
              <strong>{runPlanningMessages.fields.validationWarnings}</strong>
              <JsonBlock value={plan.validation.warnings} />
            </div>
            <div className="stack-sm">
              <strong>{runPlanningMessages.fields.modelMeta}</strong>
              <JsonBlock value={plan.modelMeta} />
            </div>

            <button
              className="button-primary"
              type="button"
              disabled={!plan.validation.materializable || materializeMutation.isPending}
              onClick={() => {
                materializeMutation.mutate(
                  {
                    requestId: plan.requestId,
                    body: { createdBy: AI_PLAN_CREATED_BY },
                  },
                  {
                    onSuccess: (run) => {
                      void navigate({
                        to: "/runs/$runId",
                        params: { runId: run.run.runId },
                      });
                    },
                  },
                );
              }}
            >
              {materializeMutation.isPending
                ? runPlanningMessages.materializing
                : runPlanningMessages.materialize}
            </button>
          </div>
        </Panel>
      ) : null}
    </PageShell>
  );
}
