package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.AiFailureTriageResultEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface AiFailureTriageResultMapper {

    @Insert("""
            INSERT INTO ai_failure_triage_results (
                triage_result_id, run_id, run_target_id, attempt_id, context_json, result_json,
                validation_json, model_meta_json, status, created_at, updated_at
            ) VALUES (
                #{result.triageResultId}, #{result.runId}, #{result.runTargetId}, #{result.attemptId}, #{result.contextJson},
                #{result.resultJson}, #{result.validationJson}, #{result.modelMetaJson}, #{result.status},
                #{result.createdAt}, #{result.updatedAt}
            )
            """)
    void insert(@Param("result") AiFailureTriageResultEntity result);

    @Select("""
            SELECT triage_result_id, run_id, run_target_id, attempt_id, context_json, result_json,
                   validation_json, model_meta_json, status, created_at, updated_at
            FROM ai_failure_triage_results
            WHERE triage_result_id = #{triageResultId}
            """)
    AiFailureTriageResultEntity findById(@Param("triageResultId") String triageResultId);

    @Select("""
            SELECT triage_result_id, run_id, run_target_id, attempt_id, context_json, result_json,
                   validation_json, model_meta_json, status, created_at, updated_at
            FROM ai_failure_triage_results
            WHERE run_target_id = #{runTargetId}
            ORDER BY created_at DESC
            LIMIT 1
            """)
    AiFailureTriageResultEntity findLatestByRunTargetId(@Param("runTargetId") String runTargetId);

    @Select("""
            SELECT triage_result_id, run_id, run_target_id, attempt_id, context_json, result_json,
                   validation_json, model_meta_json, status, created_at, updated_at
            FROM ai_failure_triage_results
            WHERE run_target_id = #{runTargetId}
            ORDER BY created_at DESC
            """)
    List<AiFailureTriageResultEntity> findByRunTargetId(@Param("runTargetId") String runTargetId);

    @Update("""
            UPDATE ai_failure_triage_results
            SET result_json = #{result.resultJson},
                validation_json = #{result.validationJson},
                model_meta_json = #{result.modelMetaJson},
                status = #{result.status},
                updated_at = #{result.updatedAt}
            WHERE triage_result_id = #{result.triageResultId}
            """)
    void update(@Param("result") AiFailureTriageResultEntity result);
}
