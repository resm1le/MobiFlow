package com.example.platform.control.application;

import com.example.platform.control.api.ExecutorAuthContext;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import org.springframework.stereotype.Component;

import java.util.Objects;

@Component
public class AttemptAccessValidator {

    private final TaskAttemptMapper attemptMapper;

    public AttemptAccessValidator(TaskAttemptMapper attemptMapper) {
        this.attemptMapper = attemptMapper;
    }

    public TaskAttemptEntity requireAttempt(String attemptId) {
        TaskAttemptEntity attempt = attemptMapper.findById(attemptId);
        if (attempt == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.ATTEMPT_NOT_FOUND);
        }
        return attempt;
    }

    public TaskAttemptEntity requireOwnedAttempt(ExecutorAuthContext authContext, String attemptId) {
        TaskAttemptEntity attempt = requireAttempt(attemptId);
        if (!Objects.equals(authContext.deviceId(), attempt.getDeviceId())) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.ATTEMPT_OWNERSHIP_INVALID);
        }
        return attempt;
    }

    public void validateAttemptReference(TaskAttemptEntity attempt, String pathAttemptId, String requestAttemptId) {
        if (requestAttemptId != null && !Objects.equals(pathAttemptId, requestAttemptId)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.EXECUTOR_IDENTITY_MISMATCH);
        }
        if (!Objects.equals(attempt.getAttemptId(), pathAttemptId)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.EXECUTOR_IDENTITY_MISMATCH);
        }
    }

    public void validateTaskReference(TaskAttemptEntity attempt, String taskId) {
        if (taskId != null && !Objects.equals(attempt.getTaskId(), taskId)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.EXECUTOR_IDENTITY_MISMATCH);
        }
    }

    public void validateDeviceReference(TaskAttemptEntity attempt, ExecutorAuthContext authContext, String deviceId) {
        if (!Objects.equals(attempt.getDeviceId(), authContext.deviceId())
                || (deviceId != null && !Objects.equals(authContext.deviceId(), deviceId))) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.EXECUTOR_IDENTITY_MISMATCH);
        }
    }

    public void validateRunReference(TaskAttemptEntity attempt, String runId) {
        if (attempt.getRunId() != null && runId != null && !Objects.equals(attempt.getRunId(), runId)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.EXECUTOR_IDENTITY_MISMATCH);
        }
    }
}
