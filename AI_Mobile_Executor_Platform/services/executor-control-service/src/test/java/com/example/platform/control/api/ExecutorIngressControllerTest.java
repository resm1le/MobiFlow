package com.example.platform.control.api;

import com.example.platform.control.application.ArtifactUploadService;
import com.example.platform.control.application.ControlPlaneService;
import com.example.platform.control.api.ExecutorApiModels.ExecutorWaypointSegment;
import com.example.platform.control.api.ExecutorApiModels.ExecutorWaypointSegmentsRequest;
import com.example.platform.control.api.ExecutorApiModels.ExecutorWaypointSegmentsResponse;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.Collections;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ExecutorIngressControllerTest {

    private final ObjectMapper objectMapper = new ObjectMapper()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    private final Validator validator = Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void waypointSegmentContractPreservesNullableTimings() throws Exception {
        ExecutorWaypointSegmentsRequest request = objectMapper.readValue("""
                {
                  "waypointSegments": [
                    {
                      "step_id": "logged_in",
                      "behavior_label": "wechat_text_chat",
                      "entered_at_ms": 1000,
                      "arrived_at_ms": null,
                      "dwell_ms": null
                    }
                  ]
                }
                """, ExecutorWaypointSegmentsRequest.class);

        assertEquals(1, request.waypointSegments().size());
        assertEquals("logged_in", request.waypointSegments().get(0).stepId());
        assertEquals(1000L, request.waypointSegments().get(0).enteredAtMs());
        assertEquals(null, request.waypointSegments().get(0).arrivedAtMs());
    }

    @Test
    void waypointSegmentContractRejectsCallerSuppliedIdentity() {
        assertThrows(Exception.class, () -> objectMapper.readValue("""
                {
                  "waypointSegments": [
                    {
                      "step_id": "logged_in",
                      "behavior_label": "wechat_text_chat",
                      "entered_at_ms": 1000,
                      "arrived_at_ms": 1500,
                      "dwell_ms": 500,
                      "deviceId": "forged-device"
                    }
                  ]
                }
                """, ExecutorWaypointSegmentsRequest.class));
    }

    @Test
    void waypointRequestContractRejectsUnknownTopLevelFields() {
        assertThrows(Exception.class, () -> objectMapper.readValue("""
                {
                  "waypointSegments": [{"step_id":"logged_in","behavior_label":"wechat_text_chat"}],
                  "runTargetId": "forged-target"
                }
                """, ExecutorWaypointSegmentsRequest.class));
    }

    @Test
    void waypointRequestValidationRejectsEmptyOversizedAndBlankSegments() {
        ExecutorWaypointSegment valid = new ExecutorWaypointSegment(
                "logged_in", "wechat_text_chat", null, null, null);

        assertFalse(validator.validate(new ExecutorWaypointSegmentsRequest(List.of())).isEmpty());
        assertFalse(validator.validate(new ExecutorWaypointSegmentsRequest(
                Collections.nCopies(257, valid))).isEmpty());
        assertFalse(validator.validate(new ExecutorWaypointSegmentsRequest(List.of(
                new ExecutorWaypointSegment("", "wechat_text_chat", null, null, null)
        ))).isEmpty());
    }

    @Test
    void waypointEndpointDelegatesWithAuthenticatedIdentity() throws Exception {
        ControlPlaneService controlPlaneService = mock(ControlPlaneService.class);
        ExecutorAuthContext authContext = new ExecutorAuthContext(
                "device-1", "v1", 1000L, "nonce-1", true);
        when(controlPlaneService.recordWaypointSegments(eq(authContext), eq("attempt-1"), any()))
                .thenReturn(new ExecutorWaypointSegmentsResponse("target-1", "attempt-1", 1));
        MockMvc mockMvc = MockMvcBuilders
                .standaloneSetup(new ExecutorIngressController(
                        controlPlaneService, mock(ArtifactUploadService.class)))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/executor/tasks/attempt-1/waypoint-segments")
                        .requestAttr(ExecutorAuthContext.REQUEST_ATTRIBUTE, authContext)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"waypointSegments":[{
                                  "step_id":"logged_in",
                                  "behavior_label":"wechat_text_chat",
                                  "entered_at_ms":1000,
                                  "arrived_at_ms":1500,
                                  "dwell_ms":500
                                }]}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.runTargetId").value("target-1"))
                .andExpect(jsonPath("$.attemptId").value("attempt-1"))
                .andExpect(jsonPath("$.recordedCount").value(1));

        verify(controlPlaneService).recordWaypointSegments(eq(authContext), eq("attempt-1"), any());
    }

    @Test
    void removedArtifactUploadEndpointReturnsGoneTombstone() throws Exception {
        MockMvc mockMvc = MockMvcBuilders
                .standaloneSetup(new ExecutorIngressController(mock(ControlPlaneService.class), mock(ArtifactUploadService.class)))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/executor/tasks/attempt-1/artifacts")
                        .param("artifactType", "run_log")
                        .param("fileName", "run.log")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("legacy"))
                .andExpect(status().isGone())
                .andExpect(jsonPath("$.code").value("ARTIFACT_UPLOAD_V1_REMOVED"))
                .andExpect(jsonPath("$.message").value("ARTIFACT_UPLOAD_V1_REMOVED"));
    }
}
