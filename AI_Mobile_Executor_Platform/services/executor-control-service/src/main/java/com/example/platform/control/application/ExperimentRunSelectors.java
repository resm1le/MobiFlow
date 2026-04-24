package com.example.platform.control.application;

import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;

import java.util.Set;

final class ExperimentRunSelectors {

    private ExperimentRunSelectors() {
    }

    static boolean matchesPool(DeviceEntity device,
                               DeviceRuntimeStateEntity runtime,
                               String hostGroup,
                               Set<String> selectedIds,
                               Set<String> requiredTags,
                               Set<String> excludedTags,
                               JsonCodec jsonCodec) {
        if (runtime == null || !runtime.isRegistered() || !runtime.isOnline()
                || DomainValues.DEVICE_STATUS_QUIESCED.equals(runtime.getStatus())) {
            return false;
        }
        if (hostGroup != null && !hostGroup.isBlank() && !hostGroup.equals(device.getHostGroup())) {
            return false;
        }
        if (!selectedIds.isEmpty() && !selectedIds.contains(device.getDeviceId())) {
            return false;
        }
        Set<String> tags = Set.copyOf(jsonCodec.readStringList(device.getTagsJson()));
        if (!tags.containsAll(requiredTags)) {
            return false;
        }
        return excludedTags.stream().noneMatch(tags::contains);
    }
}
