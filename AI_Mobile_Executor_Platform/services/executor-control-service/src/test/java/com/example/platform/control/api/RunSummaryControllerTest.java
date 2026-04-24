package com.example.platform.control.api;

import com.example.platform.control.application.AiRunSummaryService;
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

class RunSummaryControllerTest {

    @Test
    void createRunSummaryReturnsStructuredPayload() throws Exception {
        AiRunSummaryService service = mock(AiRunSummaryService.class);
        when(service.createRunSummary("run-1")).thenReturn(response());

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new RunSummaryController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/api/runs/run-1/summary"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.summaryId").value("summary-1"))
                .andExpect(jsonPath("$.result.summaryText").value("Run completed successfully."))
                .andExpect(jsonPath("$.validation.valid").value(true));
    }

    @Test
    void latestRunSummaryReturnsStructuredPayload() throws Exception {
        AiRunSummaryService service = mock(AiRunSummaryService.class);
        when(service.getLatestRunSummary("run-1")).thenReturn(response());

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new RunSummaryController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(get("/api/runs/run-1/summary/latest"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.summaryId").value("summary-1"));
    }

    private AiRunSummaryApiModels.RunSummaryResponse response() {
        return new AiRunSummaryApiModels.RunSummaryResponse(
                "summary-1",
                "run-1",
                new Phase3AiModels.RunSummaryResult(
                        "Run completed successfully.",
                        List.of(new Phase3AiModels.RunSummaryKeyMoment("Launch", "STEP", 1, "app entered home")),
                        "Healthy run.",
                        List.of("targets:succeeded=1")
                ),
                new AiRunSummaryApiModels.ValidationResponse(true, List.of(), List.of()),
                Map.of("provider", "stub"),
                1770000000000L
        );
    }
}
