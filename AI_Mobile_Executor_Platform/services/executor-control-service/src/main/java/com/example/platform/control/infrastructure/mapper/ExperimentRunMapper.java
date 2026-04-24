package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.ExperimentRunEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface ExperimentRunMapper {

    @Insert("""
            INSERT INTO experiment_runs (
                run_id, name, description, pool_id, status, final_state, task_type, profile_package,
                task_payload_json, run_config_json, artifact_policy_json, priority, labels_json, source, created_by,
                max_retries_per_device, queue_timeout_ms, cancel_requested, created_at, updated_at, started_at, finished_at
            ) VALUES (
                #{run.runId}, #{run.name}, #{run.description}, #{run.poolId}, #{run.status}, #{run.finalState}, #{run.taskType}, #{run.profilePackage},
                #{run.taskPayloadJson}, #{run.runConfigJson}, #{run.artifactPolicyJson}, #{run.priority}, #{run.labelsJson}, #{run.source}, #{run.createdBy},
                #{run.maxRetriesPerDevice}, #{run.queueTimeoutMs}, #{run.cancelRequested}, #{run.createdAt}, #{run.updatedAt}, #{run.startedAt}, #{run.finishedAt}
            )
            """)
    void insert(@Param("run") ExperimentRunEntity run);

    @Select("""
            SELECT run_id, name, description, pool_id, status, final_state, task_type, profile_package,
                   task_payload_json, run_config_json, artifact_policy_json, priority, labels_json, source, created_by,
                   max_retries_per_device, queue_timeout_ms, cancel_requested, created_at, updated_at, started_at, finished_at
            FROM experiment_runs
            ORDER BY created_at DESC
            """)
    List<ExperimentRunEntity> findAll();

    @Select("""
            SELECT run_id, name, description, pool_id, status, final_state, task_type, profile_package,
                   task_payload_json, run_config_json, artifact_policy_json, priority, labels_json, source, created_by,
                   max_retries_per_device, queue_timeout_ms, cancel_requested, created_at, updated_at, started_at, finished_at
            FROM experiment_runs
            WHERE run_id = #{runId}
            """)
    ExperimentRunEntity findById(@Param("runId") String runId);

    @Select("""
            SELECT run_id, name, description, pool_id, status, final_state, task_type, profile_package,
                   task_payload_json, run_config_json, artifact_policy_json, priority, labels_json, source, created_by,
                   max_retries_per_device, queue_timeout_ms, cancel_requested, created_at, updated_at, started_at, finished_at
            FROM experiment_runs
            WHERE run_id = #{runId}
            FOR UPDATE
            """)
    ExperimentRunEntity lockById(@Param("runId") String runId);

    @Update("""
            UPDATE experiment_runs
            SET name = #{run.name},
                description = #{run.description},
                pool_id = #{run.poolId},
                status = #{run.status},
                final_state = #{run.finalState},
                task_type = #{run.taskType},
                profile_package = #{run.profilePackage},
                task_payload_json = #{run.taskPayloadJson},
                run_config_json = #{run.runConfigJson},
                artifact_policy_json = #{run.artifactPolicyJson},
                priority = #{run.priority},
                labels_json = #{run.labelsJson},
                source = #{run.source},
                created_by = #{run.createdBy},
                max_retries_per_device = #{run.maxRetriesPerDevice},
                queue_timeout_ms = #{run.queueTimeoutMs},
                cancel_requested = #{run.cancelRequested},
                updated_at = #{run.updatedAt},
                started_at = #{run.startedAt},
                finished_at = #{run.finishedAt}
            WHERE run_id = #{run.runId}
            """)
    void update(@Param("run") ExperimentRunEntity run);
}
