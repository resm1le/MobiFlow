import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { ErrorState, PageShell, Panel } from "../components/ui";
import { DEFAULT_TASK_FORM, PROFILE_OPTIONS } from "../lib/constants";
import { formatJson, parseJsonInput } from "../lib/format";
import { useCreateRunMutation, useDevicePoolsQuery } from "../lib/hooks";
import { useI18n } from "../lib/i18n";

export function RunNewPage() {
  const navigate = useNavigate();
  const { messages } = useI18n();
  const poolsQuery = useDevicePoolsQuery();
  const createMutation = useCreateRunMutation();
  const [name, setName] = useState("Demo run");
  const [description, setDescription] = useState("");
  const [devicePoolId, setDevicePoolId] = useState("");
  const [taskType, setTaskType] = useState(DEFAULT_TASK_FORM.taskType);
  const [profilePackage, setProfilePackage] = useState(DEFAULT_TASK_FORM.profilePackage);
  const [priority, setPriority] = useState(String(DEFAULT_TASK_FORM.priority));
  const [source, setSource] = useState("console-run");
  const [labels, setLabels] = useState("run-first, batch");
  const [createdBy, setCreatedBy] = useState("console");
  const [maxRetriesPerDevice, setMaxRetriesPerDevice] = useState("0");
  const [queueTimeoutMs, setQueueTimeoutMs] = useState("300000");
  const [taskPayload, setTaskPayload] = useState(formatJson(DEFAULT_TASK_FORM.taskPayload));
  const [runConfig, setRunConfig] = useState(formatJson(DEFAULT_TASK_FORM.runConfig));
  const [artifactPolicy, setArtifactPolicy] = useState(
    formatJson(DEFAULT_TASK_FORM.artifactPolicy),
  );
  const [formError, setFormError] = useState<string | null>(null);

  return (
    <PageShell title={messages.runNew.title}>
      <Panel title={messages.runNew.panelTitle} subtitle={messages.runNew.panelSubtitle}>
        {poolsQuery.isError ? <ErrorState body={poolsQuery.error.message} /> : null}
        {!poolsQuery.isPending && (poolsQuery.data?.length ?? 0) === 0 ? (
          <ErrorState
            title={messages.runNew.noPoolsTitle}
            body={messages.runNew.noPoolsBody}
          />
        ) : null}
        <form
          className="stack-lg"
          onSubmit={(event) => {
            event.preventDefault();
            try {
              setFormError(null);
              createMutation.mutate(
                {
                  name,
                  description: description.trim() || null,
                  devicePoolId,
                  taskType,
                  profilePackage,
                  taskPayload: parseJsonInput(taskPayload),
                  runConfig: parseJsonInput(runConfig),
                  artifactPolicy: parseJsonInput(artifactPolicy),
                  priority: Number(priority),
                  labels: labels
                    .split(",")
                    .map((value) => value.trim())
                    .filter(Boolean),
                  source,
                  createdBy: createdBy.trim() || null,
                  maxRetriesPerDevice: Number(maxRetriesPerDevice),
                  queueTimeoutMs: Number(queueTimeoutMs),
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
            } catch (error) {
              setFormError(
                error instanceof Error ? error.message : messages.runNew.invalidFormInput,
              );
            }
          }}
        >
          <div className="grid-two">
            <label className="field">
              <span>{messages.runNew.fields.name}</span>
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="field">
              <span>{messages.runNew.fields.devicePoolId}</span>
              <select
                value={devicePoolId}
                onChange={(event) => setDevicePoolId(event.target.value)}
              >
                <option value="">{messages.runNew.selectPoolPlaceholder}</option>
                {(poolsQuery.data ?? []).map((pool) => (
                  <option key={pool.poolId} value={pool.poolId}>
                    {pool.name} ({pool.poolId})
                  </option>
                ))}
              </select>
            </label>
            <label className="field field-full">
              <span>{messages.runNew.fields.description}</span>
              <textarea
                rows={4}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <label className="field">
              <span>{messages.runNew.fields.taskType}</span>
              <input value={taskType} onChange={(event) => setTaskType(event.target.value)} />
            </label>
            <label className="field">
              <span>{messages.runNew.fields.profilePackage}</span>
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
              <span>{messages.runNew.fields.priority}</span>
              <input
                type="number"
                value={priority}
                onChange={(event) => setPriority(event.target.value)}
              />
            </label>
            <label className="field">
              <span>{messages.runNew.fields.maxRetriesPerDevice}</span>
              <input
                type="number"
                value={maxRetriesPerDevice}
                onChange={(event) => setMaxRetriesPerDevice(event.target.value)}
              />
            </label>
            <label className="field">
              <span>{messages.runNew.fields.queueTimeoutMs}</span>
              <input
                type="number"
                value={queueTimeoutMs}
                onChange={(event) => setQueueTimeoutMs(event.target.value)}
              />
            </label>
            <label className="field">
              <span>{messages.runNew.fields.source}</span>
              <input value={source} onChange={(event) => setSource(event.target.value)} />
            </label>
            <label className="field">
              <span>{messages.runNew.fields.createdBy}</span>
              <input value={createdBy} onChange={(event) => setCreatedBy(event.target.value)} />
            </label>
            <label className="field field-full">
              <span>{messages.runNew.fields.labels}</span>
              <input value={labels} onChange={(event) => setLabels(event.target.value)} />
            </label>
            <label className="field field-full">
              <span>{messages.runNew.fields.taskPayload}</span>
              <textarea
                rows={8}
                value={taskPayload}
                onChange={(event) => setTaskPayload(event.target.value)}
              />
            </label>
            <label className="field field-full">
              <span>{messages.runNew.fields.runConfig}</span>
              <textarea
                rows={8}
                value={runConfig}
                onChange={(event) => setRunConfig(event.target.value)}
              />
            </label>
            <label className="field field-full">
              <span>{messages.runNew.fields.artifactPolicy}</span>
              <textarea
                rows={8}
                value={artifactPolicy}
                onChange={(event) => setArtifactPolicy(event.target.value)}
              />
            </label>
          </div>
          {formError ? <ErrorState body={formError} /> : null}
          {createMutation.isError ? <ErrorState body={createMutation.error.message} /> : null}
          <div className="page-actions">
            <button className="button-primary" type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? messages.runNew.creating : messages.runNew.create}
            </button>
            <Link className="button-secondary" to="/device-pools">
              {messages.runNew.managePools}
            </Link>
          </div>
        </form>
      </Panel>
    </PageShell>
  );
}
