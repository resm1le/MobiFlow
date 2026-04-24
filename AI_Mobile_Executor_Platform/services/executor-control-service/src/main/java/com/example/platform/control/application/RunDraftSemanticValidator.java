package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels.CreateTaskRequest;
import com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy;
import com.example.platform.control.api.ExecutorApiModels.RunConfig;
import com.example.platform.control.domain.PersistenceModels.DevicePoolEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.infrastructure.mapper.DeviceMapper;
import com.example.platform.control.infrastructure.mapper.DevicePoolMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Component
public class RunDraftSemanticValidator {

    private final DevicePoolMapper devicePoolMapper;
    private final DeviceMapper deviceMapper;
    private final DeviceRuntimeStateMapper runtimeStateMapper;
    private final TaskRequestValidator taskRequestValidator;
    private final JsonCodec jsonCodec;

    public RunDraftSemanticValidator(DevicePoolMapper devicePoolMapper,
                                     DeviceMapper deviceMapper,
                                     DeviceRuntimeStateMapper runtimeStateMapper,
                                     TaskRequestValidator taskRequestValidator,
                                     JsonCodec jsonCodec) {
        this.devicePoolMapper = devicePoolMapper;
        this.deviceMapper = deviceMapper;
        this.runtimeStateMapper = runtimeStateMapper;
        this.taskRequestValidator = taskRequestValidator;
        this.jsonCodec = jsonCodec;
    }

    public Phase3AiModels.ValidationResult validate(Phase3AiModels.RunDraftResult result) {
        List<String> errors = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        if (result == null || result.runDraft() == null) {
            return new Phase3AiModels.ValidationResult(false, List.of("runDraft must be present"), List.of());
        }
        Phase3AiModels.RunDraft draft = result.runDraft();
        DevicePoolEntity pool = devicePoolMapper.findById(draft.devicePoolId());
        if (pool == null) {
            errors.add("devicePoolId must reference an existing device pool");
        }
        try {
            taskRequestValidator.validateAndNormalize(new CreateTaskRequest(
                    draft.taskType(),
                    draft.profilePackage(),
                    draft.taskPayload(),
                    toRunConfig(draft.runConfig()),
                    toArtifactPolicy(draft.artifactPolicy()),
                    draft.priority(),
                    draft.labels(),
                    "ai-phase3",
                    "phase3-validator",
                    null
            ));
        } catch (RuntimeException exception) {
            errors.add("taskPayload and execution config failed semantic validation");
        }
        if (draft.maxRetriesPerDevice() < 0) {
            errors.add("maxRetriesPerDevice must be non-negative");
        }
        if (draft.queueTimeoutMs() < 1_000L) {
            errors.add("queueTimeoutMs must be at least 1000");
        }
        if (pool != null && !hasAnyEligibleDevice(pool, draft.profilePackage())) {
            errors.add("selected pool does not currently contain any online registered device with the requested profile");
        }
        if (draft.labels() != null && draft.labels().stream().anyMatch("phase3-ai"::equals)) {
            warnings.add("phase3-ai labels are reserved for internal auditing and should be operator-reviewed");
        }
        return new Phase3AiModels.ValidationResult(errors.isEmpty(), List.copyOf(errors), List.copyOf(warnings));
    }

    private boolean hasAnyEligibleDevice(DevicePoolEntity pool, String profilePackage) {
        Map<String, DeviceRuntimeStateEntity> runtimes = runtimeStateMapper.findAll().stream()
                .collect(Collectors.toMap(DeviceRuntimeStateEntity::getDeviceId, Function.identity()));
        Set<String> selectedIds = Set.copyOf(jsonCodec.readStringList(pool.getDeviceIdsJson()));
        Set<String> requiredTags = Set.copyOf(jsonCodec.readStringList(pool.getRequiredTagsJson()));
        Set<String> excludedTags = Set.copyOf(jsonCodec.readStringList(pool.getExcludedTagsJson()));
        return deviceMapper.findAll().stream()
                .filter(device -> ExperimentRunSelectors.matchesPool(
                        device,
                        runtimes.get(device.getDeviceId()),
                        pool.getHostGroup(),
                        selectedIds,
                        requiredTags,
                        excludedTags,
                        jsonCodec
                ))
                .anyMatch(device -> jsonCodec.readStringList(device.getInstalledProfilesJson()).contains(profilePackage));
    }

    private RunConfig toRunConfig(Map<String, Object> map) {
        return new RunConfig(
                ((Number) map.get("loopCount")).intValue(),
                ((Number) map.get("budgetMs")).longValue(),
                ((Number) map.get("loopIntervalMs")).longValue(),
                Boolean.TRUE.equals(map.get("networkIsolationEnabled")),
                ((Number) map.get("pollIntervalMs")).longValue(),
                ((Number) map.get("heartbeatIntervalMs")).longValue()
        );
    }

    private ArtifactPolicy toArtifactPolicy(Map<String, Object> map) {
        return new ArtifactPolicy(
                Boolean.TRUE.equals(map.get("uploadLog")),
                Boolean.TRUE.equals(map.get("uploadScreenshot")),
                Boolean.TRUE.equals(map.get("uploadDump"))
        );
    }
}
