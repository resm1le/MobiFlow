package com.example.platform.control.application;

import com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import com.example.platform.control.domain.PersistenceModels.DevicePoolEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.infrastructure.mapper.DeviceMapper;
import com.example.platform.control.infrastructure.mapper.DevicePoolMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Component
public class RunPlanningContextBuilder {

    private static final int DEFAULT_PRIORITY = 100;
    private static final int DEFAULT_MAX_RETRIES_PER_DEVICE = 0;
    private static final long DEFAULT_QUEUE_TIMEOUT_MS = 300_000L;

    private final DevicePoolMapper devicePoolMapper;
    private final DeviceMapper deviceMapper;
    private final DeviceRuntimeStateMapper runtimeStateMapper;
    private final JsonCodec jsonCodec;
    private final ControlProperties controlProperties;

    public RunPlanningContextBuilder(DevicePoolMapper devicePoolMapper,
                                     DeviceMapper deviceMapper,
                                     DeviceRuntimeStateMapper runtimeStateMapper,
                                     JsonCodec jsonCodec,
                                     ControlProperties controlProperties) {
        this.devicePoolMapper = devicePoolMapper;
        this.deviceMapper = deviceMapper;
        this.runtimeStateMapper = runtimeStateMapper;
        this.jsonCodec = jsonCodec;
        this.controlProperties = controlProperties;
    }

    public Phase3AiModels.RunPlanningContext build(String goal, Map<String, Object> constraints) {
        Map<String, DeviceRuntimeStateEntity> runtimes = runtimeStateMapper.findAll().stream()
                .collect(Collectors.toMap(DeviceRuntimeStateEntity::getDeviceId, Function.identity()));
        List<DeviceEntity> devices = deviceMapper.findAll();
        List<Phase3AiModels.AvailableDevicePool> pools = devicePoolMapper.findAll().stream()
                .map(pool -> toAvailableDevicePool(pool, devices, runtimes))
                .sorted(Comparator.comparing(Phase3AiModels.AvailableDevicePool::name))
                .toList();
        List<Phase3AiModels.AvailableProfile> profiles = toAvailableProfiles(devices, runtimes);
        return new Phase3AiModels.RunPlanningContext(
                goal,
                constraints == null ? Map.of() : Map.copyOf(constraints),
                pools,
                profiles,
                defaultRunPolicy(),
                DomainValues.ALLOWED_AI_TASK_TYPES.stream().sorted().toList()
        );
    }

    private Phase3AiModels.AvailableDevicePool toAvailableDevicePool(DevicePoolEntity pool,
                                                                     List<DeviceEntity> devices,
                                                                     Map<String, DeviceRuntimeStateEntity> runtimes) {
        Set<String> selectedIds = Set.copyOf(jsonCodec.readStringList(pool.getDeviceIdsJson()));
        Set<String> requiredTags = Set.copyOf(jsonCodec.readStringList(pool.getRequiredTagsJson()));
        Set<String> excludedTags = Set.copyOf(jsonCodec.readStringList(pool.getExcludedTagsJson()));
        int deviceCount = (int) devices.stream()
                .filter(device -> ExperimentRunSelectors.matchesPool(device, runtimes.get(device.getDeviceId()), pool.getHostGroup(), selectedIds, requiredTags, excludedTags, jsonCodec))
                .count();
        return new Phase3AiModels.AvailableDevicePool(
                pool.getPoolId(),
                pool.getName(),
                pool.getHostGroup(),
                deviceCount,
                List.copyOf(requiredTags),
                List.copyOf(excludedTags)
        );
    }

    private List<Phase3AiModels.AvailableProfile> toAvailableProfiles(List<DeviceEntity> devices,
                                                                      Map<String, DeviceRuntimeStateEntity> runtimes) {
        Map<String, Integer> deviceCounts = new LinkedHashMap<>();
        for (DeviceEntity device : devices) {
            DeviceRuntimeStateEntity runtime = runtimes.get(device.getDeviceId());
            if (runtime == null || !runtime.isRegistered()) {
                continue;
            }
            for (String profile : jsonCodec.readStringList(device.getInstalledProfilesJson())) {
                if (profile != null && !profile.isBlank()) {
                    deviceCounts.merge(profile, 1, Integer::sum);
                }
            }
        }
        List<Phase3AiModels.AvailableProfile> profiles = new ArrayList<>();
        for (Map.Entry<String, Integer> entry : deviceCounts.entrySet()) {
            Map<String, Object> defaults = new LinkedHashMap<>();
            defaults.put("runConfig", defaultRunConfigMap());
            defaults.put("artifactPolicy", defaultArtifactPolicyMap());
            defaults.put("priority", DEFAULT_PRIORITY);
            defaults.put("maxRetriesPerDevice", DEFAULT_MAX_RETRIES_PER_DEVICE);
            defaults.put("queueTimeoutMs", DEFAULT_QUEUE_TIMEOUT_MS);
            profiles.add(new Phase3AiModels.AvailableProfile(
                    entry.getKey(),
                    entry.getValue(),
                    DomainValues.ALLOWED_AI_TASK_TYPES.stream().sorted().toList(),
                    List.of("goal"),
                    defaults,
                    List.of("Profile-specific payload fields must be reviewed by an operator before materialization.")
            ));
        }
        profiles.sort(Comparator.comparing(Phase3AiModels.AvailableProfile::profilePackage));
        return profiles;
    }

    private Phase3AiModels.DefaultRunPolicy defaultRunPolicy() {
        return new Phase3AiModels.DefaultRunPolicy(
                DEFAULT_PRIORITY,
                DEFAULT_MAX_RETRIES_PER_DEVICE,
                DEFAULT_QUEUE_TIMEOUT_MS,
                defaultRunConfigMap(),
                defaultArtifactPolicyMap()
        );
    }

    private Map<String, Object> defaultRunConfigMap() {
        ControlProperties.DefaultRunConfig runConfig = controlProperties.getDefaultRunConfig();
        Map<String, Object> defaults = new LinkedHashMap<>();
        defaults.put("loopCount", runConfig.getLoopCount());
        defaults.put("budgetMs", runConfig.getBudgetMs());
        defaults.put("loopIntervalMs", runConfig.getLoopIntervalMs());
        defaults.put("networkIsolationEnabled", runConfig.isNetworkIsolationEnabled());
        defaults.put("pollIntervalMs", runConfig.getPollIntervalMs());
        defaults.put("heartbeatIntervalMs", runConfig.getHeartbeatIntervalMs());
        return defaults;
    }

    private Map<String, Object> defaultArtifactPolicyMap() {
        ArtifactPolicy defaults = new ArtifactPolicy(true, true, true);
        Map<String, Object> artifactPolicy = new LinkedHashMap<>();
        artifactPolicy.put("uploadLog", defaults.uploadLog());
        artifactPolicy.put("uploadScreenshot", defaults.uploadScreenshot());
        artifactPolicy.put("uploadDump", defaults.uploadDump());
        return artifactPolicy;
    }
}
