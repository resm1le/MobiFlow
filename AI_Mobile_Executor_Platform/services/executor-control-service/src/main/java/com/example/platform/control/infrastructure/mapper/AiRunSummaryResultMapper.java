package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.AiRunSummaryResultEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface AiRunSummaryResultMapper {

    @Insert("""
            INSERT INTO ai_run_summary_results (
                summary_id, run_id, context_json, result_json, validation_json, model_meta_json,
                status, created_at, updated_at
            ) VALUES (
                #{result.summaryId}, #{result.runId}, #{result.contextJson}, #{result.resultJson},
                #{result.validationJson}, #{result.modelMetaJson}, #{result.status},
                #{result.createdAt}, #{result.updatedAt}
            )
            """)
    void insert(@Param("result") AiRunSummaryResultEntity result);

    @Select("""
            SELECT summary_id, run_id, context_json, result_json, validation_json, model_meta_json,
                   status, created_at, updated_at
            FROM ai_run_summary_results
            WHERE summary_id = #{summaryId}
            """)
    AiRunSummaryResultEntity findById(@Param("summaryId") String summaryId);

    @Select("""
            SELECT summary_id, run_id, context_json, result_json, validation_json, model_meta_json,
                   status, created_at, updated_at
            FROM ai_run_summary_results
            WHERE run_id = #{runId}
            ORDER BY created_at DESC
            LIMIT 1
            """)
    AiRunSummaryResultEntity findLatestByRunId(@Param("runId") String runId);

    @Update("""
            UPDATE ai_run_summary_results
            SET result_json = #{result.resultJson},
                validation_json = #{result.validationJson},
                model_meta_json = #{result.modelMetaJson},
                status = #{result.status},
                updated_at = #{result.updatedAt}
            WHERE summary_id = #{result.summaryId}
            """)
    void update(@Param("result") AiRunSummaryResultEntity result);
}
