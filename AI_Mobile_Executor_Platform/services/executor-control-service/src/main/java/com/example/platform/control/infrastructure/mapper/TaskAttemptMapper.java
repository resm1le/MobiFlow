package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface TaskAttemptMapper {

    @Insert("""
            INSERT INTO task_attempts (
                attempt_id, task_id, device_id, run_id, status, final_state, lease_expire_at, failure_reason,
                preflight_summary_json, failure_detail_json, started_at, finished_at, created_at, updated_at
            ) VALUES (
                #{attempt.attemptId}, #{attempt.taskId}, #{attempt.deviceId}, #{attempt.runId}, #{attempt.status}, #{attempt.finalState},
                #{attempt.leaseExpireAt}, #{attempt.failureReason}, #{attempt.preflightSummaryJson}, #{attempt.failureDetailJson},
                #{attempt.startedAt}, #{attempt.finishedAt}, #{attempt.createdAt}, #{attempt.updatedAt}
            )
            """)
    void insert(@Param("attempt") TaskAttemptEntity attempt);

    @Select("""
            SELECT attempt_id, task_id, device_id, run_id, status, final_state, lease_expire_at, failure_reason,
                   preflight_summary_json, failure_detail_json, started_at, finished_at, created_at, updated_at
            FROM task_attempts
            WHERE attempt_id = #{attemptId}
            """)
    TaskAttemptEntity findById(@Param("attemptId") String attemptId);

    @Select("""
            SELECT attempt_id, task_id, device_id, run_id, status, final_state, lease_expire_at, failure_reason,
                   preflight_summary_json, failure_detail_json, started_at, finished_at, created_at, updated_at
            FROM task_attempts
            ORDER BY created_at DESC
            """)
    List<TaskAttemptEntity> findAll();

    @Select("""
            SELECT attempt_id, task_id, device_id, run_id, status, final_state, lease_expire_at, failure_reason,
                   preflight_summary_json, failure_detail_json, started_at, finished_at, created_at, updated_at
            FROM task_attempts
            WHERE device_id = #{deviceId}
            ORDER BY created_at DESC
            """)
    List<TaskAttemptEntity> findByDeviceId(@Param("deviceId") String deviceId);

    @Select("""
            SELECT attempt_id, task_id, device_id, run_id, status, final_state, lease_expire_at, failure_reason,
                   preflight_summary_json, failure_detail_json, started_at, finished_at, created_at, updated_at
            FROM task_attempts
            WHERE task_id = #{taskId}
            ORDER BY created_at DESC
            LIMIT 1
            """)
    TaskAttemptEntity findLatestByTaskId(@Param("taskId") String taskId);

    @Select("""
            SELECT attempt_id, task_id, device_id, run_id, status, final_state, lease_expire_at, failure_reason,
                   preflight_summary_json, failure_detail_json, started_at, finished_at, created_at, updated_at
            FROM task_attempts
            WHERE lease_expire_at IS NOT NULL
              AND lease_expire_at < #{now}
              AND status IN ('CREATED', 'LEASED', 'RUNNING')
            ORDER BY lease_expire_at ASC
            """)
    List<TaskAttemptEntity> findExpiredActiveAttempts(@Param("now") long now);

    @Select("""
            SELECT ta.attempt_id, ta.task_id, ta.device_id, ta.run_id, ta.status, ta.final_state, ta.lease_expire_at, ta.failure_reason,
                   ta.preflight_summary_json, ta.failure_detail_json, ta.started_at, ta.finished_at, ta.created_at, ta.updated_at
            FROM task_attempts ta
            JOIN tasks t ON t.task_id = ta.task_id
            WHERE t.run_target_id = #{runTargetId}
            ORDER BY ta.created_at DESC
            LIMIT #{limit}
            """)
    List<TaskAttemptEntity> findByRunTargetId(@Param("runTargetId") String runTargetId, @Param("limit") int limit);

    @Select("""
            SELECT COUNT(1)
            FROM task_attempts
            WHERE attempt_id = #{attemptId}
              AND device_id = #{deviceId}
              AND status IN ('CREATED', 'LEASED', 'RUNNING')
            """)
    int countActiveAttempt(@Param("deviceId") String deviceId, @Param("attemptId") String attemptId);

    @Update("""
            UPDATE task_attempts
            SET run_id = #{runId},
                status = #{status},
                lease_expire_at = #{leaseExpireAt},
                started_at = COALESCE(started_at, #{startedAt}),
                updated_at = #{updatedAt}
            WHERE attempt_id = #{attemptId}
            """)
    void markRunning(@Param("attemptId") String attemptId,
                     @Param("runId") String runId,
                     @Param("status") String status,
                     @Param("leaseExpireAt") long leaseExpireAt,
                     @Param("startedAt") long startedAt,
                     @Param("updatedAt") long updatedAt);

    @Update("""
            UPDATE task_attempts
            SET lease_expire_at = #{leaseExpireAt},
                updated_at = #{updatedAt}
            WHERE attempt_id = #{attemptId}
              AND device_id = #{deviceId}
              AND status IN ('CREATED', 'LEASED', 'RUNNING')
            """)
    int renewLease(@Param("attemptId") String attemptId,
                   @Param("deviceId") String deviceId,
                   @Param("leaseExpireAt") long leaseExpireAt,
                   @Param("updatedAt") long updatedAt);

    @Update("""
            UPDATE task_attempts
            SET status = #{status},
                final_state = #{finalState},
                failure_reason = #{failureReason},
                preflight_summary_json = #{preflightSummaryJson},
                failure_detail_json = #{failureDetailJson},
                finished_at = #{finishedAt},
                updated_at = #{updatedAt}
            WHERE attempt_id = #{attemptId}
            """)
    void finish(@Param("attemptId") String attemptId,
                @Param("status") String status,
                @Param("finalState") String finalState,
                @Param("failureReason") String failureReason,
                @Param("preflightSummaryJson") String preflightSummaryJson,
                @Param("failureDetailJson") String failureDetailJson,
                @Param("finishedAt") long finishedAt,
                @Param("updatedAt") long updatedAt);

    @Update("""
            UPDATE task_attempts
            SET status = #{status},
                final_state = #{finalState},
                failure_reason = #{failureReason},
                preflight_summary_json = #{preflightSummaryJson},
                failure_detail_json = #{failureDetailJson},
                finished_at = #{finishedAt},
                updated_at = #{updatedAt}
            WHERE attempt_id = #{attemptId}
              AND status IN ('CREATED', 'LEASED', 'RUNNING')
            """)
    int finishIfActive(@Param("attemptId") String attemptId,
                       @Param("status") String status,
                       @Param("finalState") String finalState,
                       @Param("failureReason") String failureReason,
                       @Param("preflightSummaryJson") String preflightSummaryJson,
                       @Param("failureDetailJson") String failureDetailJson,
                       @Param("finishedAt") long finishedAt,
                       @Param("updatedAt") long updatedAt);
}
