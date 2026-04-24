package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.DeviceEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface DeviceMapper {

    @Insert("""
            INSERT INTO devices (
                device_id, protocol_version, executor_version, brand, model, android_version,
                screen_width, screen_height, installed_profiles_json, tags_json, host_group,
                created_at, updated_at
            ) VALUES (
                #{device.deviceId}, #{device.protocolVersion}, #{device.executorVersion}, #{device.brand}, #{device.model}, #{device.androidVersion},
                #{device.screenWidth}, #{device.screenHeight}, #{device.installedProfilesJson}, #{device.tagsJson}, #{device.hostGroup},
                #{device.createdAt}, #{device.updatedAt}
            )
            ON DUPLICATE KEY UPDATE
                protocol_version = VALUES(protocol_version),
                executor_version = VALUES(executor_version),
                brand = VALUES(brand),
                model = VALUES(model),
                android_version = VALUES(android_version),
                screen_width = VALUES(screen_width),
                screen_height = VALUES(screen_height),
                installed_profiles_json = VALUES(installed_profiles_json),
                tags_json = VALUES(tags_json),
                host_group = VALUES(host_group),
                updated_at = VALUES(updated_at)
            """)
    void upsert(@Param("device") DeviceEntity device);

    @Select("""
            SELECT device_id, protocol_version, executor_version, brand, model, android_version,
                   screen_width, screen_height, installed_profiles_json, tags_json, host_group,
                   created_at, updated_at
            FROM devices
            WHERE device_id = #{deviceId}
            """)
    DeviceEntity findById(@Param("deviceId") String deviceId);

    @Select("""
            SELECT device_id, protocol_version, executor_version, brand, model, android_version,
                   screen_width, screen_height, installed_profiles_json, tags_json, host_group,
                   created_at, updated_at
            FROM devices
            ORDER BY updated_at DESC
            """)
    List<DeviceEntity> findAll();
}
