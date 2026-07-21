package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels.CreateHeterogeneousRunRequest;
import com.example.platform.control.api.AdminApiModels.CreateTaskRequest;
import com.example.platform.control.api.AdminApiModels.DeviceSelector;
import com.example.platform.control.api.AdminApiModels.HeterogeneousDispatchEntry;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.infrastructure.mapper.DeviceMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Component
public class HeterogeneousDispatchResolver {

    private static final int MAX_DISPATCH_ENTRIES = 256;

    private final DeviceMapper deviceMapper;
    private final DeviceRuntimeStateMapper runtimeStateMapper;
    private final TaskRequestValidator taskRequestValidator;
    private final JsonCodec jsonCodec;

    public HeterogeneousDispatchResolver(DeviceMapper deviceMapper,
                                         DeviceRuntimeStateMapper runtimeStateMapper,
                                         TaskRequestValidator taskRequestValidator,
                                         JsonCodec jsonCodec) {
        this.deviceMapper = deviceMapper;
        this.runtimeStateMapper = runtimeStateMapper;
        this.taskRequestValidator = taskRequestValidator;
        this.jsonCodec = jsonCodec;
    }

    public List<ResolvedDispatchEntry> resolve(CreateHeterogeneousRunRequest request) {
        if (request == null || request.dispatch() == null || request.dispatch().isEmpty()
                || request.dispatch().size() > MAX_DISPATCH_ENTRIES) {
            throw badRequest(ControlErrorCode.HETEROGENEOUS_RUN_INVALID);
        }

        List<NormalizedEntry> entries = new ArrayList<>();
        for (int index = 0; index < request.dispatch().size(); index++) {
            HeterogeneousDispatchEntry entry = request.dispatch().get(index);
            if (entry == null) {
                throw badRequest(ControlErrorCode.HETEROGENEOUS_RUN_INVALID);
            }
            String sequenceId = requireNonBlank(entry.sequenceId(), ControlErrorCode.HETEROGENEOUS_RUN_INVALID);
            TaskRequestValidator.NormalizedTaskRequest task = taskRequestValidator.validateAndNormalize(new CreateTaskRequest(
                    request.taskType(),
                    entry.profilePackage(),
                    entry.taskPayload(),
                    request.runConfig(),
                    request.artifactPolicy(),
                    request.priority(),
                    request.labels(),
                    request.source(),
                    request.createdBy(),
                    null
            ));
            validateWaypointPayload(sequenceId, task.profilePackage(), task.taskPayload());
            entries.add(new NormalizedEntry(index, sequenceId, task, normalizeSelector(entry.select())));
        }

        Map<String, DeviceEntity> devicesById = deviceMapper.findAll().stream()
                .collect(Collectors.toMap(DeviceEntity::getDeviceId, Function.identity(), (left, right) -> left));
        Map<String, DeviceRuntimeStateEntity> runtimesById = runtimeStateMapper.findAll().stream()
                .collect(Collectors.toMap(DeviceRuntimeStateEntity::getDeviceId, Function.identity(), (left, right) -> left));
        List<DeviceEntity> sortedDevices = devicesById.values().stream()
                .sorted(Comparator.comparing(DeviceEntity::getDeviceId))
                .toList();

        Set<String> reserved = new HashSet<>();
        Map<Integer, List<String>> assignments = new HashMap<>();

        for (NormalizedEntry entry : entries) {
            if (!entry.selector().named()) {
                continue;
            }
            List<String> selected = new ArrayList<>();
            for (String deviceId : entry.selector().deviceIds()) {
                if (!reserved.add(deviceId)) {
                    throw badRequest(ControlErrorCode.DISPATCH_DEVICE_CONFLICT);
                }
                DeviceEntity device = devicesById.get(deviceId);
                if (!eligible(device, runtimesById.get(deviceId), entry.task().profilePackage())) {
                    throw badRequest(ControlErrorCode.DISPATCH_DEVICE_UNAVAILABLE);
                }
                selected.add(deviceId);
            }
            assignments.put(entry.index(), List.copyOf(selected));
        }

        for (NormalizedEntry entry : entries) {
            if (entry.selector().named()) {
                continue;
            }
            List<String> selected = sortedDevices.stream()
                    .filter(device -> !reserved.contains(device.getDeviceId()))
                    .filter(device -> eligible(device, runtimesById.get(device.getDeviceId()), entry.task().profilePackage()))
                    .filter(device -> matchesTags(device, entry.selector().requiredTags(), entry.selector().excludedTags()))
                    .limit(entry.selector().count())
                    .map(DeviceEntity::getDeviceId)
                    .toList();
            if (selected.size() != entry.selector().count()) {
                throw badRequest(ControlErrorCode.DISPATCH_CAPACITY_INSUFFICIENT);
            }
            reserved.addAll(selected);
            assignments.put(entry.index(), selected);
        }

        return entries.stream()
                .map(entry -> new ResolvedDispatchEntry(
                        entry.sequenceId(), entry.task(), assignments.get(entry.index())))
                .toList();
    }

    private NormalizedSelector normalizeSelector(DeviceSelector selector) {
        if (selector == null) {
            throw badRequest(ControlErrorCode.DISPATCH_SELECTOR_INVALID);
        }
        List<String> deviceIds = normalizeDeviceIds(selector.deviceIds());
        List<String> requiredTags = normalizeStrings(selector.requiredTags());
        List<String> excludedTags = normalizeStrings(selector.excludedTags());
        boolean named = !deviceIds.isEmpty();
        if (named) {
            if (selector.count() != null || !requiredTags.isEmpty() || !excludedTags.isEmpty()) {
                throw badRequest(ControlErrorCode.DISPATCH_SELECTOR_INVALID);
            }
            return new NormalizedSelector(true, 0, deviceIds, List.of(), List.of());
        }
        if (selector.count() == null || selector.count() <= 0) {
            throw badRequest(ControlErrorCode.DISPATCH_SELECTOR_INVALID);
        }
        return new NormalizedSelector(false, selector.count(), List.of(), requiredTags, excludedTags);
    }

    private boolean eligible(DeviceEntity device, DeviceRuntimeStateEntity runtime, String profilePackage) {
        return device != null
                && runtime != null
                && runtime.isRegistered()
                && runtime.isOnline()
                && !runtime.isBusy()
                && !DomainValues.DEVICE_STATUS_QUIESCED.equals(runtime.getStatus())
                && jsonCodec.readStringList(device.getInstalledProfilesJson()).contains(profilePackage);
    }

    private boolean matchesTags(DeviceEntity device, List<String> requiredTags, List<String> excludedTags) {
        Set<String> tags = Set.copyOf(jsonCodec.readStringList(device.getTagsJson()));
        return tags.containsAll(requiredTags) && excludedTags.stream().noneMatch(tags::contains);
    }

    @SuppressWarnings("unchecked")
    private void validateWaypointPayload(String sequenceId, String profilePackage, Map<String, Object> payload) {
        Object sequenceValue = payload.get("waypoint_sequence");
        if (!(sequenceValue instanceof Map<?, ?> rawSequence)) {
            throw badRequest(ControlErrorCode.HETEROGENEOUS_RUN_INVALID);
        }
        Map<String, Object> sequence = (Map<String, Object>) rawSequence;
        if (!Objects.equals(sequenceId, nonBlankValue(sequence.get("sequence_id")))
                || !Objects.equals(profilePackage, nonBlankValue(sequence.get("profile_package")))
                || nonBlankValue(sequence.get("behavior_label")) == null) {
            throw badRequest(ControlErrorCode.HETEROGENEOUS_RUN_INVALID);
        }
        Object waypointValue = sequence.get("waypoints");
        if (!(waypointValue instanceof List<?> waypoints) || waypoints.isEmpty() || waypoints.size() > 256) {
            throw badRequest(ControlErrorCode.HETEROGENEOUS_RUN_INVALID);
        }
        Set<String> waypointIds = new HashSet<>();
        for (Object value : waypoints) {
            if (!(value instanceof Map<?, ?> waypoint)) {
                throw badRequest(ControlErrorCode.HETEROGENEOUS_RUN_INVALID);
            }
            String waypointId = nonBlankValue(waypoint.get("waypoint_id"));
            if (waypointId == null || !waypointIds.add(waypointId)
                    || nonBlankValue(waypoint.get("description")) == null
                    || !(waypoint.get("arrival_spec") instanceof Map<?, ?> arrivalSpec)
                    || nonBlankValue(arrivalSpec.get("verification_id")) == null
                    || nonBlankValue(arrivalSpec.get("target_kind")) == null
                    || nonBlankValue(arrivalSpec.get("target_id")) == null
                    || !(arrivalSpec.get("success_checks") instanceof List<?> successChecks)
                    || successChecks.isEmpty()) {
                throw badRequest(ControlErrorCode.HETEROGENEOUS_RUN_INVALID);
            }
            for (Object checkValue : successChecks) {
                if (!(checkValue instanceof Map<?, ?> check)
                        || nonBlankValue(check.get("check_id")) == null
                        || nonBlankValue(check.get("description")) == null) {
                    throw badRequest(ControlErrorCode.HETEROGENEOUS_RUN_INVALID);
                }
            }
        }
    }

    private List<String> normalizeStrings(List<String> values) {
        if (values == null || values.isEmpty()) {
            return List.of();
        }
        LinkedHashSet<String> normalized = new LinkedHashSet<>();
        for (String value : values) {
            String text = requireNonBlank(value, ControlErrorCode.DISPATCH_SELECTOR_INVALID);
            normalized.add(text);
        }
        return List.copyOf(normalized);
    }

    private List<String> normalizeDeviceIds(List<String> values) {
        if (values == null || values.isEmpty()) {
            return List.of();
        }
        List<String> normalized = new ArrayList<>(values.size());
        Set<String> seen = new HashSet<>();
        for (String value : values) {
            String text = requireNonBlank(value, ControlErrorCode.DISPATCH_SELECTOR_INVALID);
            if (!seen.add(text)) {
                throw badRequest(ControlErrorCode.DISPATCH_DEVICE_CONFLICT);
            }
            normalized.add(text);
        }
        return List.copyOf(normalized);
    }

    private String requireNonBlank(String value, String errorCode) {
        if (value == null || value.isBlank()) {
            throw badRequest(errorCode);
        }
        return value.trim();
    }

    private String nonBlankValue(Object value) {
        return value instanceof String text && !text.isBlank() ? text.trim() : null;
    }

    private RuntimeException badRequest(String errorCode) {
        return ControlApiExceptions.badRequest(errorCode);
    }

    public record ResolvedDispatchEntry(
            String sequenceId,
            TaskRequestValidator.NormalizedTaskRequest task,
            List<String> deviceIds
    ) {
    }

    private record NormalizedEntry(
            int index,
            String sequenceId,
            TaskRequestValidator.NormalizedTaskRequest task,
            NormalizedSelector selector
    ) {
    }

    private record NormalizedSelector(
            boolean named,
            int count,
            List<String> deviceIds,
            List<String> requiredTags,
            List<String> excludedTags
    ) {
    }
}
