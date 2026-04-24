package com.example.platform.control.api;

import com.example.platform.control.application.AiFailureTriageService;
import com.example.platform.control.application.Phase3AiModels;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;
import java.util.Map;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class RunTargetFailureTriageControllerTest {

    @Test
    void createEndpointReturnsStructuredTriage() throws Exception {
        AiFailureTriageService service = mock(AiFailureTriageService.class);
        when(service.createFailureTriage("target-1")).thenReturn(response("triage-1", "target-1"));

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new RunTargetFailureTriageController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/api/run-targets/target-1/failure-triage"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.triageResultId").value("triage-1"))
                .andExpect(jsonPath("$.result.failureCategory").value("UI_NOT_FOUND"));
    }

    @Test
    void latestEndpointReturnsStoredTriage() throws Exception {
        AiFailureTriageService service = mock(AiFailureTriageService.class);
        when(service.getLatestFailureTriage("target-1")).thenReturn(response("triage-2", "target-1"));

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new RunTargetFailureTriageController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(get("/api/run-targets/target-1/failure-triage/latest"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.triageResultId").value("triage-2"))
                .andExpect(jsonPath("$.validation.valid").value(true));
    }

    private AiFailureTriageApiModels.FailureTriageResponse response(String triageResultId, String runTargetId) {
        return new AiFailureTriageApiModels.FailureTriageResponse(
                triageResultId,
                runTargetId,
                new Phase3AiModels.FailureTriageResult(
                        Phase3AiModels.FailureCategory.UI_NOT_FOUND,
                        "Target never appeared.",
                        0.8d,
                        Phase3AiModels.RetryRecommendation.RETRY_SAME_DEVICE,
                        Phase3AiModels.SuggestedNextAction.INSPECT_ARTIFACTS,
                        List.of("check the latest screenshot"),
                        List.of("lastError:ui target not found")
                ),
                new AiFailureTriageApiModels.ValidationResponse(true, List.of(), List.of()),
                Map.of("provider", "stub"),
                1770000000000L
        );
    }
}
