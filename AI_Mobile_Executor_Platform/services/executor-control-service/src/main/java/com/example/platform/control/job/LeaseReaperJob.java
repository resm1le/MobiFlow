package com.example.platform.control.job;

import com.example.platform.control.application.RuntimeMaintenanceService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Clock;

@Component
public class LeaseReaperJob {

    private final RuntimeMaintenanceService runtimeMaintenanceService;
    private final Clock clock = Clock.systemUTC();

    public LeaseReaperJob(RuntimeMaintenanceService runtimeMaintenanceService) {
        this.runtimeMaintenanceService = runtimeMaintenanceService;
    }

    @Scheduled(fixedDelayString = "${platform.control.jobs.lease-reaper-interval-ms:5000}")
    public void run() {
        runtimeMaintenanceService.reapExpiredLeases(clock.millis());
    }
}
