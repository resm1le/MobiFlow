package com.example.platform.control.application;

import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import org.springframework.stereotype.Component;

@Component
public class ControlStateRules {

    public boolean isClaimAllowed(DeviceRuntimeStateEntity runtime) {
        return runtime != null
                && runtime.isRegistered()
                && runtime.isOnline()
                && !runtime.isBusy()
                && !DomainValues.DEVICE_STATUS_QUIESCED.equals(runtime.getStatus());
    }

    public void validateAttemptCanStart(TaskAttemptEntity attempt) {
        if (!isStartableAttempt(attempt)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.ATTEMPT_STATE_INVALID);
        }
    }

    public void validateAttemptCanFinish(TaskAttemptEntity attempt) {
        if (!isActiveAttempt(attempt)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.ATTEMPT_STATE_INVALID);
        }
    }

    public void validateAttemptCanRecordEvents(TaskAttemptEntity attempt) {
        if (!isActiveAttempt(attempt)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.ATTEMPT_STATE_INVALID);
        }
    }

    public CancelAction validateTaskCancellation(TaskEntity task, TaskAttemptEntity latestAttempt) {
        if (DomainValues.TASK_STATUS_QUEUED.equals(task.getStatus())) {
            return CancelAction.CANCEL_DIRECTLY;
        }
        if (!DomainValues.TASK_STATUS_RUNNING.equals(task.getStatus())) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
        }
        if (!isActiveAttempt(latestAttempt)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
        }
        return CancelAction.ENQUEUE_CANCEL_COMMAND;
    }

    public void validateRuntimeCanResume(DeviceRuntimeStateEntity runtime) {
        if (runtime == null || !DomainValues.DEVICE_STATUS_QUIESCED.equals(runtime.getStatus())) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.DEVICE_STATE_INVALID);
        }
    }

    public String releasedRuntimeStatus(DeviceRuntimeStateEntity runtime) {
        if (runtime == null) {
            return DomainValues.DEVICE_STATUS_ONLINE;
        }
        if (DomainValues.DEVICE_STATUS_QUIESCED.equals(runtime.getStatus())) {
            return DomainValues.DEVICE_STATUS_QUIESCED;
        }
        if (!runtime.isOnline() || DomainValues.DEVICE_STATUS_OFFLINE.equals(runtime.getStatus())) {
            return DomainValues.DEVICE_STATUS_OFFLINE;
        }
        return DomainValues.DEVICE_STATUS_ONLINE;
    }

    public String resumedRuntimeStatus(DeviceRuntimeStateEntity runtime) {
        return runtime.isOnline()
                ? DomainValues.DEVICE_STATUS_ONLINE
                : DomainValues.DEVICE_STATUS_OFFLINE;
    }

    public boolean isActiveAttempt(TaskAttemptEntity attempt) {
        return attempt != null && DomainValues.ACTIVE_ATTEMPT_STATUSES.contains(attempt.getStatus());
    }

    private boolean isStartableAttempt(TaskAttemptEntity attempt) {
        return attempt != null && (
                DomainValues.ATTEMPT_STATUS_CREATED.equals(attempt.getStatus())
                        || DomainValues.ATTEMPT_STATUS_LEASED.equals(attempt.getStatus())
        );
    }

    public enum CancelAction {
        CANCEL_DIRECTLY,
        ENQUEUE_CANCEL_COMMAND
    }
}
