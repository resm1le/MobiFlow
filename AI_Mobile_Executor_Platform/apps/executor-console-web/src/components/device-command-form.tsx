import { useState } from "react";
import { formatMappedValue, useI18n } from "../lib/i18n";
import { useSendDeviceCommandMutation } from "../lib/hooks";
import type { DeviceCommandType } from "../lib/types";
import { ErrorState, SuccessState } from "./ui";

const COMMAND_OPTIONS: DeviceCommandType[] = [
  "QUIESCE",
  "FORCE_HEALTH_CHECK",
  "REREGISTER",
  "CANCEL_ATTEMPT",
];

export function DeviceCommandForm({
  deviceId,
  currentAttemptId,
}: {
  deviceId: string;
  currentAttemptId: string | null;
}) {
  const { messages } = useI18n();
  const [commandType, setCommandType] = useState<DeviceCommandType>("FORCE_HEALTH_CHECK");
  const [expireInMs, setExpireInMs] = useState("120000");
  const mutation = useSendDeviceCommandMutation();

  const canSubmit =
    !mutation.isPending &&
    (commandType !== "CANCEL_ATTEMPT" || Boolean(currentAttemptId));

  return (
    <form
      className="stack-sm"
      onSubmit={(event) => {
        event.preventDefault();
        if (!canSubmit) {
          return;
        }
        mutation.mutate({
          deviceId,
          body: {
            type: commandType,
            attemptId: commandType === "CANCEL_ATTEMPT" ? currentAttemptId : null,
            expireInMs: Number(expireInMs),
          },
        });
      }}
      >
      <label className="field">
        <span>{messages.actions.command}</span>
        <select
          value={commandType}
          onChange={(event) => setCommandType(event.target.value as DeviceCommandType)}
        >
          {COMMAND_OPTIONS.map((option) => (
            <option
              key={option}
              value={option}
              disabled={option === "CANCEL_ATTEMPT" && !currentAttemptId}
            >
              {formatMappedValue(
                messages.enumLabels.commandType,
                option,
                messages.common.notAvailable,
              )}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{messages.actions.expireInMs}</span>
        <input
          type="number"
          min={30}
          value={expireInMs}
          onChange={(event) => setExpireInMs(event.target.value)}
        />
      </label>
      <button className="button-primary" type="submit" disabled={!canSubmit}>
        {mutation.isPending ? messages.actions.sending : messages.actions.sendCommand}
      </button>
      {mutation.isError ? (
        <ErrorState body={mutation.error.message} />
      ) : null}
      {mutation.isSuccess ? (
        <SuccessState body={messages.actions.commandQueued(mutation.data.type)} />
      ) : null}
    </form>
  );
}
