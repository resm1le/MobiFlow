package com.example.platform.control.api;

import com.example.platform.control.application.AdminApiService;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;
import java.util.Map;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class AdminDeviceControllerTest {

    @Test
    void resumeEndpointReturnsLatestDeviceState() throws Exception {
        AdminApiService adminApiService = mock(AdminApiService.class);
        when(adminApiService.resumeDevice("device-1")).thenReturn(new AdminApiModels.DeviceResponse(
                "device-1",
                "v1",
                "1.0",
                "google",
                "Pixel 6",
                "13",
                1080,
                2400,
                List.of("com.google.android.apps.maps"),
                List.of("android-executor"),
                "default",
                true,
                true,
                false,
                "ONLINE",
                null,
                null,
                null,
                "cfg-v1",
                true,
                null,
                0L,
                "QUIESCE",
                Map.of("authConfigured", true),
                0L
        ));

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new AdminDeviceController(adminApiService)).build();

        mockMvc.perform(post("/api/devices/device-1/resume"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.deviceId").value("device-1"))
                .andExpect(jsonPath("$.status").value("ONLINE"));
    }
}
