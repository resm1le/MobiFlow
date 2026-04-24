package com.example.platform.control.job;

import com.example.platform.control.application.RuntimeMaintenanceService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Clock;

@Component
public class RunMaintenanceJob {

    private final RuntimeMaintenanceService runtimeMaintenanceService;
    private final Clock clock = Clock.systemUTC();

    public RunMaintenanceJob(RuntimeMaintenanceService runtimeMaintenanceService) {
        this.runtimeMaintenanceService = runtimeMaintenanceService;
    }

    @Scheduled(fixedDelayString = "${platform.control.jobs.run-maintenance-interval-ms:10000}")
    public void run() {
        runtimeMaintenanceService.reconcileQueuedRunTimeouts(clock.millis());
    }
}
