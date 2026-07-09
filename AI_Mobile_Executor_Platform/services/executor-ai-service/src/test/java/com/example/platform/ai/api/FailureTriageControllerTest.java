package com.example.platform.ai.api;

import com.example.platform.ai.api.dto.ModelMetaDto;
import com.example.platform.ai.app.ActiveAiProvider;
import com.example.platform.ai.app.ProviderResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FailureTriageControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private ActiveAiProvider activeAiProvider;

    @Test
    void createFailureTriageReturnsStructuredResult() throws Exception {
        when(activeAiProvider.generateFailureTriage(any())).thenReturn(new ProviderResult(
                objectMapper.readTree("""
                        {
                          "failureCategory": "UI_NOT_FOUND",
                          "probableCause": "Target never appeared.",
                          "confidence": 0.8,
                          "retryRecommendation": "RETRY_SAME_DEVICE",
                          "suggestedNextAction": "INSPECT_ARTIFACTS",
                          "operatorReviewHints": ["check the latest screenshot"],
                          "evidence": ["lastError:ui target not found"]
                        }
                        """),
                List.of(),
                new ModelMetaDto("stub", "local-stub", 1770000000000L)
        ));

        mockMvc.perform(post("/internal/failure-triage")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(failureTriageContextBody()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result.failureCategory").value("UI_NOT_FOUND"))
                .andExpect(jsonPath("$.result.retryRecommendation").value("RETRY_SAME_DEVICE"))
                .andExpect(jsonPath("$.modelMeta.provider").value("stub"));
    }

    @Test
    void createFailureTriageRejectsInvalidProviderPayload() throws Exception {
        when(activeAiProvider.generateFailureTriage(any())).thenReturn(new ProviderResult(
                objectMapper.readTree("""
                        {
                          "failureCategory": "UI_NOT_FOUND",
                          "probableCause": "Target never appeared.",
                          "confidence": 2.0,
                          "retryRecommendation": "RETRY_SAME_DEVICE",
                          "suggestedNextAction": "INSPECT_ARTIFACTS",
                          "operatorReviewHints": ["check the latest screenshot"],
                          "evidence": ["lastError:ui target not found"]
                        }
                        """),
                List.of(),
                new ModelMetaDto("stub", "local-stub", 1770000000000L)
        ));

        mockMvc.perform(post("/internal/failure-triage")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(failureTriageContextBody()))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("PROVIDER_OUTPUT_INVALID"));
    }

    private String failureTriageContextBody() {
        return """
                {
                  "run": {
                    "runId": "run-1",
                    "poolId": "pool-1",
                    "status": "TERMINAL",
                    "finalState": "FAILED",
                    "taskType": "PLUGIN_RUN",
                    "profilePackage": "com.google.android.apps.maps",
                    "priority": 100,
                    "labels": ["phase3"],
                    "maxRetriesPerDevice": 0,
                    "queueTimeoutMs": 300000,
                    "cancelRequested": false,
                    "startedAt": 1,
                    "finishedAt": 2
                  },
                  "target": {
                    "runTargetId": "target-1",
                    "deviceId": "device-1",
                    "status": "FAILED",
                    "attemptCount": 1,
                    "currentTaskId": "task-1",
                    "latestAttemptId": "attempt-1",
                    "failureReason": "UI target not found",
                    "startedAt": 1,
                    "finishedAt": 2
                  },
                  "latestAttempt": {
                    "attemptId": "attempt-1",
                    "taskId": "task-1",
                    "deviceId": "device-1",
                    "runId": "run-1",
                    "status": "FAILED",
                    "finalState": "FAILED",
                    "failureReason": "UI target not found",
                    "preflightSummary": {},
                    "failureDetail": {
                      "lastError": "ui target not found"
                    },
                    "startedAt": 1,
                    "finishedAt": 2,
                    "createdAt": 1
                  },
                  "attemptHistorySummary": {
                    "attemptCount": 1,
                    "recentAttempts": [
                      {
                        "attemptId": "attempt-1",
                        "status": "FAILED",
                        "finalState": "FAILED",
                        "failureReason": "UI target not found",
                        "finishedAt": 2,
                        "deviceId": "device-1"
                      }
                    ],
                    "queueTimeoutObserved": false,
                    "cancelObserved": false
                  },
                  "failureContext": {
                    "finalState": "FAILED",
                    "failureReason": "UI target not found",
                    "lastError": "ui target not found",
                    "queueTimeout": false,
                    "cancelled": false,
                    "leaseLost": false,
                    "precheckFailed": false,
                    "preflightSummary": {},
                    "failureDetail": {
                      "lastError": "ui target not found"
                    }
                  },
                  "keyEvents": [
                    {
                      "eventType": "STEP",
                      "message": "search",
                      "ts": 1
                    }
                  ],
                  "artifactManifest": [
                    {
                      "artifactId": "artifact-1",
                      "artifactType": "run_log",
                      "fileName": "run.log",
                      "mimeType": "text/plain",
                      "sizeBytes": 12,
                      "objectKey": "artifact/run.log"
                    }
                  ],
                  "deviceOperationalSnapshot": {
                    "snapshotType": "FAILURE",
                    "capturedAt": 2,
                    "deviceId": "device-1",
                    "hostGroup": "default",
                    "profilePackages": ["com.google.android.apps.maps"],
                    "capabilities": {},
                    "healthSnapshot": {},
                    "preflightSummary": {},
                    "lastHeartbeatAt": 2
                  }
                }
                """;
    }
}
