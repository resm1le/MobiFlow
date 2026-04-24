package com.example.platform.control.application;

import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import com.example.platform.control.infrastructure.mapper.DeviceCommandMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import com.example.platform.control.infrastructure.mapper.TaskMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RuntimeMaintenanceService {

    private static final Logger log = LoggerFactory.getLogger(RuntimeMaintenanceService.class);

    private final TaskAttemptMapper attemptMapper;
    private final TaskMapper taskMapper;
    private final DeviceRuntimeStateMapper runtimeStateMapper;
    private final DeviceCommandMapper commandMapper;
    private final ControlStateRules controlStateRules;
    private final ExperimentRunService experimentRunService;

    public RuntimeMaintenanceService(TaskAttemptMapper attemptMapper,
                                     TaskMapper taskMapper,
                                     DeviceRuntimeStateMapper runtimeStateMapper,
                                     DeviceCommandMapper commandMapper,
                                     ControlStateRules controlStateRules,
                                     ExperimentRunService experimentRunService) {
        this.attemptMapper = attemptMapper;
        this.taskMapper = taskMapper;
        this.runtimeStateMapper = runtimeStateMapper;
        this.commandMapper = commandMapper;
        this.controlStateRules = controlStateRules;
        this.experimentRunService = experimentRunService;
    }

    @Transactional
    public int reapExpiredLeases(long now) {
        int reaped = 0;
        for (TaskAttemptEntity attempt : attemptMapper.findExpiredActiveAttempts(now)) {
            int updated = attemptMapper.finishIfActive(
                    attempt.getAttemptId(),
                    DomainValues.ATTEMPT_STATUS_LEASE_EXPIRED,
                    "LEASE_EXPIRED",
                    "lease expired during execution",
                    null,
                    null,
                    now,
                    now
            );
            if (updated != 1) {
                log.info("lease.reap_skipped taskId={} attemptId={} deviceId={} reason=attempt_not_active",
                        attempt.getTaskId(),
                        attempt.getAttemptId(),
                        attempt.getDeviceId());
                continue;
            }
            TaskEntity task = taskMapper.findById(attempt.getTaskId());
            if (task != null) {
                taskMapper.updateStatus(task.getTaskId(), DomainValues.TASK_STATUS_FAILED, task.getScheduleVersion(), now);
            }
            DeviceRuntimeStateEntity runtime = runtimeStateMapper.findById(attempt.getDeviceId());
            if (runtime != null) {
                runtimeStateMapper.updateAssignmentIfCurrent(
                        attempt.getDeviceId(),
                        attempt.getAttemptId(),
                        false,
                        controlStateRules.releasedRuntimeStatus(runtime),
                        null,
                        null,
                        null,
                        null,
                        now
                );
            }
            log.info("lease.reap taskId={} attemptId={} deviceId={} scheduleVersion={}",
                    attempt.getTaskId(),
                    attempt.getAttemptId(),
                    attempt.getDeviceId(),
                    task == null ? null : task.getScheduleVersion());
            if (task != null) {
                TaskAttemptEntity finishedAttempt = attemptMapper.findById(attempt.getAttemptId());
                experimentRunService.onAttemptFinished(task, finishedAttempt, "LEASE_EXPIRED", "lease expired during execution", now);
            }
            reaped++;
        }
        return reaped;
    }

    @Transactional
    public int reconcileOfflineDevices(long now, long offlineThresholdMs) {
        long threshold = now - offlineThresholdMs;
        return runtimeStateMapper.markOfflineStale(threshold, now);
    }

    @Transactional
    public int clearExpiredCommands(long now) {
        return commandMapper.deleteExpiredPending(now);
    }

    @Transactional
    public int reconcileQueuedRunTimeouts(long now) {
        return experimentRunService.reconcileQueuedTimeouts(now);
    }
}
