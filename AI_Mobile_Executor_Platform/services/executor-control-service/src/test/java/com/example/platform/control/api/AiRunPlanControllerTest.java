package com.example.platform.control.api;

import com.example.platform.control.api.AdminApiModels.ExperimentRunDetailResponse;
import com.example.platform.control.api.AdminApiModels.ExperimentRunSummaryResponse;
import com.example.platform.control.api.AdminApiModels.RunStatusCounts;
import com.example.platform.control.application.AiRunPlanningService;
import com.example.platform.control.application.Phase3AiModels;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class AiRunPlanControllerTest {

    @Test
    void createRunPlanEndpointReturnsStructuredDraft() throws Exception {
        AiRunPlanningService service = mock(AiRunPlanningService.class);
        when(service.createRunPlan(eq(new AiRunPlanApiModels.CreateRunPlanRequest("navigate to ikea", Map.of("locale", "zh-CN")))))
                .thenReturn(new AiRunPlanApiModels.CreateRunPlanResponse(
                        "run-plan-1",
                        new Phase3AiModels.RunDraft(
                                "AI run for navigate to ikea",
                                "navigate to ikea",
                                "pool-1",
                                "PLUGIN_RUN",
                                "com.google.android.apps.maps",
                                Map.of("goal", "navigate to ikea"),
                                Map.of(
                                        "loopCount", 1,
                                        "budgetMs", 60000,
                                        "loopIntervalMs", 0,
                                        "networkIsolationEnabled", false,
                                        "pollIntervalMs", 15000,
                                        "heartbeatIntervalMs", 30000
                                ),
                                Map.of(
                                        "uploadLog", true,
                                        "uploadScreenshot", true,
                                        "uploadDump", false
                                ),
                                100,
                                List.of("ai", "run-draft"),
                                0,
                                300000
                        ),
                        List.of("soft warning"),
                        List.of("review pool"),
                        new AiRunPlanApiModels.PlanValidationResponse(true, List.of(), List.of("validation warning")),
                        Map.of("provider", "stub")
                ));

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new AiRunPlanController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/api/ai/run-plans")
                        .contentType("application/json")
                        .content("""
                                {
                                  "goal": "navigate to ikea",
                                  "constraints": {
                                    "locale": "zh-CN"
                                  }
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requestId").value("run-plan-1"))
                .andExpect(jsonPath("$.runDraft.devicePoolId").value("pool-1"))
                .andExpect(jsonPath("$.validation.materializable").value(true))
                .andExpect(jsonPath("$.validation.warnings[0]").value("validation warning"));
    }

    @Test
    void materializeEndpointReturnsRunDetail() throws Exception {
        AiRunPlanningService service = mock(AiRunPlanningService.class);
        when(service.materializeRunPlan("run-plan-1", "operator"))
                .thenReturn(new ExperimentRunDetailResponse(
                        new ExperimentRunSummaryResponse(
                                "run-1",
                                "AI run",
                                "navigate to ikea",
                                "pool-1",
                                "QUEUED",
                                null,
                                "PLUGIN_RUN",
                                "com.google.android.apps.maps",
                                100,
                                List.of("ai", "run-draft"),
                                "ai-run-planning",
                                "operator",
                                0,
                                300000,
                                false,
                                1L,
                                1L,
                                null,
                                null,
                                new RunStatusCounts(1, 1, 0, 0, 0, 0, 0)
                        ),
                        Map.of("goal", "navigate to ikea"),
                        new ExecutorApiModels.RunConfig(1, 60000, 0, false, 15000, 30000),
                        new ExecutorApiModels.ArtifactPolicy(true, true, false),
                        List.of()
                ));

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new AiRunPlanController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/api/ai/run-plans/run-plan-1/materialize")
                        .contentType("application/json")
                        .content("""
                                {
                                  "createdBy": "operator"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.runId").value("run-1"))
                .andExpect(jsonPath("$.run.source").value("ai-run-planning"));
    }
}
