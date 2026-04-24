package com.example.platform.control.application;

import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ControlStateRulesTest {

    private ControlStateRules controlStateRules;

    @BeforeEach
    void setUp() {
        controlStateRules = new ControlStateRules();
    }

    @Test
    void claimRequiresRegisteredOnlineAndNonQuiescedRuntime() {
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setRegistered(true);
        runtime.setOnline(true);
        runtime.setBusy(false);
        runtime.setStatus(DomainValues.DEVICE_STATUS_ONLINE);

        assertTrue(controlStateRules.isClaimAllowed(runtime));

        runtime.setBusy(true);
        assertFalse(controlStateRules.isClaimAllowed(runtime));

        runtime.setBusy(false);
        runtime.setStatus(DomainValues.DEVICE_STATUS_QUIESCED);
        assertFalse(controlStateRules.isClaimAllowed(runtime));
    }

    @Test
    void cancelTaskAllowsQueuedAndActiveRunningOnly() {
        TaskEntity queuedTask = new TaskEntity();
        queuedTask.setStatus(DomainValues.TASK_STATUS_QUEUED);
        assertEquals(ControlStateRules.CancelAction.CANCEL_DIRECTLY, controlStateRules.validateTaskCancellation(queuedTask, null));

        TaskEntity runningTask = new TaskEntity();
        runningTask.setStatus(DomainValues.TASK_STATUS_RUNNING);
        TaskAttemptEntity runningAttempt = new TaskAttemptEntity();
        runningAttempt.setStatus(DomainValues.ATTEMPT_STATUS_RUNNING);
        assertEquals(ControlStateRules.CancelAction.ENQUEUE_CANCEL_COMMAND,
                controlStateRules.validateTaskCancellation(runningTask, runningAttempt));

        TaskAttemptEntity finishedAttempt = new TaskAttemptEntity();
        finishedAttempt.setStatus(DomainValues.ATTEMPT_STATUS_SUCCEEDED);
        ResponseStatusException attemptException = assertThrows(
                ResponseStatusException.class,
                () -> controlStateRules.validateTaskCancellation(runningTask, finishedAttempt)
        );
        assertEquals(ControlErrorCode.TASK_STATE_INVALID, attemptException.getReason());

        TaskEntity finishedTask = new TaskEntity();
        finishedTask.setStatus(DomainValues.TASK_STATUS_FAILED);
        ResponseStatusException taskException = assertThrows(
                ResponseStatusException.class,
                () -> controlStateRules.validateTaskCancellation(finishedTask, runningAttempt)
        );
        assertEquals(ControlErrorCode.TASK_STATE_INVALID, taskException.getReason());
    }

    @Test
    void resumeRequiresQuiescedRuntime() {
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setStatus(DomainValues.DEVICE_STATUS_QUIESCED);
        controlStateRules.validateRuntimeCanResume(runtime);

        runtime.setStatus(DomainValues.DEVICE_STATUS_ONLINE);
        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> controlStateRules.validateRuntimeCanResume(runtime)
        );
        assertEquals(ControlErrorCode.DEVICE_STATE_INVALID, exception.getReason());
    }

    @Test
    void releasedRuntimeStatusPreservesQuiescedAndOfflineSignals() {
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setStatus(DomainValues.DEVICE_STATUS_QUIESCED);
        runtime.setOnline(true);
        assertEquals(DomainValues.DEVICE_STATUS_QUIESCED, controlStateRules.releasedRuntimeStatus(runtime));

        runtime.setStatus(DomainValues.DEVICE_STATUS_OFFLINE);
        runtime.setOnline(false);
        assertEquals(DomainValues.DEVICE_STATUS_OFFLINE, controlStateRules.releasedRuntimeStatus(runtime));

        runtime.setStatus(DomainValues.DEVICE_STATUS_ONLINE);
        runtime.setOnline(true);
        assertEquals(DomainValues.DEVICE_STATUS_ONLINE, controlStateRules.releasedRuntimeStatus(runtime));
    }
}
