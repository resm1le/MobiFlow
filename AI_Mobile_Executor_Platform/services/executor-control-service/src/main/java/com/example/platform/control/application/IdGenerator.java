package com.example.platform.control.application;

import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
public class IdGenerator {

    public String nextTaskId() {
        return "task-" + compact();
    }

    public String nextAttemptId() {
        return "attempt-" + compact();
    }

    public String nextRunId() {
        return "run-" + compact();
    }

    public String nextRunTargetId() {
        return "target-" + compact();
    }

    public String nextDevicePoolId() {
        return "pool-" + compact();
    }

    public String nextArtifactId() {
        return "artifact-" + compact();
    }

    public String nextAiRunPlanRequestId() {
        return "airunplan-" + compact();
    }

    public String nextAiFailureTriageResultId() {
        return "aitriage-" + compact();
    }

    public String nextAiRunSummaryId() {
        return "aisummary-" + compact();
    }

    public String nextToolAuditId() {
        return "toolaudit-" + compact();
    }

    public String nextToolConfirmationId() {
        return "toolconfirm-" + compact();
    }

    private String compact() {
        return UUID.randomUUID().toString().replace("-", "");
    }
}
