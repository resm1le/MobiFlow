package com.example.platform.control.job;

import com.example.platform.control.application.ControlProperties;
import com.example.platform.control.application.RuntimeMaintenanceService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Clock;

@Component
public class OfflineDeviceReconcilerJob {

    private final RuntimeMaintenanceService runtimeMaintenanceService;
    private final ControlProperties controlProperties;
    private final Clock clock = Clock.systemUTC();

    public OfflineDeviceReconcilerJob(RuntimeMaintenanceService runtimeMaintenanceService,
                                      ControlProperties controlProperties) {
        this.runtimeMaintenanceService = runtimeMaintenanceService;
        this.controlProperties = controlProperties;
    }

    @Scheduled(fixedDelayString = "${platform.control.jobs.offline-reconciler-interval-ms:10000}")
    public void run() {
        runtimeMaintenanceService.reconcileOfflineDevices(clock.millis(), controlProperties.getJobs().getOfflineThresholdMs());
    }
}
