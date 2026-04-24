package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.AiRunPlanRequestEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface AiRunPlanRequestMapper {

    @Insert("""
            INSERT INTO ai_run_plan_requests (
                request_id, goal_text, constraints_json, context_json, status, materialized_run_id,
                materialized_by, materialized_at, created_at, updated_at
            ) VALUES (
                #{request.requestId}, #{request.goalText}, #{request.constraintsJson}, #{request.contextJson},
                #{request.status}, #{request.materializedRunId}, #{request.materializedBy},
                #{request.materializedAt}, #{request.createdAt}, #{request.updatedAt}
            )
            """)
    void insert(@Param("request") AiRunPlanRequestEntity request);

    @Select("""
            SELECT request_id, goal_text, constraints_json, context_json, status, materialized_run_id,
                   materialized_by, materialized_at, created_at, updated_at
            FROM ai_run_plan_requests
            WHERE request_id = #{requestId}
            """)
    AiRunPlanRequestEntity findById(@Param("requestId") String requestId);

    @Select("""
            SELECT request_id, goal_text, constraints_json, context_json, status, materialized_run_id,
                   materialized_by, materialized_at, created_at, updated_at
            FROM ai_run_plan_requests
            WHERE request_id = #{requestId}
            FOR UPDATE
            """)
    AiRunPlanRequestEntity lockById(@Param("requestId") String requestId);

    @Update("""
            UPDATE ai_run_plan_requests
            SET status = #{status},
                updated_at = #{updatedAt}
            WHERE request_id = #{requestId}
            """)
    void updateStatus(@Param("requestId") String requestId,
                      @Param("status") String status,
                      @Param("updatedAt") long updatedAt);

    @Update("""
            UPDATE ai_run_plan_requests
            SET status = #{request.status},
                materialized_run_id = #{request.materializedRunId},
                materialized_by = #{request.materializedBy},
                materialized_at = #{request.materializedAt},
                updated_at = #{request.updatedAt}
            WHERE request_id = #{request.requestId}
            """)
    void updateMaterialization(@Param("request") AiRunPlanRequestEntity request);
}
