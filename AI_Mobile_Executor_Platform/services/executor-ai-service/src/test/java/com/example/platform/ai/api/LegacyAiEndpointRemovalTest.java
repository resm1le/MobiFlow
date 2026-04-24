package com.example.platform.ai.api;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LegacyAiEndpointRemovalTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void legacyTaskPlanningEndpointNoLongerExists() throws Exception {
        mockMvc.perform(post("/internal/plans")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isNotFound());
    }

    @Test
    void legacyAttemptSummaryEndpointNoLongerExists() throws Exception {
        mockMvc.perform(post("/internal/summaries/runs")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isNotFound());
    }

    @Test
    void legacyAttemptFailureAnalysisEndpointNoLongerExists() throws Exception {
        mockMvc.perform(post("/internal/analyses/failures")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isNotFound());
    }
}
