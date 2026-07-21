package com.example.platform.control.application;

import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.ExperimentRunTargetEntity;
import com.example.platform.control.domain.PersistenceModels.RunEventEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import com.example.platform.control.infrastructure.mapper.ExperimentRunTargetMapper;
import com.example.platform.control.infrastructure.mapper.RunEventMapper;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import com.example.platform.control.infrastructure.mapper.TaskMapper;
import com.example.platform.control.application.WaypointTimelineService.WaypointSegmentInput;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.io.InputStream;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class WaypointTimelineServiceTest {

    private static final String RUN_TARGET_ID = "target-1";
    private static final String ATTEMPT_ID = "attempt-1";
    private static final String TASK_ID = "task-1";
    private static final String RUN_ID = "run-1";
    private static final String DEVICE_ID = "device-trusted";
    private static final String SEQUENCE_ID = "wechat.text_chat.v1";
    private static final String BEHAVIOR_LABEL = "wechat_text_chat";

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final JsonCodec jsonCodec = new JsonCodec(objectMapper);
    private final List<RunEventEntity> storedEvents = new ArrayList<>();
    private TaskAttemptMapper attemptMapper;
    private TaskMapper taskMapper;
    private ExperimentRunTargetMapper targetMapper;
    private RunEventMapper runEventMapper;
    private WaypointTimelineService service;
    private TaskAttemptEntity attempt;
    private TaskEntity task;
    private ExperimentRunTargetEntity target;

    @BeforeEach
    void setUp() {
        attemptMapper = mock(TaskAttemptMapper.class);
        taskMapper = mock(TaskMapper.class);
        targetMapper = mock(ExperimentRunTargetMapper.class);
        runEventMapper = mock(RunEventMapper.class);
        service = new WaypointTimelineService(
                attemptMapper,
                taskMapper,
                targetMapper,
                runEventMapper,
                jsonCodec,
                Clock.fixed(Instant.ofEpochMilli(9_000L), ZoneOffset.UTC)
        );

        attempt = attempt(DomainValues.ATTEMPT_STATUS_SUCCEEDED);
        task = task(List.of("logged_in", "message_sent"));
        target = target();
        when(attemptMapper.lockById(ATTEMPT_ID)).thenReturn(attempt);
        when(taskMapper.findById(TASK_ID)).thenReturn(task);
        when(targetMapper.findById(RUN_TARGET_ID)).thenReturn(target);
        when(runEventMapper.findByAttemptIdAndEventKeys(eq(ATTEMPT_ID), anyList())).thenAnswer(invocation -> {
            List<String> keys = invocation.getArgument(1);
            return storedEvents.stream().filter(event -> keys.contains(event.getEventKey())).toList();
        });
        doAnswer(invocation -> {
            storedEvents.addAll(invocation.getArgument(0));
            return null;
        }).when(runEventMapper).insertBatchNoMutation(anyList());
    }

    @Test
    void fixtureMapsTrustedLineageAndCompleteEvents() throws IOException {
        List<WaypointSegmentInput> segments = fixtureSegments();

        List<RunEventEntity> events = service.record(RUN_TARGET_ID, ATTEMPT_ID, segments);

        assertEquals(2, events.size());
        RunEventEntity first = events.get(0);
        assertEquals(ATTEMPT_ID, first.getAttemptId());
        assertEquals(TASK_ID, first.getTaskId());
        assertEquals(DEVICE_ID, first.getDeviceId());
        assertEquals(RUN_ID, first.getRunId());
        assertEquals(SEQUENCE_ID, first.getScenarioId());
        assertEquals(0, first.getStepIndex());
        assertNull(first.getActionIndex());
        assertEquals("WAYPOINT_SEGMENT", first.getEventType());
        assertEquals("waypoint:0", first.getEventKey());
        assertEquals("COMPLETE", first.getState());
        assertNull(first.getCode());
        assertEquals("waypoint_segment:0:COMPLETE", first.getMessage());
        assertEquals(1_500L, first.getTs());
        Map<String, Object> payload = jsonCodec.readMap(first.getPayloadJson());
        assertEquals(SEQUENCE_ID, payload.get("sequence_id"));
        assertEquals("logged_in", payload.get("step_id"));
        assertEquals(BEHAVIOR_LABEL, payload.get("behavior_label"));
        assertEquals(DEVICE_ID, payload.get("deviceId"));
        assertNotNull(first.getMessage());
    }

    @Test
    void mapsInterruptedAndIncompleteWithoutClaimingCompleteWindows() {
        task.setTaskPayloadJson(taskPayload(List.of("entered", "not_run")));
        List<WaypointSegmentInput> segments = List.of(
                segment("entered", 2_000L, null, null),
                segment("not_run", null, null, null)
        );

        List<RunEventEntity> events = service.record(RUN_TARGET_ID, ATTEMPT_ID, segments);

        assertEquals(List.of("INTERRUPTED", "INCOMPLETE"), events.stream().map(RunEventEntity::getState).toList());
        assertEquals(List.of(2_000L, 9_000L), events.stream().map(RunEventEntity::getTs).toList());
        assertEquals("waypoint_segment:0:INTERRUPTED", events.get(0).getMessage());
        assertEquals("waypoint_segment:1:INCOMPLETE", events.get(1).getMessage());
    }

    @Test
    void rejectsAllInvalidPartialAndNegativeTimingCombinations() {
        List<WaypointSegmentInput> invalidSegments = List.of(
                segment("logged_in", null, 1_500L, null),
                segment("logged_in", null, null, 500L),
                segment("logged_in", 1_000L, null, 500L),
                segment("logged_in", 1_500L, 1_000L, -500L),
                segment("logged_in", 1_000L, 1_500L, 499L),
                segment("logged_in", -1L, null, null)
        );

        for (WaypointSegmentInput invalidSegment : invalidSegments) {
            assertInvalid(() -> service.record(
                    RUN_TARGET_ID,
                    ATTEMPT_ID,
                    List.of(invalidSegment, segment("message_sent", null, null, null))
            ));
        }
        verify(runEventMapper, never()).insertBatchNoMutation(anyList());
    }

    @Test
    void rejectsActiveAttemptBeforeReadingUntrustedLineage() {
        attempt.setStatus(DomainValues.ATTEMPT_STATUS_RUNNING);

        assertInvalid(() -> service.record(RUN_TARGET_ID, ATTEMPT_ID, fixtureSegmentsUnchecked()));

        verify(taskMapper, never()).findById(TASK_ID);
        verify(runEventMapper, never()).insertBatchNoMutation(anyList());
    }

    @Test
    void rejectsAttemptTaskTargetMismatch() {
        attempt.setDeviceId("forged-device");

        assertInvalid(() -> service.record(RUN_TARGET_ID, ATTEMPT_ID, fixtureSegmentsUnchecked()));

        verify(runEventMapper, never()).insertBatchNoMutation(anyList());
    }

    @Test
    void rejectsWrongOrderLabelAndCallerSuppliedIdentity() {
        assertInvalid(() -> service.record(RUN_TARGET_ID, ATTEMPT_ID, List.of(
                segment("message_sent", 1_000L, 1_500L, 500L),
                segment("logged_in", 1_600L, 2_200L, 600L)
        )));
        assertInvalid(() -> service.record(RUN_TARGET_ID, ATTEMPT_ID, List.of(
                segment("unknown", 1_000L, 1_500L, 500L),
                segment("message_sent", 1_600L, 2_200L, 600L)
        )));
        assertInvalid(() -> service.record(RUN_TARGET_ID, ATTEMPT_ID, List.of(
                segment("logged_in", 1_000L, 1_500L, 500L),
                segment("logged_in", 1_600L, 2_200L, 600L)
        )));
        assertInvalid(() -> service.record(RUN_TARGET_ID, ATTEMPT_ID, List.of(
                new WaypointSegmentInput("logged_in", "wrong", 1_000L, 1_500L, 500L),
                segment("message_sent", 1_600L, 2_200L, 600L)
        )));
        assertInvalid(() -> service.record(RUN_TARGET_ID, ATTEMPT_ID, List.of(
                new WaypointSegmentInput("logged_in", BEHAVIOR_LABEL, 1_000L, 1_500L, 500L, "forged", null),
                segment("message_sent", 1_600L, 2_200L, 600L)
        )));
        assertInvalid(() -> service.record(RUN_TARGET_ID, ATTEMPT_ID, List.of(
                new WaypointSegmentInput("logged_in", BEHAVIOR_LABEL, 1_000L, 1_500L, 500L, null, "forged"),
                segment("message_sent", 1_600L, 2_200L, 600L)
        )));
    }

    @Test
    void rejectsMoreThan256Segments() {
        List<WaypointSegmentInput> segments = new ArrayList<>();
        for (int index = 0; index < 257; index++) {
            segments.add(segment("step-" + index, null, null, null));
        }

        assertInvalid(() -> service.record(RUN_TARGET_ID, ATTEMPT_ID, segments));

        verify(attemptMapper, never()).lockById(ATTEMPT_ID);
    }

    @Test
    void rejectsTargetSequenceThatDoesNotMatchTaskPayload() {
        target.setSequenceId("different-sequence");

        assertInvalid(() -> service.record(RUN_TARGET_ID, ATTEMPT_ID, fixtureSegmentsUnchecked()));

        verify(runEventMapper, never()).insertBatchNoMutation(anyList());
    }

    @Test
    void exactReplayIsNoOpAndReturnsOriginallyPersistedIncompleteTimestamp() {
        task.setTaskPayloadJson(taskPayload(List.of("logged_in", "message_sent")));
        List<WaypointSegmentInput> segments = List.of(
                segment("logged_in", 1_000L, 1_500L, 500L),
                segment("message_sent", null, null, null)
        );
        List<RunEventEntity> first = service.record(RUN_TARGET_ID, ATTEMPT_ID, segments);

        List<RunEventEntity> replay = service.record(RUN_TARGET_ID, ATTEMPT_ID, segments);

        assertEquals(2, replay.size());
        assertEquals(first.get(1).getTs(), replay.get(1).getTs());
        verify(runEventMapper).insertBatchNoMutation(anyList());
    }

    @Test
    void conflictingExistingEventIsRejectedWithoutMutation() {
        List<RunEventEntity> initial = service.record(RUN_TARGET_ID, ATTEMPT_ID, fixtureSegmentsUnchecked());
        initial.get(0).setPayloadJson(initial.get(0).getPayloadJson().replace(DEVICE_ID, "different-device"));

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> service.record(RUN_TARGET_ID, ATTEMPT_ID, fixtureSegmentsUnchecked())
        );

        assertEquals(HttpStatus.CONFLICT, exception.getStatusCode());
        assertEquals(ControlErrorCode.WAYPOINT_SEGMENT_CONFLICT, exception.getReason());
    }

    @Test
    void postReadDetectsConcurrentConflictingNoMutationUpsert() {
        doAnswer(invocation -> {
            List<RunEventEntity> events = invocation.getArgument(0);
            storedEvents.addAll(events.stream().map(this::copyEvent).toList());
            storedEvents.get(0).setMessage("conflicting-writer");
            return null;
        }).when(runEventMapper).insertBatchNoMutation(anyList());

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> service.record(RUN_TARGET_ID, ATTEMPT_ID, fixtureSegmentsUnchecked())
        );

        assertEquals(HttpStatus.CONFLICT, exception.getStatusCode());
        assertEquals(ControlErrorCode.WAYPOINT_SEGMENT_CONFLICT, exception.getReason());
    }

    private List<WaypointSegmentInput> fixtureSegments() throws IOException {
        try (InputStream input = getClass().getResourceAsStream("/contracts/p2-1d-waypoint-segments.json")) {
            assertNotNull(input);
            return objectMapper.readValue(input, new TypeReference<>() {
            });
        }
    }

    private List<WaypointSegmentInput> fixtureSegmentsUnchecked() {
        try {
            return fixtureSegments();
        } catch (IOException exception) {
            throw new AssertionError(exception);
        }
    }

    private TaskAttemptEntity attempt(String status) {
        TaskAttemptEntity value = new TaskAttemptEntity();
        value.setAttemptId(ATTEMPT_ID);
        value.setTaskId(TASK_ID);
        value.setDeviceId(DEVICE_ID);
        value.setRunId(RUN_ID);
        value.setStatus(status);
        return value;
    }

    private TaskEntity task(List<String> waypointIds) {
        TaskEntity value = new TaskEntity();
        value.setTaskId(TASK_ID);
        value.setRunId(RUN_ID);
        value.setRunTargetId(RUN_TARGET_ID);
        value.setTargetDeviceId(DEVICE_ID);
        value.setTaskPayloadJson(taskPayload(waypointIds));
        return value;
    }

    private ExperimentRunTargetEntity target() {
        ExperimentRunTargetEntity value = new ExperimentRunTargetEntity();
        value.setRunTargetId(RUN_TARGET_ID);
        value.setRunId(RUN_ID);
        value.setDeviceId(DEVICE_ID);
        value.setSequenceId(SEQUENCE_ID);
        return value;
    }

    private String taskPayload(List<String> waypointIds) {
        List<Map<String, Object>> waypoints = waypointIds.stream()
                .map(id -> Map.<String, Object>of("waypoint_id", id))
                .toList();
        return jsonCodec.write(Map.of(
                "goal", "run sequence",
                "waypoint_sequence", Map.of(
                        "sequence_id", SEQUENCE_ID,
                        "behavior_label", BEHAVIOR_LABEL,
                        "profile_package", "com.tencent.mm",
                        "waypoints", waypoints
                )
        ));
    }

    private WaypointSegmentInput segment(String stepId, Long enteredAt, Long arrivedAt, Long dwell) {
        return new WaypointSegmentInput(stepId, BEHAVIOR_LABEL, enteredAt, arrivedAt, dwell);
    }

    private RunEventEntity copyEvent(RunEventEntity source) {
        RunEventEntity copy = new RunEventEntity();
        copy.setAttemptId(source.getAttemptId());
        copy.setTaskId(source.getTaskId());
        copy.setDeviceId(source.getDeviceId());
        copy.setRunId(source.getRunId());
        copy.setScenarioId(source.getScenarioId());
        copy.setStepIndex(source.getStepIndex());
        copy.setActionIndex(source.getActionIndex());
        copy.setEventType(source.getEventType());
        copy.setEventKey(source.getEventKey());
        copy.setState(source.getState());
        copy.setCode(source.getCode());
        copy.setMessage(source.getMessage());
        copy.setPayloadJson(source.getPayloadJson());
        copy.setTs(source.getTs());
        return copy;
    }

    private void assertInvalid(Runnable operation) {
        ResponseStatusException exception = assertThrows(ResponseStatusException.class, operation::run);
        assertEquals(HttpStatus.BAD_REQUEST, exception.getStatusCode());
        assertEquals(ControlErrorCode.WAYPOINT_SEGMENT_INVALID, exception.getReason());
    }
}
