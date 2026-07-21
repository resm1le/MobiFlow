package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels.CreateHeterogeneousRunRequest;
import com.example.platform.control.api.AdminApiModels.DeviceSelector;
import com.example.platform.control.api.AdminApiModels.HeterogeneousDispatchEntry;
import com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy;
import com.example.platform.control.api.ExecutorApiModels.RunConfig;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.infrastructure.mapper.DeviceMapper;
import com.example.platform.control.infrastructure.mapper.DeviceRuntimeStateMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

import java.io.InputStream;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class HeterogeneousDispatchResolverTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private DeviceMapper deviceMapper;
    private DeviceRuntimeStateMapper runtimeStateMapper;
    private HeterogeneousDispatchResolver resolver;
    private Map<String, Object> taskPayload;

    @BeforeEach
    void setUp() throws Exception {
        deviceMapper = mock(DeviceMapper.class);
        runtimeStateMapper = mock(DeviceRuntimeStateMapper.class);
        resolver = new HeterogeneousDispatchResolver(
                deviceMapper,
                runtimeStateMapper,
                new TaskRequestValidator(),
                new JsonCodec(objectMapper)
        );
        try (InputStream stream = getClass().getResourceAsStream("/contracts/p2-2-resolved-sequence.json")) {
            taskPayload = objectMapper.readValue(stream, new TypeReference<>() { });
        }
    }

    @Test
    void namedSelectorsReserveBeforeEarlierTagSelectorsAndTagsUseDeviceIdOrder() {
        when(deviceMapper.findAll()).thenReturn(List.of(
                device("device-3", List.of("lab")),
                device("device-2", List.of("lab")),
                device("device-1", List.of("lab"))
        ));
        when(runtimeStateMapper.findAll()).thenReturn(List.of(
                runtime("device-1", false), runtime("device-2", false), runtime("device-3", false)
        ));

        var resolved = resolver.resolve(request(List.of(
                entry(new DeviceSelector(2, List.of(), List.of("lab"), List.of())),
                entry(new DeviceSelector(null, List.of("device-1"), List.of(), List.of()))
        )));

        assertEquals(List.of("device-2", "device-3"), resolved.get(0).deviceIds());
        assertEquals(List.of("device-1"), resolved.get(1).deviceIds());
    }

    @Test
    void filtersBusyDevicesAndRejectsInsufficientCapacityWithoutPartialResult() {
        when(deviceMapper.findAll()).thenReturn(List.of(device("device-1", List.of("lab"))));
        when(runtimeStateMapper.findAll()).thenReturn(List.of(runtime("device-1", true)));

        ResponseStatusException error = assertThrows(ResponseStatusException.class, () ->
                resolver.resolve(request(List.of(entry(new DeviceSelector(1, List.of(), List.of("lab"), List.of()))))));

        assertEquals(ControlErrorCode.DISPATCH_CAPACITY_INSUFFICIENT, error.getReason());
    }

    @Test
    void rejectsNamedDeviceConflictsAcrossEntries() {
        when(deviceMapper.findAll()).thenReturn(List.of(device("device-1", List.of("lab"))));
        when(runtimeStateMapper.findAll()).thenReturn(List.of(runtime("device-1", false)));
        DeviceSelector named = new DeviceSelector(null, List.of("device-1"), List.of(), List.of());

        ResponseStatusException error = assertThrows(ResponseStatusException.class, () ->
                resolver.resolve(request(List.of(entry(named), entry(named)))));

        assertEquals(ControlErrorCode.DISPATCH_DEVICE_CONFLICT, error.getReason());
    }

    @Test
    void rejectsDuplicateDeviceWithinNamedSelector() {
        DeviceSelector duplicate = new DeviceSelector(
                null, List.of("device-1", "device-1"), List.of(), List.of());

        ResponseStatusException error = assertThrows(ResponseStatusException.class, () ->
                resolver.resolve(request(List.of(entry(duplicate)))));

        assertEquals(ControlErrorCode.DISPATCH_DEVICE_CONFLICT, error.getReason());
    }

    @Test
    void rejectsSequenceIdentityMismatch() {
        Map<String, Object> invalid = objectMapper.convertValue(taskPayload, new TypeReference<>() { });
        @SuppressWarnings("unchecked")
        Map<String, Object> sequence = (Map<String, Object>) invalid.get("waypoint_sequence");
        sequence.put("sequence_id", "wrong.sequence.v1");
        var request = request(List.of(new HeterogeneousDispatchEntry(
                "wechat.text_chat.v1", "com.tencent.mm", invalid,
                new DeviceSelector(null, List.of("device-1"), List.of(), List.of())
        )));

        ResponseStatusException error = assertThrows(ResponseStatusException.class, () -> resolver.resolve(request));

        assertEquals(ControlErrorCode.HETEROGENEOUS_RUN_INVALID, error.getReason());
    }

    private CreateHeterogeneousRunRequest request(List<HeterogeneousDispatchEntry> dispatch) {
        return new CreateHeterogeneousRunRequest(
                "heterogeneous", null, "PLUGIN_RUN",
                new RunConfig(1, 60_000, 0, false, 15_000, 30_000),
                new ArtifactPolicy(true, true, true),
                100, List.of("pcap"), "agent", "agent", 1, 300_000L, dispatch
        );
    }

    private HeterogeneousDispatchEntry entry(DeviceSelector selector) {
        return new HeterogeneousDispatchEntry(
                "wechat.text_chat.v1", "com.tencent.mm", taskPayload, selector
        );
    }

    private DeviceEntity device(String deviceId, List<String> tags) {
        DeviceEntity device = new DeviceEntity();
        device.setDeviceId(deviceId);
        device.setTagsJson(write(tags));
        device.setInstalledProfilesJson(write(List.of("com.tencent.mm")));
        return device;
    }

    private DeviceRuntimeStateEntity runtime(String deviceId, boolean busy) {
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId(deviceId);
        runtime.setRegistered(true);
        runtime.setOnline(true);
        runtime.setBusy(busy);
        runtime.setStatus(DomainValues.DEVICE_STATUS_ONLINE);
        return runtime;
    }

    private String write(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
    }
}
