package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.ExperimentRunTargetEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface ExperimentRunTargetMapper {

    @Insert("""
            INSERT INTO experiment_run_targets (
                run_target_id, run_id, device_id, sequence_id, status, attempt_count, current_task_id, latest_attempt_id,
                failure_reason, created_at, updated_at, started_at, finished_at
            ) VALUES (
                #{target.runTargetId}, #{target.runId}, #{target.deviceId}, #{target.sequenceId}, #{target.status}, #{target.attemptCount},
                #{target.currentTaskId}, #{target.latestAttemptId}, #{target.failureReason}, #{target.createdAt},
                #{target.updatedAt}, #{target.startedAt}, #{target.finishedAt}
            )
            """)
    void insert(@Param("target") ExperimentRunTargetEntity target);

    @Select("""
            SELECT run_target_id, run_id, device_id, sequence_id, status, attempt_count, current_task_id, latest_attempt_id,
                   failure_reason, created_at, updated_at, started_at, finished_at
            FROM experiment_run_targets
            WHERE run_target_id = #{runTargetId}
            """)
    ExperimentRunTargetEntity findById(@Param("runTargetId") String runTargetId);

    @Select("""
            SELECT run_target_id, run_id, device_id, sequence_id, status, attempt_count, current_task_id, latest_attempt_id,
                   failure_reason, created_at, updated_at, started_at, finished_at
            FROM experiment_run_targets
            WHERE run_target_id = #{runTargetId}
            FOR UPDATE
            """)
    ExperimentRunTargetEntity lockById(@Param("runTargetId") String runTargetId);

    @Select("""
            SELECT run_target_id, run_id, device_id, sequence_id, status, attempt_count, current_task_id, latest_attempt_id,
                   failure_reason, created_at, updated_at, started_at, finished_at
            FROM experiment_run_targets
            WHERE run_id = #{runId}
            ORDER BY created_at ASC
            """)
    List<ExperimentRunTargetEntity> findByRunId(@Param("runId") String runId);

    @Select("""
            SELECT run_target_id, run_id, device_id, sequence_id, status, attempt_count, current_task_id, latest_attempt_id,
                   failure_reason, created_at, updated_at, started_at, finished_at
            FROM experiment_run_targets
            WHERE status IN ('QUEUED', 'RETRY_PENDING')
            ORDER BY updated_at ASC
            """)
    List<ExperimentRunTargetEntity> findPendingQueueTargets();

    @Update("""
            UPDATE experiment_run_targets
            SET status = #{target.status},
                attempt_count = #{target.attemptCount},
                current_task_id = #{target.currentTaskId},
                latest_attempt_id = #{target.latestAttemptId},
                failure_reason = #{target.failureReason},
                updated_at = #{target.updatedAt},
                started_at = #{target.startedAt},
                finished_at = #{target.finishedAt}
            WHERE run_target_id = #{target.runTargetId}
            """)
    void update(@Param("target") ExperimentRunTargetEntity target);
}
