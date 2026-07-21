package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.RunEventEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.InsertProvider;
import org.apache.ibatis.annotations.SelectProvider;

import java.util.List;

@Mapper
public interface RunEventMapper {

    @Insert("""
            INSERT INTO run_events (
                attempt_id, task_id, device_id, run_id, scenario_id, step_index, action_index,
                event_type, event_key, state, code, message, payload_json, ts
            ) VALUES (
                #{event.attemptId}, #{event.taskId}, #{event.deviceId}, #{event.runId}, #{event.scenarioId}, #{event.stepIndex},
                #{event.actionIndex}, #{event.eventType}, #{event.eventKey}, #{event.state}, #{event.code}, #{event.message},
                #{event.payloadJson}, #{event.ts}
            )
            """)
    void insert(@Param("event") RunEventEntity event);

    @InsertProvider(type = RunEventSqlProvider.class, method = "insertBatch")
    void insertBatch(@Param("events") List<RunEventEntity> events);

    @InsertProvider(type = RunEventSqlProvider.class, method = "insertBatchNoMutation")
    void insertBatchNoMutation(@Param("events") List<RunEventEntity> events);

    @Select("""
            SELECT id, attempt_id, task_id, device_id, run_id, scenario_id, step_index, action_index,
                   event_type, event_key, state, code, message, payload_json, ts
            FROM run_events
            WHERE attempt_id = #{attemptId}
            ORDER BY ts ASC, id ASC
            """)
    List<RunEventEntity> findByAttemptId(@Param("attemptId") String attemptId);

    @Select("""
            SELECT id, attempt_id, task_id, device_id, run_id, scenario_id, step_index, action_index,
                   event_type, event_key, state, code, message, payload_json, ts
            FROM run_events
            WHERE run_id = #{runId}
            ORDER BY ts ASC, id ASC
            """)
    List<RunEventEntity> findByRunId(@Param("runId") String runId);

    @SelectProvider(type = RunEventSqlProvider.class, method = "findByAttemptIdAndEventKeys")
    List<RunEventEntity> findByAttemptIdAndEventKeys(@Param("attemptId") String attemptId,
                                                     @Param("eventKeys") List<String> eventKeys);

    class RunEventSqlProvider {
        public String insertBatch(@Param("events") List<RunEventEntity> events) {
            return insertBatchSql(events, false);
        }

        public String insertBatchNoMutation(@Param("events") List<RunEventEntity> events) {
            return insertBatchSql(events, true);
        }

        private String insertBatchSql(List<RunEventEntity> events, boolean noMutation) {
            StringBuilder sql = new StringBuilder("""
                    INSERT INTO run_events (
                        attempt_id, task_id, device_id, run_id, scenario_id, step_index, action_index,
                        event_type, event_key, state, code, message, payload_json, ts
                    ) VALUES
                    """);
            for (int index = 0; index < events.size(); index++) {
                if (index > 0) {
                    sql.append(", ");
                }
                sql.append("(")
                        .append("#{events[").append(index).append("].attemptId}, ")
                        .append("#{events[").append(index).append("].taskId}, ")
                        .append("#{events[").append(index).append("].deviceId}, ")
                        .append("#{events[").append(index).append("].runId}, ")
                        .append("#{events[").append(index).append("].scenarioId}, ")
                        .append("#{events[").append(index).append("].stepIndex}, ")
                        .append("#{events[").append(index).append("].actionIndex}, ")
                        .append("#{events[").append(index).append("].eventType}, ")
                        .append("#{events[").append(index).append("].eventKey}, ")
                        .append("#{events[").append(index).append("].state}, ")
                        .append("#{events[").append(index).append("].code}, ")
                        .append("#{events[").append(index).append("].message}, ")
                        .append("#{events[").append(index).append("].payloadJson}, ")
                        .append("#{events[").append(index).append("].ts})");
            }
            if (noMutation) {
                sql.append(" ON DUPLICATE KEY UPDATE event_key = event_key");
            }
            return sql.toString();
        }

        public String findByAttemptIdAndEventKeys(@Param("attemptId") String attemptId,
                                                   @Param("eventKeys") List<String> eventKeys) {
            StringBuilder sql = new StringBuilder("""
                    SELECT id, attempt_id, task_id, device_id, run_id, scenario_id, step_index, action_index,
                           event_type, event_key, state, code, message, payload_json, ts
                    FROM run_events
                    WHERE attempt_id = #{attemptId}
                      AND event_key IN (
                    """);
            for (int index = 0; index < eventKeys.size(); index++) {
                if (index > 0) {
                    sql.append(", ");
                }
                sql.append("#{eventKeys[").append(index).append("]}");
            }
            return sql.append(") ORDER BY step_index ASC, id ASC").toString();
        }
    }
}
