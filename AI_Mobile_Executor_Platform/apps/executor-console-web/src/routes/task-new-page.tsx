import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ErrorState, PageShell, Panel } from "../components/ui";
import { DEFAULT_TASK_FORM, PROFILE_OPTIONS } from "../lib/constants";
import { formatJson, parseJsonInput } from "../lib/format";
import { useCreateTaskMutation } from "../lib/hooks";
import { useI18n } from "../lib/i18n";

export function TaskNewPage() {
  const navigate = useNavigate();
  const { messages } = useI18n();
  const mutation = useCreateTaskMutation();
  const [taskType, setTaskType] = useState(DEFAULT_TASK_FORM.taskType);
  const [profilePackage, setProfilePackage] = useState(DEFAULT_TASK_FORM.profilePackage);
  const [priority, setPriority] = useState(String(DEFAULT_TASK_FORM.priority));
  const [source, setSource] = useState(DEFAULT_TASK_FORM.source);
  const [labels, setLabels] = useState(DEFAULT_TASK_FORM.labels.join(", "));
  const [taskPayload, setTaskPayload] = useState(formatJson(DEFAULT_TASK_FORM.taskPayload));
  const [runConfig, setRunConfig] = useState(formatJson(DEFAULT_TASK_FORM.runConfig));
  const [artifactPolicy, setArtifactPolicy] = useState(
    formatJson(DEFAULT_TASK_FORM.artifactPolicy),
  );
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  return (
    <PageShell title={messages.taskNew.title}>
      <Panel
        title={messages.taskNew.panelTitle}
        subtitle={messages.taskNew.panelSubtitle}
      >
        <form
          className="stack-lg"
          onSubmit={(event) => {
            event.preventDefault();
            try {
              setFormError(null);
              mutation.mutate(
                {
                  taskType,
                  profilePackage,
                  priority: Number(priority),
                  source,
                  labels: labels
                    .split(",")
                    .map((value) => value.trim())
                    .filter(Boolean),
                  taskPayload: parseJsonInput(taskPayload),
                  runConfig: parseJsonInput(runConfig),
                  artifactPolicy: parseJsonInput(artifactPolicy),
                  idempotencyKey: idempotencyKey.trim() || null,
                },
                {
                  onSuccess: (task) => {
                    void navigate({ to: "/tasks/$taskId", params: { taskId: task.taskId } });
                  },
                },
              );
            } catch (error) {
              setFormError(
                error instanceof Error ? error.message : messages.taskNew.invalidFormInput,
              );
            }
          }}
        >
          <div className="grid-two">
            <label className="field">
              <span>{messages.taskNew.fields.taskType}</span>
              <input value={taskType} onChange={(event) => setTaskType(event.target.value)} />
            </label>
            <label className="field">
              <span>{messages.taskNew.fields.profilePackage}</span>
              <select
                value={profilePackage}
                onChange={(event) => setProfilePackage(event.target.value)}
              >
                {PROFILE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{messages.taskNew.fields.priority}</span>
              <input
                type="number"
                value={priority}
                onChange={(event) => setPriority(event.target.value)}
              />
            </label>
            <label className="field">
              <span>{messages.taskNew.fields.source}</span>
              <input value={source} onChange={(event) => setSource(event.target.value)} />
            </label>
            <label className="field field-full">
              <span>{messages.taskNew.fields.labels}</span>
              <input value={labels} onChange={(event) => setLabels(event.target.value)} />
            </label>
            <label className="field field-full">
              <span>{messages.taskNew.fields.idempotencyKey}</span>
              <input
                value={idempotencyKey}
                onChange={(event) => setIdempotencyKey(event.target.value)}
              />
            </label>
            <label className="field field-full">
              <span>{messages.taskNew.fields.taskPayload}</span>
              <textarea
                rows={8}
                value={taskPayload}
                onChange={(event) => setTaskPayload(event.target.value)}
              />
            </label>
            <label className="field field-full">
              <span>{messages.taskNew.fields.runConfig}</span>
              <textarea
                rows={8}
                value={runConfig}
                onChange={(event) => setRunConfig(event.target.value)}
              />
            </label>
            <label className="field field-full">
              <span>{messages.taskNew.fields.artifactPolicy}</span>
              <textarea
                rows={8}
                value={artifactPolicy}
                onChange={(event) => setArtifactPolicy(event.target.value)}
              />
            </label>
          </div>
          {formError ? <ErrorState body={formError} /> : null}
          {mutation.isError ? <ErrorState body={mutation.error.message} /> : null}
          <button className="button-primary" type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? messages.taskNew.creating : messages.taskNew.create}
          </button>
        </form>
      </Panel>
    </PageShell>
  );
}
