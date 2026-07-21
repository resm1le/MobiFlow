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
import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class WaypointTimelineService {

    private static final int MAX_SEGMENTS = 256;
    private static final String EVENT_TYPE = "WAYPOINT_SEGMENT";
    private static final Set<String> TERMINAL_ATTEMPT_STATUSES = Set.of(
            DomainValues.ATTEMPT_STATUS_SUCCEEDED,
            DomainValues.ATTEMPT_STATUS_FAILED,
            DomainValues.ATTEMPT_STATUS_CANCELLED,
            DomainValues.ATTEMPT_STATUS_PRECHECK_FAILED,
            DomainValues.ATTEMPT_STATUS_SYSTEM_ABORTED,
            DomainValues.ATTEMPT_STATUS_LEASE_EXPIRED
    );
    private static final Set<String> PAYLOAD_KEYS = Set.of(
            "sequence_id",
            "step_id",
            "behavior_label",
            "deviceId",
            "entered_at_ms",
            "arrived_at_ms",
            "dwell_ms"
    );

    private final TaskAttemptMapper attemptMapper;
    private final TaskMapper taskMapper;
    private final ExperimentRunTargetMapper targetMapper;
    private final RunEventMapper runEventMapper;
    private final JsonCodec jsonCodec;
    private final Clock clock;

    public WaypointTimelineService(TaskAttemptMapper attemptMapper,
                                   TaskMapper taskMapper,
                                   ExperimentRunTargetMapper targetMapper,
                                   RunEventMapper runEventMapper,
                                   JsonCodec jsonCodec) {
        this(attemptMapper, taskMapper, targetMapper, runEventMapper, jsonCodec, Clock.systemUTC());
    }

    WaypointTimelineService(TaskAttemptMapper attemptMapper,
                            TaskMapper taskMapper,
                            ExperimentRunTargetMapper targetMapper,
                            RunEventMapper runEventMapper,
                            JsonCodec jsonCodec,
                            Clock clock) {
        this.attemptMapper = attemptMapper;
        this.taskMapper = taskMapper;
        this.targetMapper = targetMapper;
        this.runEventMapper = runEventMapper;
        this.jsonCodec = jsonCodec;
        this.clock = clock;
    }

    @Transactional
    public List<RunEventEntity> record(String runTargetId,
                                       String attemptId,
                                       List<WaypointSegmentInput> waypointSegments) {
        requireNonBlank(runTargetId);
        requireNonBlank(attemptId);
        if (waypointSegments == null || waypointSegments.isEmpty() || waypointSegments.size() > MAX_SEGMENTS) {
            throw invalid();
        }

        TaskAttemptEntity attempt = attemptMapper.lockById(attemptId);
        if (attempt == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.ATTEMPT_NOT_FOUND);
        }
        if (!TERMINAL_ATTEMPT_STATUSES.contains(attempt.getStatus())) {
            throw invalid();
        }

        TaskEntity task = taskMapper.findById(attempt.getTaskId());
        if (task == null) {
            throw invalid();
        }
        ExperimentRunTargetEntity target = targetMapper.findById(runTargetId);
        if (target == null) {
            throw ControlApiExceptions.notFound(ControlErrorCode.RUN_TARGET_NOT_FOUND);
        }
        validateLineage(runTargetId, attempt, task, target);

        ResolvedSequence sequence = parseSequence(task.getTaskPayloadJson());
        if (!Objects.equals(target.getSequenceId(), sequence.sequenceId())) {
            throw invalid();
        }
        validateStepOrder(waypointSegments, sequence);

        long receivedAt = clock.millis();
        List<RunEventEntity> expected = new ArrayList<>(waypointSegments.size());
        for (int index = 0; index < waypointSegments.size(); index++) {
            expected.add(toEvent(index, waypointSegments.get(index), sequence, attempt, task, target, receivedAt));
        }

        List<String> eventKeys = expected.stream().map(RunEventEntity::getEventKey).toList();
        Map<String, RunEventEntity> existingByKey = uniqueByEventKey(
                runEventMapper.findByAttemptIdAndEventKeys(attemptId, eventKeys)
        );
        List<RunEventEntity> missing = new ArrayList<>();
        for (RunEventEntity event : expected) {
            RunEventEntity existing = existingByKey.get(event.getEventKey());
            if (existing == null) {
                missing.add(event);
            } else if (!sameCanonicalEvent(existing, event)) {
                throw conflict();
            }
        }
        if (!missing.isEmpty()) {
            runEventMapper.insertBatchNoMutation(missing);
        }

        Map<String, RunEventEntity> persistedByKey = uniqueByEventKey(
                runEventMapper.findByAttemptIdAndEventKeys(attemptId, eventKeys)
        );
        if (persistedByKey.size() != expected.size()) {
            throw conflict();
        }
        List<RunEventEntity> persisted = new ArrayList<>(expected.size());
        for (RunEventEntity expectedEvent : expected) {
            RunEventEntity persistedEvent = persistedByKey.get(expectedEvent.getEventKey());
            if (persistedEvent == null || !sameCanonicalEvent(persistedEvent, expectedEvent)) {
                throw conflict();
            }
            persisted.add(persistedEvent);
        }
        return List.copyOf(persisted);
    }

    private void validateLineage(String runTargetId,
                                 TaskAttemptEntity attempt,
                                 TaskEntity task,
                                 ExperimentRunTargetEntity target) {
        if (!Objects.equals(attempt.getTaskId(), task.getTaskId())
                || !Objects.equals(task.getRunTargetId(), runTargetId)
                || !Objects.equals(target.getRunTargetId(), runTargetId)
                || !Objects.equals(attempt.getRunId(), task.getRunId())
                || !Objects.equals(task.getRunId(), target.getRunId())
                || !Objects.equals(attempt.getDeviceId(), target.getDeviceId())
                || !Objects.equals(task.getTargetDeviceId(), target.getDeviceId())
                || isBlank(attempt.getRunId())
                || isBlank(attempt.getDeviceId())
                || isBlank(target.getSequenceId())) {
            throw invalid();
        }
    }

    private ResolvedSequence parseSequence(String taskPayloadJson) {
        Map<String, Object> taskPayload;
        try {
            taskPayload = jsonCodec.readMap(taskPayloadJson);
        } catch (RuntimeException exception) {
            throw invalid();
        }
        if (!(taskPayload.get("waypoint_sequence") instanceof Map<?, ?> sequenceMap)) {
            throw invalid();
        }
        String sequenceId = requiredString(sequenceMap.get("sequence_id"));
        String behaviorLabel = requiredString(sequenceMap.get("behavior_label"));
        if (!(sequenceMap.get("waypoints") instanceof List<?> waypointValues)
                || waypointValues.isEmpty()
                || waypointValues.size() > MAX_SEGMENTS) {
            throw invalid();
        }
        List<String> waypointIds = new ArrayList<>(waypointValues.size());
        for (Object value : waypointValues) {
            if (!(value instanceof Map<?, ?> waypoint)) {
                throw invalid();
            }
            waypointIds.add(requiredString(waypoint.get("waypoint_id")));
        }
        if (waypointIds.size() != Set.copyOf(waypointIds).size()) {
            throw invalid();
        }
        return new ResolvedSequence(sequenceId, behaviorLabel, List.copyOf(waypointIds));
    }

    private void validateStepOrder(List<WaypointSegmentInput> segments, ResolvedSequence sequence) {
        if (segments.size() != sequence.waypointIds().size()) {
            throw invalid();
        }
        for (int index = 0; index < segments.size(); index++) {
            WaypointSegmentInput segment = segments.get(index);
            if (segment == null
                    || segment.deviceId() != null
                    || segment.sequenceId() != null
                    || !Objects.equals(sequence.waypointIds().get(index), segment.stepId())
                    || !Objects.equals(sequence.behaviorLabel(), segment.behaviorLabel())) {
                throw invalid();
            }
        }
    }

    private RunEventEntity toEvent(int index,
                                   WaypointSegmentInput segment,
                                   ResolvedSequence sequence,
                                   TaskAttemptEntity attempt,
                                   TaskEntity task,
                                   ExperimentRunTargetEntity target,
                                   long receivedAt) {
        SegmentTiming timing = validateTiming(segment, receivedAt);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("sequence_id", sequence.sequenceId());
        payload.put("step_id", segment.stepId());
        payload.put("behavior_label", segment.behaviorLabel());
        payload.put("deviceId", target.getDeviceId());
        payload.put("entered_at_ms", segment.enteredAtMs());
        payload.put("arrived_at_ms", segment.arrivedAtMs());
        payload.put("dwell_ms", segment.dwellMs());

        RunEventEntity event = new RunEventEntity();
        event.setAttemptId(attempt.getAttemptId());
        event.setTaskId(task.getTaskId());
        event.setDeviceId(target.getDeviceId());
        event.setRunId(target.getRunId());
        event.setScenarioId(sequence.sequenceId());
        event.setStepIndex(index);
        event.setActionIndex(null);
        event.setEventType(EVENT_TYPE);
        event.setEventKey("waypoint:" + index);
        event.setState(timing.state());
        event.setCode(null);
        event.setMessage("waypoint_segment:" + index + ":" + timing.state());
        event.setPayloadJson(jsonCodec.write(payload));
        event.setTs(timing.timestamp());
        return event;
    }

    private SegmentTiming validateTiming(WaypointSegmentInput segment, long receivedAt) {
        Long entered = segment.enteredAtMs();
        Long arrived = segment.arrivedAtMs();
        Long dwell = segment.dwellMs();
        if (entered == null && arrived == null && dwell == null) {
            return new SegmentTiming("INCOMPLETE", receivedAt);
        }
        if (entered != null && arrived == null && dwell == null && entered >= 0) {
            return new SegmentTiming("INTERRUPTED", entered);
        }
        if (entered != null
                && arrived != null
                && dwell != null
                && entered >= 0
                && arrived >= entered
                && dwell >= 0
                && dwell == arrived - entered) {
            return new SegmentTiming("COMPLETE", arrived);
        }
        throw invalid();
    }

    private Map<String, RunEventEntity> uniqueByEventKey(List<RunEventEntity> events) {
        if (events == null) {
            return Map.of();
        }
        try {
            return events.stream().collect(Collectors.toMap(
                    RunEventEntity::getEventKey,
                    Function.identity(),
                    (left, right) -> {
                        throw conflict();
                    },
                    LinkedHashMap::new
            ));
        } catch (NullPointerException exception) {
            throw conflict();
        }
    }

    private boolean sameCanonicalEvent(RunEventEntity actual, RunEventEntity expected) {
        return Objects.equals(actual.getAttemptId(), expected.getAttemptId())
                && Objects.equals(actual.getTaskId(), expected.getTaskId())
                && Objects.equals(actual.getDeviceId(), expected.getDeviceId())
                && Objects.equals(actual.getRunId(), expected.getRunId())
                && Objects.equals(actual.getScenarioId(), expected.getScenarioId())
                && Objects.equals(actual.getStepIndex(), expected.getStepIndex())
                && Objects.equals(actual.getActionIndex(), expected.getActionIndex())
                && Objects.equals(actual.getEventType(), expected.getEventType())
                && Objects.equals(actual.getEventKey(), expected.getEventKey())
                && Objects.equals(actual.getState(), expected.getState())
                && Objects.equals(actual.getCode(), expected.getCode())
                && Objects.equals(actual.getMessage(), expected.getMessage())
                && ("INCOMPLETE".equals(expected.getState()) || actual.getTs() == expected.getTs())
                && sameCanonicalPayload(actual.getPayloadJson(), expected.getPayloadJson());
    }

    private boolean sameCanonicalPayload(String actualJson, String expectedJson) {
        Map<String, Object> actual;
        Map<String, Object> expected;
        try {
            actual = jsonCodec.readMap(actualJson);
            expected = jsonCodec.readMap(expectedJson);
        } catch (RuntimeException exception) {
            return false;
        }
        if (!actual.keySet().equals(PAYLOAD_KEYS) || !expected.keySet().equals(PAYLOAD_KEYS)) {
            return false;
        }
        return Objects.equals(actual.get("sequence_id"), expected.get("sequence_id"))
                && Objects.equals(actual.get("step_id"), expected.get("step_id"))
                && Objects.equals(actual.get("behavior_label"), expected.get("behavior_label"))
                && Objects.equals(actual.get("deviceId"), expected.get("deviceId"))
                && sameNullableLong(actual.get("entered_at_ms"), expected.get("entered_at_ms"))
                && sameNullableLong(actual.get("arrived_at_ms"), expected.get("arrived_at_ms"))
                && sameNullableLong(actual.get("dwell_ms"), expected.get("dwell_ms"));
    }

    private boolean sameNullableLong(Object left, Object right) {
        if (left == null || right == null) {
            return left == right;
        }
        return left instanceof Number leftNumber
                && right instanceof Number rightNumber
                && leftNumber.longValue() == rightNumber.longValue();
    }

    private static String requiredString(Object value) {
        if (!(value instanceof String text) || isBlank(text)) {
            throw invalid();
        }
        return text;
    }

    private static void requireNonBlank(String value) {
        if (isBlank(value)) {
            throw invalid();
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static org.springframework.web.server.ResponseStatusException invalid() {
        return ControlApiExceptions.badRequest(ControlErrorCode.WAYPOINT_SEGMENT_INVALID);
    }

    private static org.springframework.web.server.ResponseStatusException conflict() {
        return ControlApiExceptions.conflict(ControlErrorCode.WAYPOINT_SEGMENT_CONFLICT);
    }

    public record WaypointSegmentInput(
            @JsonProperty("step_id") String stepId,
            @JsonProperty("behavior_label") String behaviorLabel,
            @JsonProperty("entered_at_ms") Long enteredAtMs,
            @JsonProperty("arrived_at_ms") Long arrivedAtMs,
            @JsonProperty("dwell_ms") Long dwellMs,
            @JsonProperty("deviceId") String deviceId,
            @JsonProperty("sequenceId") String sequenceId
    ) {
        public WaypointSegmentInput(String stepId,
                                    String behaviorLabel,
                                    Long enteredAtMs,
                                    Long arrivedAtMs,
                                    Long dwellMs) {
            this(stepId, behaviorLabel, enteredAtMs, arrivedAtMs, dwellMs, null, null);
        }
    }

    private record ResolvedSequence(String sequenceId, String behaviorLabel, List<String> waypointIds) {
    }

    private record SegmentTiming(String state, long timestamp) {
    }
}
