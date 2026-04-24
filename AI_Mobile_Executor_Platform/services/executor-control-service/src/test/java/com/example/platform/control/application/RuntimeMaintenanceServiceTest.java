package com.example.platform.control.application;

import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import com.example.platform.control.infrastructure.mapper.DeviceCommandMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import com.example.platform.control.infrastructure.mapper.TaskMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RuntimeMaintenanceServiceTest {

    private TaskAttemptMapper attemptMapper;
    private TaskMapper taskMapper;
    private DeviceRuntimeStateMapper runtimeStateMapper;
    private DeviceCommandMapper commandMapper;
    private ExperimentRunService experimentRunService;
    private RuntimeMaintenanceService runtimeMaintenanceService;

    @BeforeEach
    void setUp() {
        attemptMapper = Mockito.mock(TaskAttemptMapper.class);
        taskMapper = Mockito.mock(TaskMapper.class);
        runtimeStateMapper = Mockito.mock(DeviceRuntimeStateMapper.class);
        commandMapper = Mockito.mock(DeviceCommandMapper.class);
        experimentRunService = Mockito.mock(ExperimentRunService.class);
        runtimeMaintenanceService = new RuntimeMaintenanceService(
                attemptMapper,
                taskMapper,
                runtimeStateMapper,
                commandMapper,
                new ControlStateRules(),
                experimentRunService
        );
    }

    @Test
    void reapsExpiredLeaseAndReleasesRuntime() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setDeviceId("device-1");
        when(attemptMapper.findExpiredActiveAttempts(1000L)).thenReturn(List.of(attempt));
        when(attemptMapper.finishIfActive(anyString(), anyString(), anyString(), anyString(), any(), any(), anyLong(), anyLong())).thenReturn(1);

        TaskEntity task = new TaskEntity();
        task.setTaskId("task-1");
        task.setScheduleVersion("sched-v1");
        when(taskMapper.findById("task-1")).thenReturn(task);

        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId("device-1");
        runtime.setStatus(DomainValues.DEVICE_STATUS_ONLINE);
        runtime.setOnline(true);
        when(runtimeStateMapper.findById("device-1")).thenReturn(runtime);

        int reaped = runtimeMaintenanceService.reapExpiredLeases(1000L);

        assertEquals(1, reaped);
        verify(taskMapper).updateStatus("task-1", DomainValues.TASK_STATUS_FAILED, "sched-v1", 1000L);
        verify(runtimeStateMapper).updateAssignmentIfCurrent("device-1", "attempt-1", false, DomainValues.DEVICE_STATUS_ONLINE, null, null, null, null, 1000L);
    }

    @Test
    void reconcilesOfflineDevicesUsingThreshold() {
        when(runtimeStateMapper.markOfflineStale(1000L, 4000L)).thenReturn(1);

        int reconciled = runtimeMaintenanceService.reconcileOfflineDevices(4000L, 3000L);

        assertEquals(1, reconciled);
    }

    @Test
    void clearsExpiredPendingCommands() {
        when(commandMapper.deleteExpiredPending(5000L)).thenReturn(2);

        int cleared = runtimeMaintenanceService.clearExpiredCommands(5000L);

        assertEquals(2, cleared);
    }

    @Test
    void leaseReaperOnlyClearsRuntimeWhenAssignmentStillMatches() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setDeviceId("device-1");
        when(attemptMapper.findExpiredActiveAttempts(1000L)).thenReturn(List.of(attempt));
        when(attemptMapper.finishIfActive(anyString(), anyString(), anyString(), anyString(), any(), any(), anyLong(), anyLong())).thenReturn(1);

        TaskEntity task = new TaskEntity();
        task.setTaskId("task-1");
        task.setScheduleVersion("sched-v1");
        when(taskMapper.findById("task-1")).thenReturn(task);
        when(runtimeStateMapper.findById("device-1")).thenReturn(null);

        int reaped = runtimeMaintenanceService.reapExpiredLeases(1000L);

        assertEquals(1, reaped);
        verify(runtimeStateMapper, never()).updateAssignmentIfCurrent(anyString(), anyString(), org.mockito.ArgumentMatchers.anyBoolean(), anyString(), any(), any(), any(), any(), anyLong());
    }

    @Test
    void leaseReaperSkipsAlreadyFinishedAttempt() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-2");
        attempt.setTaskId("task-2");
        attempt.setDeviceId("device-2");
        when(attemptMapper.findExpiredActiveAttempts(1000L)).thenReturn(List.of(attempt));
        when(attemptMapper.finishIfActive(anyString(), anyString(), anyString(), anyString(), any(), any(), anyLong(), anyLong())).thenReturn(0);

        int reaped = runtimeMaintenanceService.reapExpiredLeases(1000L);

        assertEquals(0, reaped);
        verify(taskMapper, never()).updateStatus(anyString(), anyString(), anyString(), anyLong());
        verify(runtimeStateMapper, never()).updateAssignmentIfCurrent(anyString(), anyString(), org.mockito.ArgumentMatchers.anyBoolean(), anyString(), any(), any(), any(), any(), anyLong());
    }
}
