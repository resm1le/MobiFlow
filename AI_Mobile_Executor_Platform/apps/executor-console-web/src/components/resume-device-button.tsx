import { useResumeDeviceMutation } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { ErrorState, SuccessState } from "./ui";

export function ResumeDeviceButton({
  deviceId,
  compact = false,
}: {
  deviceId: string;
  compact?: boolean;
}) {
  const { messages } = useI18n();
  const mutation = useResumeDeviceMutation();

  return (
    <div className="stack-sm">
      <button
        className="button-secondary"
        type="button"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate(deviceId)}
      >
        {mutation.isPending ? messages.actions.resuming : messages.actions.resume}
      </button>
      {mutation.isError ? <ErrorState body={mutation.error.message} /> : null}
      {mutation.isSuccess ? (
        compact ? (
          <span className="inline-success">{messages.actions.resumed}</span>
        ) : (
          <SuccessState body={messages.actions.deviceResumed(deviceId)} />
        )
      ) : null}
    </div>
  );
}
