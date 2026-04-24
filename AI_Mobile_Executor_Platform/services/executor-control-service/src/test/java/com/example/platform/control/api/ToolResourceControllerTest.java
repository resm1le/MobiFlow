package com.example.platform.control.api;

import com.example.platform.control.application.ToolResourceService;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.io.ByteArrayInputStream;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ToolResourceControllerTest {

    @Test
    void readReturnsStructuredContent() throws Exception {
        ToolResourceService service = mock(ToolResourceService.class);
        when(service.read("rh_1")).thenReturn(new ToolApiModels.ReadResourceResponse(
                "rh_1",
                "attempt_artifact",
                "application/json",
                "result.json",
                java.util.Map.of("ok", true)
        ));

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new ToolResourceController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/tools/resources/read")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"handle\":\"rh_1\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.handle").value("rh_1"))
                .andExpect(jsonPath("$.content.ok").value(true));
    }

    @Test
    void downloadStreamsResourceBody() throws Exception {
        ToolResourceService service = mock(ToolResourceService.class);
        when(service.download("rh_2")).thenReturn(new ToolResourceService.ToolResourceDownload(
                "screen.png",
                "image/png",
                new ByteArrayInputStream(new byte[]{1, 2, 3})
        ));

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new ToolResourceController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(get("/tools/resources/rh_2/download"))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Type", "image/png"))
                .andExpect(content().bytes(new byte[]{1, 2, 3}));
    }
}
