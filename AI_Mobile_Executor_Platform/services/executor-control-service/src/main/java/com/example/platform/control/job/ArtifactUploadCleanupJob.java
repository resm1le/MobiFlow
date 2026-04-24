package com.example.platform.control.job;

import com.example.platform.control.application.ArtifactUploadService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Clock;

@Component
public class ArtifactUploadCleanupJob {

    private final ArtifactUploadService artifactUploadService;
    private final Clock clock = Clock.systemUTC();

    public ArtifactUploadCleanupJob(ArtifactUploadService artifactUploadService) {
        this.artifactUploadService = artifactUploadService;
    }

    @Scheduled(fixedDelayString = "${platform.control.artifacts.cleanup-interval-ms:60000}")
    public void run() {
        artifactUploadService.cleanupExpiredUploads(clock.millis());
    }
}
