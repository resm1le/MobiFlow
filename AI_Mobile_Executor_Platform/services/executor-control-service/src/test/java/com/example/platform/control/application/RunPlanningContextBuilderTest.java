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

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

class RunPlanningContextBuilderTest {

    private DevicePoolMapper devicePoolMapper;
    private DeviceMapper deviceMapper;
    private DeviceRuntimeStateMapper runtimeStateMapper;
    private RunPlanningContextBuilder builder;

    @BeforeEach
    void setUp() {
        devicePoolMapper = Mockito.mock(DevicePoolMapper.class);
        deviceMapper = Mockito.mock(DeviceMapper.class);
        runtimeStateMapper = Mockito.mock(DeviceRuntimeStateMapper.class);
        builder = new RunPlanningContextBuilder(
                devicePoolMapper,
                deviceMapper,
                runtimeStateMapper,
                new JsonCodec(new ObjectMapper()),
                new ControlProperties()
        );
    }

    @Test
    void buildsProfileContractsAndPoolCountsFromControlPlaneState() {
        DevicePoolEntity pool = new DevicePoolEntity();
        pool.setPoolId("pool-1");
        pool.setName("default");
        pool.setHostGroup("default");
        pool.setDeviceIdsJson("[]");
        pool.setRequiredTagsJson("[\"debug\"]");
        pool.setExcludedTagsJson("[]");
        when(devicePoolMapper.findAll()).thenReturn(List.of(pool));

        DeviceEntity device = new DeviceEntity();
        device.setDeviceId("device-1");
        device.setHostGroup("default");
        device.setInstalledProfilesJson("[\"com.zhiliaoapp.musically\"]");
        device.setTagsJson("[\"debug\"]");
        when(deviceMapper.findAll()).thenReturn(List.of(device));

        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId("device-1");
        runtime.setRegistered(true);
        runtime.setOnline(true);
        runtime.setStatus("ONLINE");
        when(runtimeStateMapper.findAll()).thenReturn(List.of(runtime));

        Phase3AiModels.RunPlanningContext context = builder.build("open tiktok", Map.of("locale", "zh-CN"));

        assertEquals("open tiktok", context.goal());
        assertEquals(1, context.availableDevicePools().size());
        assertEquals(1, context.availableDevicePools().get(0).deviceCount());
        assertEquals(1, context.availableProfiles().size());
        assertEquals("com.zhiliaoapp.musically", context.availableProfiles().get(0).profilePackage());
        assertEquals(List.of("goal"), context.availableProfiles().get(0).requiredTaskPayloadFields());
        assertTrue(context.allowedTaskTypes().contains("PLUGIN_RUN"));
        assertFalse(context.defaultRunPolicy().defaultRunConfig().isEmpty());
        assertFalse(context.defaultRunPolicy().defaultArtifactPolicy().isEmpty());
    }
}
