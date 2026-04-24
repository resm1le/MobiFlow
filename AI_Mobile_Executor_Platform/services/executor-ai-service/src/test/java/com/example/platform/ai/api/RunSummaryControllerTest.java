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
class RunSummaryControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private ActiveAiProvider activeAiProvider;

    @Test
    void createRunSummaryReturnsStructuredSummary() throws Exception {
        when(activeAiProvider.generateRunSummary(any())).thenReturn(new ProviderResult(
                objectMapper.readTree("""
                        {
                          "summaryText": "Run run-1 completed successfully.",
                          "keyMoments": [
                            {
                              "title": "Launch complete",
                              "eventType": "action_end",
                              "stepIndex": 1,
                              "message": "Tap ok"
                            }
                          ],
                          "finalJudgement": "Healthy run.",
                          "evidence": ["targets:succeeded=1", "artifact:run_log:run.log"]
                        }
                        """),
                List.of(),
                new ModelMetaDto("stub", "local-stub", 1770000000000L)
        ));

        mockMvc.perform(post("/internal/run-summaries")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(runSummaryContextBody()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result.summaryText").value("Run run-1 completed successfully."))
                .andExpect(jsonPath("$.result.keyMoments[0].title").value("Launch complete"))
                .andExpect(jsonPath("$.result.finalJudgement").value("Healthy run."))
                .andExpect(jsonPath("$.modelMeta.provider").value("stub"));
    }

    @Test
    void createRunSummaryRejectsInvalidProviderPayload() throws Exception {
        when(activeAiProvider.generateRunSummary(any())).thenReturn(new ProviderResult(
                objectMapper.readTree("""
                        {
                          "summaryText": "",
                          "keyMoments": [],
                          "finalJudgement": "Healthy run.",
                          "evidence": []
                        }
                        """),
                List.of(),
                new ModelMetaDto("stub", "local-stub", 1770000000000L)
        ));

        mockMvc.perform(post("/internal/run-summaries")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(runSummaryContextBody()))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.error").value("PROVIDER_OUTPUT_INVALID"));
    }

    private String runSummaryContextBody() {
        return """
                {
                  "run": {
                    "runId": "run-1",
                    "poolId": "pool-1",
                    "status": "TERMINAL",
                    "finalState": "SUCCEEDED",
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
                  "counts": {
                    "totalTargets": 1,
                    "queued": 0,
                    "running": 0,
                    "retryPending": 0,
                    "succeeded": 1,
                    "failed": 0,
                    "cancelled": 0
                  },
                  "targets": [
                    {
                      "runTargetId": "target-1",
                      "deviceId": "device-1",
                      "status": "SUCCEEDED",
                      "attemptCount": 1,
                      "currentTaskId": "task-1",
                      "latestAttemptId": "attempt-1",
                      "failureReason": null,
                      "startedAt": 1,
                      "finishedAt": 2
                    }
                  ],
                  "representativeAttempts": [
                    {
                      "attemptId": "attempt-1",
                      "taskId": "task-1",
                      "deviceId": "device-1",
                      "runId": "run-1",
                      "status": "SUCCEEDED",
                      "finalState": "SUCCESS",
                      "failureReason": null,
                      "preflightSummary": {},
                      "failureDetail": {},
                      "startedAt": 1,
                      "finishedAt": 2,
                      "createdAt": 1
                    }
                  ],
                  "keyEvents": [
                    {
                      "eventType": "action_end",
                      "message": "Tap ok",
                      "stepIndex": 1,
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
                  ]
                }
                """;
    }
}
