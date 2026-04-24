package com.example.platform.ai.api.dto;

public enum SuggestedNextActionDto {
    NONE,
    RETRY_TARGET,
    RETRY_ON_OTHER_DEVICE,
    INSPECT_ARTIFACTS,
    INSPECT_DEVICE_HEALTH,
    INSPECT_PROFILE_LOGIC,
    CHECK_CONTROL_PLANE,
    MANUAL_REVIEW
}
