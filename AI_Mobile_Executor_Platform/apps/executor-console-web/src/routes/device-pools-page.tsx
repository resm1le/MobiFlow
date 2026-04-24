import { useState } from "react";
import { EmptyState, ErrorState, LoadingState, PageShell, Panel, SuccessState } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { useCreateDevicePoolMutation, useDevicePoolsQuery } from "../lib/hooks";
import { useI18n } from "../lib/i18n";

function parseListInput(value: string): string[] {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function DevicePoolsPage() {
  const { messages } = useI18n();
  const poolsQuery = useDevicePoolsQuery();
  const createMutation = useCreateDevicePoolMutation();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [hostGroup, setHostGroup] = useState("default");
  const [deviceIds, setDeviceIds] = useState("");
  const [requiredTags, setRequiredTags] = useState("");
  const [excludedTags, setExcludedTags] = useState("");
  const [createdBy, setCreatedBy] = useState("console");

  return (
    <PageShell title={messages.devicePools.title}>
      <Panel
        title={messages.devicePools.panelTitle}
        subtitle={messages.devicePools.panelSubtitle}
      >
        {poolsQuery.isPending ? <LoadingState /> : null}
        {poolsQuery.isError ? <ErrorState body={poolsQuery.error.message} /> : null}
        {poolsQuery.data && poolsQuery.data.length === 0 ? (
          <EmptyState
            title={messages.devicePools.emptyTitle}
            body={messages.devicePools.emptyBody}
          />
        ) : null}
        {poolsQuery.data && poolsQuery.data.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{messages.devicePools.headers.name}</th>
                  <th>{messages.devicePools.headers.hostGroup}</th>
                  <th>{messages.devicePools.headers.deviceIds}</th>
                  <th>{messages.devicePools.headers.requiredTags}</th>
                  <th>{messages.devicePools.headers.excludedTags}</th>
                  <th>{messages.devicePools.headers.createdBy}</th>
                  <th>{messages.devicePools.headers.updated}</th>
                </tr>
              </thead>
              <tbody>
                {poolsQuery.data.map((pool) => (
                  <tr key={pool.poolId}>
                    <td className="wrap-cell">
                      <strong>{pool.name}</strong>
                      <div>{pool.poolId}</div>
                      {pool.description ? <div>{pool.description}</div> : null}
                    </td>
                    <td>{pool.hostGroup ?? messages.common.notAvailable}</td>
                    <td className="wrap-cell">
                      {pool.deviceIds.join(", ") || messages.common.notAvailable}
                    </td>
                    <td className="wrap-cell">
                      {pool.requiredTags.join(", ") || messages.common.notAvailable}
                    </td>
                    <td className="wrap-cell">
                      {pool.excludedTags.join(", ") || messages.common.notAvailable}
                    </td>
                    <td>{pool.createdBy}</td>
                    <td>{formatDateTime(pool.updatedAt, messages.locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Panel>
      <Panel
        title={messages.devicePools.createTitle}
        subtitle={messages.devicePools.createSubtitle}
      >
        <form
          className="stack-lg"
          onSubmit={(event) => {
            event.preventDefault();
            createMutation.mutate(
              {
                name,
                description: description.trim() || null,
                hostGroup: hostGroup.trim() || null,
                deviceIds: parseListInput(deviceIds),
                requiredTags: parseListInput(requiredTags),
                excludedTags: parseListInput(excludedTags),
                createdBy: createdBy.trim() || null,
              },
              {
                onSuccess: () => {
                  setName("");
                  setDescription("");
                  setDeviceIds("");
                  setRequiredTags("");
                  setExcludedTags("");
                },
              },
            );
          }}
        >
          <div className="grid-two">
            <label className="field">
              <span>{messages.devicePools.fields.name}</span>
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="field">
              <span>{messages.devicePools.fields.hostGroup}</span>
              <input value={hostGroup} onChange={(event) => setHostGroup(event.target.value)} />
            </label>
            <label className="field field-full">
              <span>{messages.devicePools.fields.description}</span>
              <textarea
                rows={4}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <label className="field field-full">
              <span>{messages.devicePools.fields.deviceIds}</span>
              <input value={deviceIds} onChange={(event) => setDeviceIds(event.target.value)} />
            </label>
            <label className="field">
              <span>{messages.devicePools.fields.requiredTags}</span>
              <input
                value={requiredTags}
                onChange={(event) => setRequiredTags(event.target.value)}
              />
            </label>
            <label className="field">
              <span>{messages.devicePools.fields.excludedTags}</span>
              <input
                value={excludedTags}
                onChange={(event) => setExcludedTags(event.target.value)}
              />
            </label>
            <label className="field">
              <span>{messages.devicePools.fields.createdBy}</span>
              <input value={createdBy} onChange={(event) => setCreatedBy(event.target.value)} />
            </label>
          </div>
          {createMutation.isError ? <ErrorState body={createMutation.error.message} /> : null}
          {createMutation.isSuccess ? (
            <SuccessState body={messages.devicePools.createAccepted} />
          ) : null}
          <button className="button-primary" type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending
              ? messages.devicePools.creating
              : messages.devicePools.create}
          </button>
        </form>
      </Panel>
    </PageShell>
  );
}
