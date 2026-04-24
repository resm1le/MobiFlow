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
class RunPlanControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private ActiveAiProvider activeAiProvider;

    @Test
    void createRunPlanReturnsStructuredRunDraft() throws Exception {
        when(activeAiProvider.generateRunPlan(any())).thenReturn(new ProviderResult(
                objectMapper.readTree("""
                        {
                          "runDraft": {
                            "name": "AI run for navigate to ikea",
                            "description": "navigate to ikea",
                            "devicePoolId": "pool-1",
                            "taskType": "PLUGIN_RUN",
                            "profilePackage": "com.google.android.apps.maps",
                            "taskPayload": {
                              "goal": "navigate to ikea"
                            },
                            "runConfig": {
                              "loopCount": 1,
                              "budgetMs": 60000,
                              "loopIntervalMs": 0,
                              "networkIsolationEnabled": false,
                              "pollIntervalMs": 15000,
                              "heartbeatIntervalMs": 30000
                            },
                            "artifactPolicy": {
                              "uploadLog": true,
                              "uploadScreenshot": true,
                              "uploadDump": false
                            },
                            "priority": 100,
                            "labels": ["ai", "run-draft"],
                            "maxRetriesPerDevice": 0,
                            "queueTimeoutMs": 300000
                          },
                          "warnings": ["stub warning"],
                          "reviewHints": ["review target pool"]
                        }
                        """),
                List.of("provider warning"),
                new ModelMetaDto("stub", "local-stub", 1770000000000L)
        ));

        mockMvc.perform(post("/internal/run-plans")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(runPlanningContextBody()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.runDraft.devicePoolId").value("pool-1"))
                .andExpect(jsonPath("$.runDraft.profilePackage").value("com.google.android.apps.maps"))
                .andExpect(jsonPath("$.warnings[0]").value("stub warning"))
                .andExpect(jsonPath("$.warnings[1]").value("provider warning"))
                .andExpect(jsonPath("$.reviewHints[0]").value("review target pool"))
                .andExpect(jsonPath("$.modelMeta.provider").value("stub"));
    }

    @Test
    void createRunPlanRejectsInvalidProviderPayload() throws Exception {
        when(activeAiProvider.generateRunPlan(any())).thenReturn(new ProviderResult(
                objectMapper.readTree("""
                        {
                          "runDraft": {
                            "name": "AI run",
                            "description": "navigate to ikea",
                            "devicePoolId": "pool-1",
                            "taskType": "PLUGIN_RUN",
                            "profilePackage": "com.google.android.apps.maps",
                            "taskPayload": {
                              "goal": "navigate to ikea"
                            },
                            "runConfig": {
                              "loopCount": 1,
                              "budgetMs": 60000,
                              "loopIntervalMs": 0,
                              "networkIsolationEnabled": false,
                              "pollIntervalMs": 15000,
                              "heartbeatIntervalMs": 30000
                            },
                            "artifactPolicy": {
                              "uploadLog": true,
                              "uploadScreenshot": true,
                              "uploadDump": false
                            },
                            "priority": 100,
                            "labels": ["ai"],
                            "maxRetriesPerDevice": 0,
                            "queueTimeoutMs": 300000,
                            "source": "forbidden"
                          },
                          "warnings": [],
                          "reviewHints": []
                        }
                        """),
                List.of(),
                new ModelMetaDto("stub", "local-stub", 1770000000000L)
        ));

        mockMvc.perform(post("/internal/run-plans")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(runPlanningContextBody()))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.error").value("PROVIDER_OUTPUT_INVALID"));
    }

    private String runPlanningContextBody() {
        return """
                {
                  "goal": "navigate to ikea",
                  "constraints": {},
                  "availableDevicePools": [
                    {
                      "poolId": "pool-1",
                      "name": "Pool 1",
                      "hostGroup": "default",
                      "deviceCount": 1,
                      "requiredTags": [],
                      "excludedTags": []
                    }
                  ],
                  "availableProfiles": [
                    {
                      "profilePackage": "com.google.android.apps.maps",
                      "installedDeviceCount": 1,
                      "supportedTaskTypes": ["PLUGIN_RUN", "PLUGIN_SMOKE"],
                      "requiredTaskPayloadFields": ["goal"],
                      "recommendedDefaults": {
                        "runConfig": {
                          "loopCount": 1,
                          "budgetMs": 60000,
                          "loopIntervalMs": 0,
                          "networkIsolationEnabled": false,
                          "pollIntervalMs": 15000,
                          "heartbeatIntervalMs": 30000
                        },
                        "artifactPolicy": {
                          "uploadLog": true,
                          "uploadScreenshot": true,
                          "uploadDump": false
                        }
                      },
                      "knownLimitations": []
                    }
                  ],
                  "defaultRunPolicy": {
                    "priority": 100,
                    "maxRetriesPerDevice": 0,
                    "queueTimeoutMs": 300000,
                    "defaultRunConfig": {
                      "loopCount": 1,
                      "budgetMs": 60000,
                      "loopIntervalMs": 0,
                      "networkIsolationEnabled": false,
                      "pollIntervalMs": 15000,
                      "heartbeatIntervalMs": 30000
                    },
                    "defaultArtifactPolicy": {
                      "uploadLog": true,
                      "uploadScreenshot": true,
                      "uploadDump": false
                    }
                  },
                  "allowedTaskTypes": ["PLUGIN_RUN", "PLUGIN_SMOKE"]
                }
                """;
    }
}
