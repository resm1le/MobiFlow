package com.example.platform.control.job;

import com.example.platform.control.application.RuntimeMaintenanceService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Clock;

@Component
public class CommandExpiryJob {

    private final RuntimeMaintenanceService runtimeMaintenanceService;
    private final Clock clock = Clock.systemUTC();

    public CommandExpiryJob(RuntimeMaintenanceService runtimeMaintenanceService) {
        this.runtimeMaintenanceService = runtimeMaintenanceService;
    }

    @Scheduled(fixedDelayString = "${platform.control.jobs.command-expiry-interval-ms:10000}")
    public void run() {
        runtimeMaintenanceService.clearExpiredCommands(clock.millis());
    }
}
