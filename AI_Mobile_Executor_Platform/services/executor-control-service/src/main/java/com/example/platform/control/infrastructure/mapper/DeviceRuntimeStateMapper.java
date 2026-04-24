package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface DeviceRuntimeStateMapper {

    @Insert("""
            INSERT INTO device_runtime_state (
                device_id, registered, online, busy, status, current_task_id, current_attempt_id, current_task_type,
                config_version, lease_expire_at, last_heartbeat_at, last_command, health_json, updated_at
            ) VALUES (
                #{state.deviceId}, #{state.registered}, #{state.online}, #{state.busy}, #{state.status}, #{state.currentTaskId},
                #{state.currentAttemptId}, #{state.currentTaskType}, #{state.configVersion}, #{state.leaseExpireAt},
                #{state.lastHeartbeatAt}, #{state.lastCommand}, #{state.healthJson}, #{state.updatedAt}
            )
            ON DUPLICATE KEY UPDATE
                registered = VALUES(registered),
                online = VALUES(online),
                busy = VALUES(busy),
                status = VALUES(status),
                current_task_id = VALUES(current_task_id),
                current_attempt_id = VALUES(current_attempt_id),
                current_task_type = VALUES(current_task_type),
                config_version = VALUES(config_version),
                lease_expire_at = VALUES(lease_expire_at),
                last_heartbeat_at = VALUES(last_heartbeat_at),
                last_command = VALUES(last_command),
                health_json = VALUES(health_json),
                updated_at = VALUES(updated_at)
            """)
    void upsert(@Param("state") DeviceRuntimeStateEntity state);

    @Select("""
            SELECT device_id, registered, online, busy, status, current_task_id, current_attempt_id, current_task_type,
                   config_version, lease_expire_at, last_heartbeat_at, last_command, health_json, updated_at
            FROM device_runtime_state
            WHERE device_id = #{deviceId}
            """)
    DeviceRuntimeStateEntity findById(@Param("deviceId") String deviceId);

    @Select("""
            SELECT device_id, registered, online, busy, status, current_task_id, current_attempt_id, current_task_type,
                   config_version, lease_expire_at, last_heartbeat_at, last_command, health_json, updated_at
            FROM device_runtime_state
            WHERE device_id = #{deviceId}
            FOR UPDATE
            """)
    DeviceRuntimeStateEntity lockByDeviceId(@Param("deviceId") String deviceId);

    @Update("""
            UPDATE device_runtime_state
            SET busy = #{busy},
                status = #{status},
                current_task_id = #{currentTaskId},
                current_attempt_id = #{currentAttemptId},
                current_task_type = #{currentTaskType},
                lease_expire_at = #{leaseExpireAt},
                last_command = #{lastCommand},
                updated_at = #{updatedAt}
            WHERE device_id = #{deviceId}
            """)
    void updateBusyState(@Param("deviceId") String deviceId,
                         @Param("busy") boolean busy,
                         @Param("status") String status,
                         @Param("currentTaskId") String currentTaskId,
                         @Param("currentAttemptId") String currentAttemptId,
                         @Param("currentTaskType") String currentTaskType,
                         @Param("leaseExpireAt") Long leaseExpireAt,
                         @Param("lastCommand") String lastCommand,
                         @Param("updatedAt") long updatedAt);

    @Update("""
            UPDATE device_runtime_state
            SET busy = #{busy},
                status = #{status},
                current_task_id = #{currentTaskId},
                current_attempt_id = #{currentAttemptId},
                current_task_type = #{currentTaskType},
                lease_expire_at = #{leaseExpireAt},
                updated_at = #{updatedAt}
            WHERE device_id = #{deviceId}
              AND current_attempt_id <=> #{expectedAttemptId}
            """)
    int updateAssignmentIfCurrent(@Param("deviceId") String deviceId,
                                  @Param("expectedAttemptId") String expectedAttemptId,
                                  @Param("busy") boolean busy,
                                  @Param("status") String status,
                                  @Param("currentTaskId") String currentTaskId,
                                  @Param("currentAttemptId") String currentAttemptId,
                                  @Param("currentTaskType") String currentTaskType,
                                  @Param("leaseExpireAt") Long leaseExpireAt,
                                  @Param("updatedAt") long updatedAt);

    @Update("""
            UPDATE device_runtime_state
            SET registered = true,
                online = true,
                status = CASE WHEN status = 'QUIESCED' THEN status ELSE 'ONLINE' END,
                config_version = #{configVersion},
                lease_expire_at = #{leaseExpireAt},
                last_heartbeat_at = #{lastHeartbeatAt},
                last_command = #{lastCommand},
                health_json = #{healthJson},
                updated_at = #{updatedAt}
            WHERE device_id = #{deviceId}
            """)
    int refreshHeartbeat(@Param("deviceId") String deviceId,
                         @Param("configVersion") String configVersion,
                         @Param("leaseExpireAt") Long leaseExpireAt,
                         @Param("lastHeartbeatAt") long lastHeartbeatAt,
                         @Param("lastCommand") String lastCommand,
                         @Param("healthJson") String healthJson,
                         @Param("updatedAt") long updatedAt);

    @Update("""
            UPDATE device_runtime_state
            SET online = false,
                status = CASE WHEN status = 'QUIESCED' THEN status ELSE 'OFFLINE' END,
                updated_at = #{updatedAt}
            WHERE last_heartbeat_at < #{heartbeatThreshold}
              AND online = true
            """)
    int markOfflineStale(@Param("heartbeatThreshold") long heartbeatThreshold,
                         @Param("updatedAt") long updatedAt);

    @Select("""
            SELECT device_id, registered, online, busy, status, current_task_id, current_attempt_id, current_task_type,
                   config_version, lease_expire_at, last_heartbeat_at, last_command, health_json, updated_at
            FROM device_runtime_state
            ORDER BY updated_at DESC
            """)
    List<DeviceRuntimeStateEntity> findAll();
}
