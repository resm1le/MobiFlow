package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.ArtifactPolicyDto;

public record RunPlanningIntentSignals(
        String devicePoolId,
        String profilePackage,
        Integer priority,
        Integer loopCount,
        Long budgetMs,
        Boolean networkIsolationEnabled,
        String taskType,
        Integer maxRetriesPerDevice,
        Long queueTimeoutMs,
        ArtifactPolicyDto artifactPolicy
) {

    public boolean hasExplicitDevicePoolId() {
        return devicePoolId != null && !devicePoolId.isBlank();
    }

    public boolean hasExplicitProfilePackage() {
        return profilePackage != null && !profilePackage.isBlank();
    }

    public boolean hasExplicitPriority() {
        return priority != null;
    }

    public boolean hasExplicitLoopCount() {
        return loopCount != null;
    }

    public boolean hasExplicitBudgetMs() {
        return budgetMs != null;
    }

    public boolean hasExplicitNetworkIsolationEnabled() {
        return networkIsolationEnabled != null;
    }

    public boolean hasExplicitTaskType() {
        return taskType != null && !taskType.isBlank();
    }

    public boolean hasExplicitMaxRetriesPerDevice() {
        return maxRetriesPerDevice != null;
    }

    public boolean hasExplicitQueueTimeoutMs() {
        return queueTimeoutMs != null;
    }

    public boolean hasExplicitArtifactPolicy() {
        return artifactPolicy != null;
    }
}
