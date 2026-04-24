package com.example.platform.control.application;

import com.example.platform.control.api.ExecutorApiModels.ArtifactUploadFinalizeRequest;
import com.example.platform.control.api.ExecutorApiModels.ArtifactUploadFinalizeResponse;
import com.example.platform.control.api.ExecutorApiModels.ArtifactUploadTicketRequest;
import com.example.platform.control.api.ExecutorApiModels.ArtifactUploadTicketResponse;
import com.example.platform.control.api.ExecutorAuthContext;
import com.example.platform.control.domain.PersistenceModels.ArtifactEntity;
import com.example.platform.control.domain.PersistenceModels.ArtifactUploadSessionEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.infrastructure.mapper.ArtifactMapper;
import com.example.platform.control.infrastructure.mapper.ArtifactUploadSessionMapper;
import com.example.platform.control.infrastructure.mapper.TaskAttemptMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ArtifactUploadServiceTest {

    private TaskAttemptMapper attemptMapper;
    private ArtifactMapper artifactMapper;
    private ArtifactUploadSessionMapper uploadSessionMapper;
    private ArtifactObjectStore artifactObjectStore;
    private ControlProperties controlProperties;
    private AttemptAccessValidator attemptAccessValidator;
    private ArtifactUploadService artifactUploadService;

    @BeforeEach
    void setUp() {
        attemptMapper = Mockito.mock(TaskAttemptMapper.class);
        artifactMapper = Mockito.mock(ArtifactMapper.class);
        uploadSessionMapper = Mockito.mock(ArtifactUploadSessionMapper.class);
        artifactObjectStore = Mockito.mock(ArtifactObjectStore.class);
        controlProperties = new ControlProperties();
        controlProperties.getArtifacts().setUploadTicketTtlMs(60_000L);
        attemptAccessValidator = new AttemptAccessValidator(attemptMapper);
        artifactUploadService = new ArtifactUploadService(
                attemptAccessValidator,
                artifactMapper,
                uploadSessionMapper,
                artifactObjectStore,
                controlProperties
        );
    }

    @Test
    void requestTicketCreatesSessionAndReturnsPresignedPut() {
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt());
        when(uploadSessionMapper.findByArtifactId("artifact-1")).thenReturn(null);
        when(artifactObjectStore.presignPut(anyString(), eq("image/png"), anyLong()))
                .thenReturn(new ArtifactObjectStore.PresignedUpload(
                        "http://minio/upload",
                        Map.of("Content-Type", "image/png"),
                        123456L
                ));

        ArtifactUploadTicketResponse response = artifactUploadService.requestUploadTicket(
                authContext(),
                "attempt-1",
                new ArtifactUploadTicketRequest(
                        "task-1",
                        "run-1",
                        "artifact-1",
                        "screenshot",
                        "screen.png",
                        "image/png",
                        100L
                )
        );

        assertEquals(ArtifactUploadMode.DIRECT_PUT_V2, response.artifactUploadMode());
        assertEquals("http://minio/upload", response.uploadUrl());
        assertEquals("PUT", response.httpMethod());
        verify(uploadSessionMapper).insert(any());
    }

    @Test
    void requestTicketRefreshesExistingAuthorizedSession() {
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt());
        when(uploadSessionMapper.findByArtifactId("artifact-1"))
                .thenReturn(session("AUTHORIZED", "artifact-1", "attempt-1", "task-1", "device-1", "run-1"));
        when(artifactObjectStore.presignPut(anyString(), eq("image/png"), anyLong()))
                .thenReturn(new ArtifactObjectStore.PresignedUpload(
                        "http://minio/upload-2",
                        Map.of("Content-Type", "image/png"),
                        123456L
                ));

        ArtifactUploadTicketResponse response = artifactUploadService.requestUploadTicket(
                authContext(),
                "attempt-1",
                new ArtifactUploadTicketRequest(
                        "task-1",
                        "run-1",
                        "artifact-1",
                        "screenshot",
                        "screen.png",
                        "image/png",
                        100L
                )
        );

        assertEquals("http://minio/upload-2", response.uploadUrl());
        verify(uploadSessionMapper).update(any());
        verify(uploadSessionMapper, never()).insert(any());
    }

    @Test
    void finalizePersistsArtifactAndMarksSessionFinalized() {
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt());
        when(artifactMapper.findByAttemptIdAndArtifactId("attempt-1", "artifact-1")).thenReturn(null);
        when(uploadSessionMapper.findByArtifactId("artifact-1"))
                .thenReturn(session("AUTHORIZED", "artifact-1", "attempt-1", "task-1", "device-1", "run-1"));
        when(artifactObjectStore.stat("artifacts/task-1/attempt-1/artifact-1/screen.png"))
                .thenReturn(new ArtifactObjectStore.StoredObjectMetadata(222L, "image/png", "etag-1"));

        ArtifactUploadFinalizeResponse response = artifactUploadService.finalizeUpload(
                authContext(),
                "attempt-1",
                "artifact-1",
                new ArtifactUploadFinalizeRequest("task-1", "run-1", "artifact-1", "etag-1")
        );

        assertEquals(222L, response.sizeBytes());
        ArgumentCaptor<ArtifactEntity> artifactCaptor = ArgumentCaptor.forClass(ArtifactEntity.class);
        verify(artifactMapper).insert(artifactCaptor.capture());
        assertEquals("artifact-1", artifactCaptor.getValue().getArtifactId());
        verify(uploadSessionMapper).markFinalized(eq("artifact-1"), anyLong(), anyLong());
    }

    @Test
    void finalizeDeletesObjectWhenMetadataInsertFails() {
        when(attemptMapper.findById("attempt-1")).thenReturn(attempt());
        when(artifactMapper.findByAttemptIdAndArtifactId("attempt-1", "artifact-1")).thenReturn(null);
        when(uploadSessionMapper.findByArtifactId("artifact-1"))
                .thenReturn(session("AUTHORIZED", "artifact-1", "attempt-1", "task-1", "device-1", "run-1"));
        when(artifactObjectStore.stat("artifacts/task-1/attempt-1/artifact-1/screen.png"))
                .thenReturn(new ArtifactObjectStore.StoredObjectMetadata(222L, "image/png", "etag-1"));
        Mockito.doThrow(new RuntimeException("db failed")).when(artifactMapper).insert(any());

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> artifactUploadService.finalizeUpload(
                        authContext(),
                        "attempt-1",
                        "artifact-1",
                        new ArtifactUploadFinalizeRequest("task-1", "run-1", "artifact-1", "etag-1")
                )
        );

        assertEquals(ControlErrorCode.ARTIFACT_UPLOAD_FAILED, exception.getReason());
        verify(artifactObjectStore).delete("artifacts/task-1/attempt-1/artifact-1/screen.png");
        verify(uploadSessionMapper, never()).markFinalized(anyString(), anyLong(), anyLong());
    }

    @Test
    void cleanupExpiresAuthorizedSessionsAndDeletesObjects() {
        when(uploadSessionMapper.findExpiredAuthorized(eq(10_000L), eq(100))).thenReturn(List.of(
                session("AUTHORIZED", "artifact-1", "attempt-1", "task-1", "device-1", "run-1")
        ));
        when(uploadSessionMapper.markExpired("artifact-1", 10_000L)).thenReturn(1);

        int cleaned = artifactUploadService.cleanupExpiredUploads(10_000L);

        assertEquals(1, cleaned);
        verify(artifactObjectStore).delete("artifacts/task-1/attempt-1/artifact-1/screen.png");
        verify(uploadSessionMapper).markExpired("artifact-1", 10_000L);
    }

    private TaskAttemptEntity attempt() {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId("attempt-1");
        attempt.setTaskId("task-1");
        attempt.setRunId("run-1");
        attempt.setDeviceId("device-1");
        return attempt;
    }

    private ArtifactUploadSessionEntity session(String status,
                                                String artifactId,
                                                String attemptId,
                                                String taskId,
                                                String deviceId,
                                                String runId) {
        ArtifactUploadSessionEntity session = new ArtifactUploadSessionEntity();
        session.setArtifactId(artifactId);
        session.setAttemptId(attemptId);
        session.setTaskId(taskId);
        session.setDeviceId(deviceId);
        session.setRunId(runId);
        session.setArtifactType("screenshot");
        session.setFileName("screen.png");
        session.setMimeType("image/png");
        session.setDeclaredSizeBytes(100L);
        session.setObjectKey("artifacts/task-1/attempt-1/artifact-1/screen.png");
        session.setStatus(status);
        session.setUploadExpiresAt(Long.MAX_VALUE);
        session.setCreatedAt(1L);
        session.setUpdatedAt(1L);
        return session;
    }

    private ExecutorAuthContext authContext() {
        return new ExecutorAuthContext("device-1", "v1", System.currentTimeMillis(), "nonce-1", true);
    }
}
