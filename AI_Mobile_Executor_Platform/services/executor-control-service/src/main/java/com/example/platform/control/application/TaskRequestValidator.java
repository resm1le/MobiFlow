package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels.CreateTaskRequest;
import com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy;
import com.example.platform.control.api.ExecutorApiModels.RunConfig;
import com.example.platform.control.domain.DomainValues;
import org.springframework.stereotype.Component;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

@Component
public class TaskRequestValidator {

    private static final Pattern ANDROID_PACKAGE_PATTERN = Pattern.compile("^[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+$");
    private static final int DEFAULT_PRIORITY = 100;
    private static final int MAX_PRIORITY = 1000;
    private static final int MAX_LABELS = 16;
    private static final int MAX_PAYLOAD_KEYS = 32;

    public NormalizedTaskRequest validateAndNormalize(CreateTaskRequest request) {
        String taskType = normalizeTaskType(request.taskType());
        String profilePackage = normalizeProfilePackage(request.profilePackage());
        Map<String, Object> taskPayload = normalizePayload(taskType, request.taskPayload());
        RunConfig runConfig = normalizeRunConfig(request.runConfig());
        ArtifactPolicy artifactPolicy = normalizeArtifactPolicy(request.artifactPolicy());
        int priority = normalizePriority(request.priority());
        List<String> labels = normalizeLabels(request.labels());
        String source = normalizeOrDefault(request.source(), "manual");
        String createdBy = normalizeOrDefault(request.createdBy(), "console");
        String idempotencyKey = normalizeOptional(request.idempotencyKey());

        return new NormalizedTaskRequest(
                taskType,
                profilePackage,
                taskPayload,
                runConfig,
                artifactPolicy,
                priority,
                labels,
                source,
                createdBy,
                idempotencyKey
        );
    }

    private String normalizeTaskType(String taskType) {
        String normalized = normalizeOptional(taskType);
        if (normalized == null || !DomainValues.ALLOWED_TASK_TYPES.contains(normalized)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
        }
        return normalized;
    }

    private String normalizeProfilePackage(String profilePackage) {
        String normalized = normalizeOptional(profilePackage);
        if (normalized == null || !ANDROID_PACKAGE_PATTERN.matcher(normalized).matches()) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.PROFILE_PACKAGE_INVALID);
        }
        return normalized;
    }

    private Map<String, Object> normalizePayload(String taskType, Map<String, Object> taskPayload) {
        if (taskPayload == null || taskPayload.isEmpty() || taskPayload.size() > MAX_PAYLOAD_KEYS) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
        }
        boolean invalidKey = taskPayload.keySet().stream()
                .anyMatch(key -> key == null || key.isBlank());
        if (invalidKey) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
        }

        if ("demo.navigate".equals(taskType)) {
            if (!hasNonBlankPayloadField(taskPayload, "target")
                    && !hasNonBlankPayloadField(taskPayload, "destination")) {
                throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
            }
        } else {
            requireNonBlankPayloadField(taskPayload, "goal");
        }
        return taskPayload;
    }

    private void requireNonBlankPayloadField(Map<String, Object> payload, String key) {
        if (!hasNonBlankPayloadField(payload, key)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
        }
    }

    private boolean hasNonBlankPayloadField(Map<String, Object> payload, String key) {
        Object value = payload.get(key);
        return value instanceof String text && !text.isBlank();
    }

    private RunConfig normalizeRunConfig(RunConfig runConfig) {
        if (runConfig == null
                || runConfig.loopCount() < 1
                || runConfig.loopCount() > 100
                || runConfig.budgetMs() < 1_000
                || runConfig.budgetMs() > 86_400_000
                || runConfig.loopIntervalMs() < 0
                || runConfig.pollIntervalMs() < 1_000
                || runConfig.heartbeatIntervalMs() < 1_000) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
        }
        return runConfig;
    }

    private ArtifactPolicy normalizeArtifactPolicy(ArtifactPolicy artifactPolicy) {
        if (artifactPolicy == null
                || (!artifactPolicy.uploadLog()
                && !artifactPolicy.uploadScreenshot()
                && !artifactPolicy.uploadDump())) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
        }
        return artifactPolicy;
    }

    private int normalizePriority(Integer priority) {
        int normalized = priority == null ? DEFAULT_PRIORITY : priority;
        if (normalized < 0 || normalized > MAX_PRIORITY) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
        }
        return normalized;
    }

    private List<String> normalizeLabels(List<String> labels) {
        if (labels == null || labels.isEmpty()) {
            return List.of();
        }
        if (labels.size() > MAX_LABELS) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
        }
        Set<String> normalized = new LinkedHashSet<>();
        for (String label : labels) {
            String value = normalizeOptional(label);
            if (value == null) {
                throw ControlApiExceptions.badRequest(ControlErrorCode.TASK_STATE_INVALID);
            }
            normalized.add(value);
        }
        return List.copyOf(normalized);
    }

    private String normalizeOrDefault(String value, String fallback) {
        String normalized = normalizeOptional(value);
        return normalized == null ? fallback : normalized;
    }

    private String normalizeOptional(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    public record NormalizedTaskRequest(
            String taskType,
            String profilePackage,
            Map<String, Object> taskPayload,
            RunConfig runConfig,
            ArtifactPolicy artifactPolicy,
            int priority,
            List<String> labels,
            String source,
            String createdBy,
            String idempotencyKey
    ) {
    }
}
