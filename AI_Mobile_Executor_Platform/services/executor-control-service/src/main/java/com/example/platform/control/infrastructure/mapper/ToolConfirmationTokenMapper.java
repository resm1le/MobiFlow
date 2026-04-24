package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.ToolConfirmationTokenEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface ToolConfirmationTokenMapper {

    @Insert("""
            INSERT INTO tool_confirmation_tokens (
                confirmation_id, audit_id, tool_name, session_id, arguments_json, caller_context_json,
                token_hash, status, expires_at, used_at, created_at, updated_at
            ) VALUES (
                #{token.confirmationId}, #{token.auditId}, #{token.toolName}, #{token.sessionId}, #{token.argumentsJson}, #{token.callerContextJson},
                #{token.tokenHash}, #{token.status}, #{token.expiresAt}, #{token.usedAt}, #{token.createdAt}, #{token.updatedAt}
            )
            """)
    void insert(@Param("token") ToolConfirmationTokenEntity token);

    @Select("""
            SELECT confirmation_id, audit_id, tool_name, session_id, arguments_json, caller_context_json,
                   token_hash, status, expires_at, used_at, created_at, updated_at
            FROM tool_confirmation_tokens
            WHERE confirmation_id = #{confirmationId}
            """)
    ToolConfirmationTokenEntity findById(@Param("confirmationId") String confirmationId);

    @Select("""
            SELECT confirmation_id, audit_id, tool_name, session_id, arguments_json, caller_context_json,
                   token_hash, status, expires_at, used_at, created_at, updated_at
            FROM tool_confirmation_tokens
            WHERE token_hash = #{tokenHash}
            """)
    ToolConfirmationTokenEntity findByTokenHash(@Param("tokenHash") String tokenHash);

    @Update("""
            UPDATE tool_confirmation_tokens
            SET status = #{token.status},
                used_at = #{token.usedAt},
                updated_at = #{token.updatedAt}
            WHERE confirmation_id = #{token.confirmationId}
            """)
    void update(@Param("token") ToolConfirmationTokenEntity token);
}
