package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.DeviceCommandEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface DeviceCommandMapper {

    @Insert("""
            INSERT INTO device_commands (
                device_id, type, attempt_id, status, payload_json, issued_at, acked_at, expire_at
            ) VALUES (
                #{command.deviceId}, #{command.type}, #{command.attemptId}, #{command.status}, #{command.payloadJson},
                #{command.issuedAt}, #{command.ackedAt}, #{command.expireAt}
            )
            """)
    @Options(useGeneratedKeys = true, keyProperty = "command.commandId")
    void insert(@Param("command") DeviceCommandEntity command);

    @Select("""
            SELECT command_id, device_id, type, attempt_id, status, payload_json, issued_at, acked_at, expire_at
            FROM device_commands
            WHERE device_id = #{deviceId}
              AND status = 'PENDING'
              AND (expire_at IS NULL OR expire_at >= #{now})
            ORDER BY issued_at ASC
            """)
    List<DeviceCommandEntity> findPendingByDevice(@Param("deviceId") String deviceId, @Param("now") long now);

    @Select("""
            SELECT COUNT(1)
            FROM device_commands
            WHERE attempt_id = #{attemptId}
              AND type = #{type}
              AND status = 'PENDING'
              AND (expire_at IS NULL OR expire_at >= #{now})
            """)
    int countPendingByAttemptAndType(@Param("attemptId") String attemptId,
                                     @Param("type") String type,
                                     @Param("now") long now);

    @Update("""
            UPDATE device_commands
            SET status = #{status}
            WHERE command_id = #{commandId}
            """)
    void updateStatus(@Param("commandId") long commandId, @Param("status") String status);

    @Update("""
            DELETE FROM device_commands
            WHERE status = 'PENDING'
              AND expire_at IS NOT NULL
              AND expire_at < #{now}
            """)
    int deleteExpiredPending(@Param("now") long now);
}
