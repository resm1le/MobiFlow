package com.example.platform.ai.api.dto;

public enum RetryRecommendationDto {
    NO_RETRY,
    RETRY_SAME_DEVICE,
    RETRY_OTHER_DEVICE,
    INSPECT_PROFILE,
    INSPECT_ENVIRONMENT,
    ESCALATE_OPERATOR
}
