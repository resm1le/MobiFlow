package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.domain.PersistenceModels.ArtifactEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface ArtifactMapper {

    @Insert("""
            INSERT INTO artifacts (
                artifact_id, attempt_id, task_id, run_id, artifact_type, file_name,
                mime_type, size_bytes, object_key, created_at
            ) VALUES (
                #{artifact.artifactId}, #{artifact.attemptId}, #{artifact.taskId}, #{artifact.runId}, #{artifact.artifactType},
                #{artifact.fileName}, #{artifact.mimeType}, #{artifact.sizeBytes}, #{artifact.objectKey}, #{artifact.createdAt}
            )
            """)
    void insert(@Param("artifact") ArtifactEntity artifact);

    @Select("""
            SELECT artifact_id, attempt_id, task_id, run_id, artifact_type, file_name,
                   mime_type, size_bytes, object_key, created_at
            FROM artifacts
            WHERE attempt_id = #{attemptId} AND artifact_id = #{artifactId}
            LIMIT 1
            """)
    ArtifactEntity findByAttemptIdAndArtifactId(@Param("attemptId") String attemptId,
                                                @Param("artifactId") String artifactId);

    @Select("""
            SELECT artifact_id, attempt_id, task_id, run_id, artifact_type, file_name,
                   mime_type, size_bytes, object_key, created_at
            FROM artifacts
            WHERE attempt_id = #{attemptId}
            ORDER BY created_at DESC
            """)
    List<ArtifactEntity> findByAttemptId(@Param("attemptId") String attemptId);

    @Select("""
            SELECT artifact_id, attempt_id, task_id, run_id, artifact_type, file_name,
                   mime_type, size_bytes, object_key, created_at
            FROM artifacts
            WHERE run_id = #{runId}
            ORDER BY created_at DESC
            """)
    List<ArtifactEntity> findByRunId(@Param("runId") String runId);
}
