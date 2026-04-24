package com.example.platform.control.api;

import com.example.platform.control.application.ToolFacadeService;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ToolFacadeControllerTest {

    @Test
    void executeReturnsNewEnvelopeShape() throws Exception {
        ToolFacadeService service = mock(ToolFacadeService.class);
        when(service.execute(any())).thenReturn(new ToolApiModels.ExecuteToolResponse(
                "tool-envelope-v2",
                "req-1",
                "session-1",
                "list_devices",
                "completed",
                List.of(Map.of("deviceId", "device-1")),
                List.of(),
                null,
                new ToolApiModels.ToolAudit("audit-1", "DISCOVERY"),
                new ToolApiModels.EntityRefs(null, null, null, null, null, List.of()),
                null
        ));

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new ToolFacadeController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/tools/execute")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "requestId": "req-1",
                                  "sessionId": "session-1",
                                  "tool": "list_devices",
                                  "arguments": {},
                                  "callerContext": {
                                    "agentTaskId": "task-1",
                                    "turnId": "turn-1",
                                    "stepId": "step-1"
                                  }
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requestId").value("req-1"))
                .andExpect(jsonPath("$.tool").value("list_devices"))
                .andExpect(jsonPath("$.status").value("completed"))
                .andExpect(jsonPath("$.audit.auditId").value("audit-1"))
                .andExpect(jsonPath("$.confirmation").doesNotExist());
    }

    @Test
    void queryAuditsReturnsTimelineEntries() throws Exception {
        ToolFacadeService service = mock(ToolFacadeService.class);
        when(service.queryAudits(any())).thenReturn(new ToolApiModels.AuditQueryResponse(
                "tool-envelope-v2",
                List.of(new ToolApiModels.AuditTimelineEntry(
                        "audit-1",
                        "req-1",
                        "session-1",
                        "get_run_governance_snapshot",
                        "SUCCEEDED",
                        "DISCOVERY",
                        new ToolApiModels.CallerContext("task-1", "turn-1", "step-1"),
                        new ToolApiModels.EntityRefs(null, "run-1", null, null, null, List.of()),
                        1L,
                        2L
                ))
        ));

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new ToolFacadeController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/tools/audits/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sessionId": "session-1",
                                  "runId": "run-1"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value("tool-envelope-v2"))
                .andExpect(jsonPath("$.entries[0].tool").value("get_run_governance_snapshot"))
                .andExpect(jsonPath("$.entries[0].entityRefs.runId").value("run-1"));
    }
}
