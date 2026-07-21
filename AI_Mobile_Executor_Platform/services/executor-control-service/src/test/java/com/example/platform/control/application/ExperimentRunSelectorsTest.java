package com.example.platform.control.application;

import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertFalse;

class ExperimentRunSelectorsTest {

    @Test
    void busyDeviceNeverMatchesPool() {
        DeviceEntity device = new DeviceEntity();
        device.setDeviceId("device-1");
        device.setTagsJson("[]");
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId("device-1");
        runtime.setRegistered(true);
        runtime.setOnline(true);
        runtime.setBusy(true);
        runtime.setStatus(DomainValues.DEVICE_STATUS_ONLINE);

        assertFalse(ExperimentRunSelectors.matchesPool(
                device, runtime, null, Set.of(), Set.of(), Set.of(), new JsonCodec(new ObjectMapper())
        ));
    }
}
