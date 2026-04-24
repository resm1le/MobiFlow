package com.example.platform.control.api;

import com.example.platform.control.application.ArtifactUploadService;
import com.example.platform.control.application.ControlPlaneService;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.mock;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ExecutorIngressControllerTest {

    @Test
    void removedArtifactUploadEndpointReturnsGoneTombstone() throws Exception {
        MockMvc mockMvc = MockMvcBuilders
                .standaloneSetup(new ExecutorIngressController(mock(ControlPlaneService.class), mock(ArtifactUploadService.class)))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/executor/tasks/attempt-1/artifacts")
                        .param("artifactType", "run_log")
                        .param("fileName", "run.log")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("legacy"))
                .andExpect(status().isGone())
                .andExpect(jsonPath("$.code").value("ARTIFACT_UPLOAD_V1_REMOVED"))
                .andExpect(jsonPath("$.message").value("ARTIFACT_UPLOAD_V1_REMOVED"));
    }
}
