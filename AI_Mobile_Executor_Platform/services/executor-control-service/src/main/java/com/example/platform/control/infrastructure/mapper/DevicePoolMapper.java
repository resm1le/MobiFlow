package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.DevicePoolEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface DevicePoolMapper {

    @Insert("""
            INSERT INTO device_pools (
                pool_id, name, description, host_group, device_ids_json, required_tags_json, excluded_tags_json,
                created_by, created_at, updated_at
            ) VALUES (
                #{pool.poolId}, #{pool.name}, #{pool.description}, #{pool.hostGroup}, #{pool.deviceIdsJson},
                #{pool.requiredTagsJson}, #{pool.excludedTagsJson}, #{pool.createdBy}, #{pool.createdAt}, #{pool.updatedAt}
            )
            """)
    void insert(@Param("pool") DevicePoolEntity pool);

    @Select("""
            SELECT pool_id, name, description, host_group, device_ids_json, required_tags_json, excluded_tags_json,
                   created_by, created_at, updated_at
            FROM device_pools
            ORDER BY created_at DESC
            """)
    List<DevicePoolEntity> findAll();

    @Select("""
            SELECT pool_id, name, description, host_group, device_ids_json, required_tags_json, excluded_tags_json,
                   created_by, created_at, updated_at
            FROM device_pools
            WHERE pool_id = #{poolId}
            """)
    DevicePoolEntity findById(@Param("poolId") String poolId);
}
