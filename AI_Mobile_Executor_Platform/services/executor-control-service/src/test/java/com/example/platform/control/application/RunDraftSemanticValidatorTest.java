package com.example.platform.control.application;

import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import com.example.platform.control.domain.PersistenceModels.DevicePoolEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.infrastructure.mapper.DeviceMapper;
import com.example.platform.control.infrastructure.mapper.DevicePoolMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

class RunDraftSemanticValidatorTest {

    private DevicePoolMapper devicePoolMapper;
    private DeviceMapper deviceMapper;
    private DeviceRuntimeStateMapper runtimeStateMapper;
    private RunDraftSemanticValidator validator;

    @BeforeEach
    void setUp() {
        devicePoolMapper = Mockito.mock(DevicePoolMapper.class);
        deviceMapper = Mockito.mock(DeviceMapper.class);
        runtimeStateMapper = Mockito.mock(DeviceRuntimeStateMapper.class);
        validator = new RunDraftSemanticValidator(
                devicePoolMapper,
                deviceMapper,
                runtimeStateMapper,
                new TaskRequestValidator(),
                new JsonCodec(new ObjectMapper())
        );
    }

    @Test
    void rejectsDraftWhenPoolHasNoEligibleProfileDevices() {
        DevicePoolEntity pool = new DevicePoolEntity();
        pool.setPoolId("pool-1");
        pool.setHostGroup("default");
        pool.setDeviceIdsJson("[]");
        pool.setRequiredTagsJson("[]");
        pool.setExcludedTagsJson("[]");
        when(devicePoolMapper.findById("pool-1")).thenReturn(pool);

        DeviceEntity device = new DeviceEntity();
        device.setDeviceId("device-1");
        device.setHostGroup("default");
        device.setInstalledProfilesJson("[\"com.other.app\"]");
        device.setTagsJson("[]");
        when(deviceMapper.findAll()).thenReturn(List.of(device));

        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId("device-1");
        runtime.setRegistered(true);
        runtime.setOnline(true);
        runtime.setStatus("ONLINE");
        when(runtimeStateMapper.findAll()).thenReturn(List.of(runtime));

        Phase3AiModels.ValidationResult result = validator.validate(validDraft("com.zhiliaoapp.musically"));

        assertFalse(result.valid());
        assertTrue(result.errors().stream().anyMatch(message -> message.contains("selected pool")));
    }

    private Phase3AiModels.RunDraftResult validDraft(String profilePackage) {
        return new Phase3AiModels.RunDraftResult(
                new Phase3AiModels.RunDraft(
                        "tiktok smoke",
                        "phase3",
                        "pool-1",
                        "PLUGIN_RUN",
                        profilePackage,
                        Map.of("goal", "open home"),
                        Map.of(
                                "loopCount", 1,
                                "budgetMs", 60_000L,
                                "loopIntervalMs", 0L,
                                "networkIsolationEnabled", false,
                                "pollIntervalMs", 15_000L,
                                "heartbeatIntervalMs", 30_000L
                        ),
                        Map.of(
                                "uploadLog", true,
                                "uploadScreenshot", true,
                                "uploadDump", true
                        ),
                        100,
                        List.of("phase3"),
                        0,
                        300_000L
                ),
                List.of(),
                List.of()
        );
    }
}
