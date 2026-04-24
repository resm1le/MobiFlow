package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.ArtifactUploadSessionEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface ArtifactUploadSessionMapper {

    @Insert("""
            INSERT INTO artifact_upload_sessions (
                artifact_id, attempt_id, task_id, device_id, run_id, artifact_type, file_name,
                mime_type, declared_size_bytes, object_key, status, upload_expires_at,
                finalized_at, created_at, updated_at
            ) VALUES (
                #{session.artifactId}, #{session.attemptId}, #{session.taskId}, #{session.deviceId}, #{session.runId},
                #{session.artifactType}, #{session.fileName}, #{session.mimeType}, #{session.declaredSizeBytes},
                #{session.objectKey}, #{session.status}, #{session.uploadExpiresAt}, #{session.finalizedAt},
                #{session.createdAt}, #{session.updatedAt}
            )
            """)
    void insert(@Param("session") ArtifactUploadSessionEntity session);

    @Update("""
            UPDATE artifact_upload_sessions
            SET run_id = #{session.runId},
                artifact_type = #{session.artifactType},
                file_name = #{session.fileName},
                mime_type = #{session.mimeType},
                declared_size_bytes = #{session.declaredSizeBytes},
                object_key = #{session.objectKey},
                status = #{session.status},
                upload_expires_at = #{session.uploadExpiresAt},
                finalized_at = #{session.finalizedAt},
                updated_at = #{session.updatedAt}
            WHERE artifact_id = #{session.artifactId}
            """)
    int update(@Param("session") ArtifactUploadSessionEntity session);

    @Select("""
            SELECT artifact_id, attempt_id, task_id, device_id, run_id, artifact_type, file_name,
                   mime_type, declared_size_bytes, object_key, status, upload_expires_at,
                   finalized_at, created_at, updated_at
            FROM artifact_upload_sessions
            WHERE artifact_id = #{artifactId}
            LIMIT 1
            """)
    ArtifactUploadSessionEntity findByArtifactId(@Param("artifactId") String artifactId);

    @Update("""
            UPDATE artifact_upload_sessions
            SET status = 'FINALIZED',
                finalized_at = #{finalizedAt},
                updated_at = #{updatedAt}
            WHERE artifact_id = #{artifactId}
            """)
    int markFinalized(@Param("artifactId") String artifactId,
                      @Param("finalizedAt") long finalizedAt,
                      @Param("updatedAt") long updatedAt);

    @Select("""
            SELECT artifact_id, attempt_id, task_id, device_id, run_id, artifact_type, file_name,
                   mime_type, declared_size_bytes, object_key, status, upload_expires_at,
                   finalized_at, created_at, updated_at
            FROM artifact_upload_sessions
            WHERE status = 'AUTHORIZED'
              AND upload_expires_at < #{now}
            ORDER BY upload_expires_at ASC
            LIMIT #{limit}
            """)
    List<ArtifactUploadSessionEntity> findExpiredAuthorized(@Param("now") long now, @Param("limit") int limit);

    @Update("""
            UPDATE artifact_upload_sessions
            SET status = 'EXPIRED',
                updated_at = #{updatedAt}
            WHERE artifact_id = #{artifactId}
            """)
    int markExpired(@Param("artifactId") String artifactId, @Param("updatedAt") long updatedAt);
}
