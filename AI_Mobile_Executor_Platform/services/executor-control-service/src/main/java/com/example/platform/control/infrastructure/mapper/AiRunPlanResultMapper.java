package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.AiRunPlanResultEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface AiRunPlanResultMapper {

    @Insert("""
            INSERT INTO ai_run_plan_results (
                request_id, result_json, validation_json, model_meta_json, status, created_at, updated_at
            ) VALUES (
                #{result.requestId}, #{result.resultJson}, #{result.validationJson}, #{result.modelMetaJson},
                #{result.status}, #{result.createdAt}, #{result.updatedAt}
            )
            """)
    void insert(@Param("result") AiRunPlanResultEntity result);

    @Select("""
            SELECT request_id, result_json, validation_json, model_meta_json, status, created_at, updated_at
            FROM ai_run_plan_results
            WHERE request_id = #{requestId}
            """)
    AiRunPlanResultEntity findById(@Param("requestId") String requestId);

    @Update("""
            UPDATE ai_run_plan_results
            SET result_json = #{result.resultJson},
                validation_json = #{result.validationJson},
                model_meta_json = #{result.modelMetaJson},
                status = #{result.status},
                updated_at = #{result.updatedAt}
            WHERE request_id = #{result.requestId}
            """)
    void upsert(@Param("result") AiRunPlanResultEntity result);
}
