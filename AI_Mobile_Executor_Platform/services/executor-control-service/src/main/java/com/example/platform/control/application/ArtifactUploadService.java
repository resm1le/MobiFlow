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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.time.Clock;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@Service
public class ArtifactUploadService {

    private static final Logger log = LoggerFactory.getLogger(ArtifactUploadService.class);
    private static final String STATUS_AUTHORIZED = "AUTHORIZED";
    private static final String STATUS_FINALIZED = "FINALIZED";
    private static final String STATUS_EXPIRED = "EXPIRED";
    private static final int CLEANUP_BATCH_SIZE = 100;

    private final AttemptAccessValidator attemptAccessValidator;
    private final ArtifactMapper artifactMapper;
    private final ArtifactUploadSessionMapper uploadSessionMapper;
    private final ArtifactObjectStore artifactObjectStore;
    private final ControlProperties controlProperties;
    private final Clock clock = Clock.systemUTC();

    public ArtifactUploadService(AttemptAccessValidator attemptAccessValidator,
                                 ArtifactMapper artifactMapper,
                                 ArtifactUploadSessionMapper uploadSessionMapper,
                                 ArtifactObjectStore artifactObjectStore,
                                 ControlProperties controlProperties) {
        this.attemptAccessValidator = attemptAccessValidator;
        this.artifactMapper = artifactMapper;
        this.uploadSessionMapper = uploadSessionMapper;
        this.artifactObjectStore = artifactObjectStore;
        this.controlProperties = controlProperties;
    }

    @Transactional
    public ArtifactUploadTicketResponse requestUploadTicket(ExecutorAuthContext authContext,
                                                            String attemptId,
                                                            ArtifactUploadTicketRequest request) {
        TaskAttemptEntity attempt = requireOwnedAttempt(authContext, attemptId);
        validateAttemptContext(attempt, request.taskId(), request.runId());

        ArtifactUploadSessionEntity session = uploadSessionMapper.findByArtifactId(request.artifactId());
        if (session == null) {
            session = new ArtifactUploadSessionEntity();
            session.setArtifactId(request.artifactId());
            session.setAttemptId(attemptId);
            session.setTaskId(attempt.getTaskId());
            session.setDeviceId(authContext.deviceId());
            session.setCreatedAt(clock.millis());
        } else {
            validateSessionShape(session, attempt, request.taskId(), request.runId(), request.artifactId());
            if (STATUS_FINALIZED.equals(session.getStatus())
                    || artifactMapper.findByAttemptIdAndArtifactId(attemptId, request.artifactId()) != null) {
                throw ControlApiExceptions.conflict(ControlErrorCode.ARTIFACT_UPLOAD_ALREADY_FINALIZED);
            }
        }

        long now = clock.millis();
        long expiresAt = now + controlProperties.getArtifacts().getUploadTicketTtlMs();
        String normalizedFileName = ArtifactObjectKeys.normalize(request.fileName());
        String objectKey = ArtifactObjectKeys.build(attempt.getTaskId(), attemptId, request.artifactId(), normalizedFileName);

        session.setRunId(request.runId());
        session.setArtifactType(request.artifactType());
        session.setFileName(normalizedFileName);
        session.setMimeType(normalizeMimeType(request.mimeType()));
        session.setDeclaredSizeBytes(request.sizeBytes());
        session.setObjectKey(objectKey);
        session.setStatus(STATUS_AUTHORIZED);
        session.setUploadExpiresAt(expiresAt);
        session.setFinalizedAt(null);
        session.setUpdatedAt(now);

        if (uploadSessionMapper.findByArtifactId(request.artifactId()) == null) {
            uploadSessionMapper.insert(session);
        } else {
            uploadSessionMapper.update(session);
        }

        ArtifactObjectStore.PresignedUpload presignedUpload = artifactObjectStore.presignPut(
                objectKey,
                session.getMimeType(),
                expiresAt
        );
        log.info("artifact.ticket_issued taskId={} attemptId={} deviceId={} artifactId={} mode={} expiresAt={}",
                attempt.getTaskId(),
                attemptId,
                authContext.deviceId(),
                request.artifactId(),
                ArtifactUploadMode.DIRECT_PUT_V2,
                expiresAt);
        return new ArtifactUploadTicketResponse(
                request.artifactId(),
                ArtifactUploadMode.DIRECT_PUT_V2,
                presignedUpload.uploadUrl(),
                "PUT",
                presignedUpload.requiredHeaders(),
                objectKey,
                presignedUpload.expiresAt()
        );
    }

    @Transactional
    public ArtifactUploadFinalizeResponse finalizeUpload(ExecutorAuthContext authContext,
                                                         String attemptId,
                                                         String artifactId,
                                                         ArtifactUploadFinalizeRequest request) {
        TaskAttemptEntity attempt = requireOwnedAttempt(authContext, attemptId);
        validateAttemptContext(attempt, request.taskId(), request.runId());

        ArtifactEntity existingArtifact = artifactMapper.findByAttemptIdAndArtifactId(attemptId, artifactId);
        if (existingArtifact != null) {
            return new ArtifactUploadFinalizeResponse(true, artifactId, existingArtifact.getSizeBytes());
        }

        ArtifactUploadSessionEntity session = uploadSessionMapper.findByArtifactId(artifactId);
        if (session == null || STATUS_EXPIRED.equals(session.getStatus()) || session.getUploadExpiresAt() < clock.millis()) {
            throw ControlApiExceptions.notFound(ControlErrorCode.ARTIFACT_UPLOAD_SESSION_NOT_FOUND);
        }
        validateSessionShape(session, attempt, request.taskId(), request.runId(), artifactId);
        if (STATUS_FINALIZED.equals(session.getStatus())) {
            throw ControlApiExceptions.conflict(ControlErrorCode.ARTIFACT_UPLOAD_ALREADY_FINALIZED);
        }

        ArtifactObjectStore.StoredObjectMetadata storedObject;
        try {
            storedObject = artifactObjectStore.stat(session.getObjectKey());
        } catch (ArtifactObjectMissingException exception) {
            throw ControlApiExceptions.notFound(ControlErrorCode.ARTIFACT_UPLOAD_OBJECT_MISSING);
        } catch (ResponseStatusException exception) {
            throw exception;
        } catch (ArtifactObjectStoreException exception) {
            throw ControlApiExceptions.internal(ControlErrorCode.ARTIFACT_UPLOAD_FAILED, exception);
        }

        ArtifactEntity artifact = new ArtifactEntity();
        artifact.setArtifactId(artifactId);
        artifact.setAttemptId(attemptId);
        artifact.setTaskId(session.getTaskId());
        artifact.setRunId(session.getRunId());
        artifact.setArtifactType(session.getArtifactType());
        artifact.setFileName(session.getFileName());
        artifact.setMimeType(normalizeMimeType(storedObject.contentType() == null ? session.getMimeType() : storedObject.contentType()));
        artifact.setSizeBytes(storedObject.sizeBytes());
        artifact.setObjectKey(session.getObjectKey());
        artifact.setCreatedAt(clock.millis());

        try {
            artifactMapper.insert(artifact);
        } catch (RuntimeException exception) {
            try {
                artifactObjectStore.delete(session.getObjectKey());
            } catch (RuntimeException cleanupException) {
                exception.addSuppressed(cleanupException);
            }
            throw ControlApiExceptions.internal(ControlErrorCode.ARTIFACT_UPLOAD_FAILED, exception);
        }
        uploadSessionMapper.markFinalized(artifactId, clock.millis(), clock.millis());
        log.info("artifact.finalized taskId={} attemptId={} deviceId={} artifactId={} sizeBytes={}",
                attempt.getTaskId(),
                attemptId,
                authContext.deviceId(),
                artifactId,
                artifact.getSizeBytes());
        return new ArtifactUploadFinalizeResponse(true, artifactId, artifact.getSizeBytes());
    }

    @Transactional
    public int cleanupExpiredUploads(long now) {
        List<ArtifactUploadSessionEntity> expired = uploadSessionMapper.findExpiredAuthorized(now, CLEANUP_BATCH_SIZE);
        int cleaned = 0;
        for (ArtifactUploadSessionEntity session : expired) {
            try {
                artifactObjectStore.delete(session.getObjectKey());
            } catch (RuntimeException exception) {
                log.warn("artifact.cleanup_delete_failed artifactId={} objectKey={}",
                        session.getArtifactId(),
                        session.getObjectKey(),
                        exception);
            }
            cleaned += uploadSessionMapper.markExpired(session.getArtifactId(), now);
        }
        if (cleaned > 0) {
            log.info("artifact.cleanup_expired count={}", cleaned);
        }
        return cleaned;
    }

    private TaskAttemptEntity requireOwnedAttempt(ExecutorAuthContext authContext, String attemptId) {
        return attemptAccessValidator.requireOwnedAttempt(authContext, attemptId);
    }

    private void validateAttemptContext(TaskAttemptEntity attempt, String taskId, String runId) {
        if (!Objects.equals(attempt.getTaskId(), taskId) || !Objects.equals(attempt.getRunId(), runId)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.ARTIFACT_UPLOAD_SESSION_MISMATCH);
        }
    }

    private void validateSessionShape(ArtifactUploadSessionEntity session,
                                      TaskAttemptEntity attempt,
                                      String taskId,
                                      String runId,
                                      String artifactId) {
        if (!Objects.equals(session.getArtifactId(), artifactId)
                || !Objects.equals(session.getAttemptId(), attempt.getAttemptId())
                || !Objects.equals(session.getTaskId(), taskId)
                || !Objects.equals(session.getDeviceId(), attempt.getDeviceId())
                || !Objects.equals(session.getRunId(), runId)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.ARTIFACT_UPLOAD_SESSION_MISMATCH);
        }
    }

    private String normalizeMimeType(String mimeType) {
        if (mimeType == null || mimeType.isBlank()) {
            return "application/octet-stream";
        }
        return mimeType;
    }
}
