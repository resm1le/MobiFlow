package com.example.platform.control.api;

import com.example.platform.control.application.AdminApiService;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.mock;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class AdminAttemptControllerTest {

    @Test
    void summaryEndpointReturnsGoneTombstone() throws Exception {
        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new AdminAttemptController(mock(AdminApiService.class)))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/api/attempts/attempt-1/summary"))
                .andExpect(status().isGone())
                .andExpect(jsonPath("$.code").value("LEGACY_AI_ATTEMPT_SUMMARY_REMOVED"));
    }

    @Test
    void failureAnalysisEndpointReturnsGoneTombstone() throws Exception {
        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new AdminAttemptController(mock(AdminApiService.class)))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/api/attempts/attempt-1/failure-analysis"))
                .andExpect(status().isGone())
                .andExpect(jsonPath("$.code").value("LEGACY_AI_ATTEMPT_FAILURE_ANALYSIS_REMOVED"));
    }
}
