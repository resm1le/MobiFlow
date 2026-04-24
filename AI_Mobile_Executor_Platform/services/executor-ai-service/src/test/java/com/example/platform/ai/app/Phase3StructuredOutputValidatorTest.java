package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.RunPlanningContext;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class Phase3StructuredOutputValidatorTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private Phase3StructuredOutputValidator validator;

    @BeforeEach
    void setUp() {
        validator = new Phase3StructuredOutputValidator();
    }

    @Test
    void validatesCanonicalRunDraftResult() throws Exception {
        RunPlanningContext context = objectMapper.readValue("""
                {
                  "goal": "open tiktok",
                  "constraints": {},
                  "availableDevicePools": [
                    {
                      "poolId": "pool-1",
                      "name": "default",
                      "hostGroup": "default",
                      "deviceCount": 1,
                      "requiredTags": [],
                      "excludedTags": []
                    }
                  ],
                  "availableProfiles": [
                    {
                      "profilePackage": "com.zhiliaoapp.musically",
                      "installedDeviceCount": 1,
                      "supportedTaskTypes": ["PLUGIN_RUN"],
                      "requiredTaskPayloadFields": ["goal"],
                      "recommendedDefaults": {},
                      "knownLimitations": ["review"]
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
                      "uploadDump": true
                    }
                  },
                  "allowedTaskTypes": ["PLUGIN_RUN"]
                }
                """, RunPlanningContext.class);

        var result = validator.validateRunDraftResult(objectMapper.readTree("""
                {
                  "runDraft": {
                    "name": "TikTok smoke",
                    "description": "phase3",
                    "devicePoolId": "pool-1",
                    "taskType": "PLUGIN_RUN",
                    "profilePackage": "com.zhiliaoapp.musically",
                    "taskPayload": {"goal": "open home"},
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
                      "uploadDump": true
                    },
                    "priority": 100,
                    "labels": ["phase3"],
                    "maxRetriesPerDevice": 0,
                    "queueTimeoutMs": 300000
                  },
                  "warnings": [],
                  "reviewHints": []
                }
                """), context);

        assertEquals("pool-1", result.runDraft().devicePoolId());
        assertEquals("PLUGIN_RUN", result.runDraft().taskType());
    }

    @Test
    void rejectsUnknownFailureTriageEnums() throws Exception {
        assertThrows(AiServiceException.class, () -> validator.validateFailureTriageResult(objectMapper.readTree("""
                {
                  "failureCategory": "NOT_REAL",
                  "probableCause": "x",
                  "confidence": 0.7,
                  "retryRecommendation": "NO_RETRY",
                  "suggestedNextAction": "NONE",
                  "operatorReviewHints": ["hint"],
                  "evidence": ["artifact"]
                }
                """)));
    }
}
