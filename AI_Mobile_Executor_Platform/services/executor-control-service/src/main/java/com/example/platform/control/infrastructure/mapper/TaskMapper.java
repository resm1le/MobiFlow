package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface TaskMapper {

    @Insert("""
            INSERT INTO tasks (
                task_id, run_id, run_target_id, target_device_id, task_type, profile_package, task_payload_json, run_config_json, artifact_policy_json,
                priority, labels_json, source, schedule_version, idempotency_key, status, created_by, created_at, updated_at
            ) VALUES (
                #{task.taskId}, #{task.runId}, #{task.runTargetId}, #{task.targetDeviceId}, #{task.taskType}, #{task.profilePackage}, #{task.taskPayloadJson}, #{task.runConfigJson}, #{task.artifactPolicyJson},
                #{task.priority}, #{task.labelsJson}, #{task.source}, #{task.scheduleVersion}, #{task.idempotencyKey}, #{task.status},
                #{task.createdBy}, #{task.createdAt}, #{task.updatedAt}
            )
            """)
    void insert(@Param("task") TaskEntity task);

    @Select("""
            SELECT task_id, task_type, profile_package, task_payload_json, run_config_json, artifact_policy_json,
                   run_id, run_target_id, target_device_id, priority, labels_json, source, schedule_version, idempotency_key, status, created_by, created_at, updated_at
            FROM tasks
            WHERE task_id = #{taskId}
            """)
    TaskEntity findById(@Param("taskId") String taskId);

    @Select("""
            SELECT task_id, task_type, profile_package, task_payload_json, run_config_json, artifact_policy_json,
                   run_id, run_target_id, target_device_id, priority, labels_json, source, schedule_version, idempotency_key, status, created_by, created_at, updated_at
            FROM tasks
            WHERE task_id = #{taskId}
            FOR UPDATE
            """)
    TaskEntity lockById(@Param("taskId") String taskId);

    @Select("""
            SELECT task_id, task_type, profile_package, task_payload_json, run_config_json, artifact_policy_json,
                   run_id, run_target_id, target_device_id, priority, labels_json, source, schedule_version, idempotency_key, status, created_by, created_at, updated_at
            FROM tasks
            WHERE idempotency_key = #{idempotencyKey}
            """)
    TaskEntity findByIdempotencyKey(@Param("idempotencyKey") String idempotencyKey);

    @Select("""
            SELECT task_id, task_type, profile_package, task_payload_json, run_config_json, artifact_policy_json,
                   run_id, run_target_id, target_device_id, priority, labels_json, source, schedule_version, idempotency_key, status, created_by, created_at, updated_at
            FROM tasks
            ORDER BY created_at DESC
            """)
    List<TaskEntity> findAll();

    @Select("""
            SELECT task_id, task_type, profile_package, task_payload_json, run_config_json, artifact_policy_json,
                   run_id, run_target_id, target_device_id, priority, labels_json, source, schedule_version, idempotency_key, status, created_by, created_at, updated_at
            FROM tasks
            WHERE status = 'QUEUED'
              AND (target_device_id IS NULL OR target_device_id = #{deviceId})
            ORDER BY priority DESC, created_at ASC
            LIMIT #{limit}
            FOR UPDATE SKIP LOCKED
            """)
    List<TaskEntity> findClaimableQueuedTasks(@Param("deviceId") String deviceId, @Param("limit") int limit);

    @Select("""
            SELECT task_id, task_type, profile_package, task_payload_json, run_config_json, artifact_policy_json,
                   run_id, run_target_id, target_device_id, priority, labels_json, source, schedule_version, idempotency_key, status, created_by, created_at, updated_at
            FROM tasks
            WHERE run_id = #{runId}
            ORDER BY created_at ASC
            """)
    List<TaskEntity> findByRunId(@Param("runId") String runId);

    @Select("""
            SELECT task_id, task_type, profile_package, task_payload_json, run_config_json, artifact_policy_json,
                   run_id, run_target_id, target_device_id, priority, labels_json, source, schedule_version, idempotency_key, status, created_by, created_at, updated_at
            FROM tasks
            WHERE run_target_id = #{runTargetId}
            ORDER BY created_at DESC
            """)
    List<TaskEntity> findByRunTargetId(@Param("runTargetId") String runTargetId);

    @Update("""
            UPDATE tasks
            SET status = #{status},
                schedule_version = #{scheduleVersion},
                updated_at = #{updatedAt}
            WHERE task_id = #{taskId}
            """)
    void updateStatus(@Param("taskId") String taskId,
                      @Param("status") String status,
                      @Param("scheduleVersion") String scheduleVersion,
                      @Param("updatedAt") long updatedAt);
}
