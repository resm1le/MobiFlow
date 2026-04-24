package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.ToolExecutionAuditEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface ToolExecutionAuditMapper {

    @Insert("""
            INSERT INTO tool_execution_audits (
                audit_id, request_id, session_id, tool_name, risk_level, status,
                request_json, caller_context_json, response_json, entity_refs_json, created_at, updated_at
            ) VALUES (
                #{audit.auditId}, #{audit.requestId}, #{audit.sessionId}, #{audit.toolName}, #{audit.riskLevel}, #{audit.status},
                #{audit.requestJson}, #{audit.callerContextJson}, #{audit.responseJson}, #{audit.entityRefsJson}, #{audit.createdAt}, #{audit.updatedAt}
            )
            """)
    void insert(@Param("audit") ToolExecutionAuditEntity audit);

    @Select("""
            SELECT audit_id, request_id, session_id, tool_name, risk_level, status,
                   request_json, caller_context_json, response_json, entity_refs_json, created_at, updated_at
            FROM tool_execution_audits
            WHERE request_id = #{requestId}
            """)
    ToolExecutionAuditEntity findByRequestId(@Param("requestId") String requestId);

    @Select("""
            SELECT audit_id, request_id, session_id, tool_name, risk_level, status,
                   request_json, caller_context_json, response_json, entity_refs_json, created_at, updated_at
            FROM tool_execution_audits
            WHERE audit_id = #{auditId}
            """)
    ToolExecutionAuditEntity findById(@Param("auditId") String auditId);

    @Update("""
            UPDATE tool_execution_audits
            SET status = #{audit.status},
                response_json = #{audit.responseJson},
                entity_refs_json = #{audit.entityRefsJson},
                updated_at = #{audit.updatedAt}
            WHERE audit_id = #{audit.auditId}
            """)
    void update(@Param("audit") ToolExecutionAuditEntity audit);

    @Select("""
            SELECT audit_id, request_id, session_id, tool_name, risk_level, status,
                   request_json, caller_context_json, response_json, entity_refs_json, created_at, updated_at
            FROM tool_execution_audits
            WHERE session_id = #{sessionId}
            ORDER BY created_at ASC
            """)
    List<ToolExecutionAuditEntity> findBySessionId(@Param("sessionId") String sessionId);

    @Select("""
            SELECT audit_id, request_id, session_id, tool_name, risk_level, status,
                   request_json, caller_context_json, response_json, entity_refs_json, created_at, updated_at
            FROM tool_execution_audits
            WHERE JSON_UNQUOTE(JSON_EXTRACT(entity_refs_json, '$.runId')) = #{runId}
            ORDER BY created_at ASC
            """)
    List<ToolExecutionAuditEntity> findByRunId(@Param("runId") String runId);

    @Select("""
            SELECT audit_id, request_id, session_id, tool_name, risk_level, status,
                   request_json, caller_context_json, response_json, entity_refs_json, created_at, updated_at
            FROM tool_execution_audits
            WHERE JSON_UNQUOTE(JSON_EXTRACT(entity_refs_json, '$.attemptId')) = #{attemptId}
            ORDER BY created_at ASC
            """)
    List<ToolExecutionAuditEntity> findByAttemptId(@Param("attemptId") String attemptId);

    @Select("""
            SELECT audit_id, request_id, session_id, tool_name, risk_level, status,
                   request_json, caller_context_json, response_json, entity_refs_json, created_at, updated_at
            FROM tool_execution_audits
            WHERE session_id = #{sessionId}
              AND JSON_UNQUOTE(JSON_EXTRACT(entity_refs_json, '$.runId')) = #{runId}
            ORDER BY created_at ASC
            """)
    List<ToolExecutionAuditEntity> findBySessionIdAndRunId(
            @Param("sessionId") String sessionId,
            @Param("runId") String runId
    );

    @Select("""
            SELECT audit_id, request_id, session_id, tool_name, risk_level, status,
                   request_json, caller_context_json, response_json, entity_refs_json, created_at, updated_at
            FROM tool_execution_audits
            ORDER BY created_at ASC
            """)
    List<ToolExecutionAuditEntity> listAll();
}
