package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels;
import com.example.platform.control.api.ToolApiModels;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

@Service
public class ToolResourceService {

    private static final String HANDLE_PREFIX = "rh_";
    private static final String KIND_ATTEMPT_ARTIFACT = "attempt_artifact";

    private final AdminApiService adminApiService;
    private final ObjectMapper objectMapper;

    public ToolResourceService(AdminApiService adminApiService, ObjectMapper objectMapper) {
        this.adminApiService = adminApiService;
        this.objectMapper = objectMapper;
    }

    public ToolApiModels.ResourceHandle createAttemptArtifactHandle(AdminApiModels.ArtifactResponse artifact) {
        ResourceDescriptor descriptor = new ResourceDescriptor(
                KIND_ATTEMPT_ARTIFACT,
                artifact.attemptId(),
                artifact.artifactId(),
                artifact.mimeType(),
                artifact.sizeBytes(),
                artifact.fileName(),
                artifact.fileName()
        );
        return new ToolApiModels.ResourceHandle(
                encode(descriptor),
                descriptor.kind(),
                descriptor.mimeType(),
                descriptor.sizeBytes(),
                descriptor.fileName(),
                descriptor.title()
        );
    }

    public ToolApiModels.ReadResourceResponse read(String handle) {
        ResourceDescriptor descriptor = decode(handle);
        if (!isReadableMimeType(descriptor.mimeType())) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_RESOURCE_NOT_READABLE);
        }
        AdminApiService.ArtifactDownload artifact = openArtifact(descriptor);
        try (InputStream inputStream = artifact.inputStream()) {
            byte[] bytes = inputStream.readAllBytes();
            Object content = parseContent(bytes, descriptor.mimeType());
            return new ToolApiModels.ReadResourceResponse(
                    handle,
                    descriptor.kind(),
                    descriptor.mimeType(),
                    descriptor.title(),
                    content
            );
        } catch (IOException exception) {
            throw ControlApiExceptions.internal(ControlErrorCode.ARTIFACT_DOWNLOAD_FAILED, exception);
        }
    }

    public ToolResourceDownload download(String handle) {
        ResourceDescriptor descriptor = decode(handle);
        AdminApiService.ArtifactDownload artifact = openArtifact(descriptor);
        return new ToolResourceDownload(artifact.fileName(), artifact.mimeType(), artifact.inputStream());
    }

    private AdminApiService.ArtifactDownload openArtifact(ResourceDescriptor descriptor) {
        if (!KIND_ATTEMPT_ARTIFACT.equals(descriptor.kind())) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_RESOURCE_INVALID);
        }
        try {
            return adminApiService.downloadAttemptArtifact(descriptor.attemptId(), descriptor.resourceId());
        } catch (org.springframework.web.server.ResponseStatusException exception) {
            if (HttpStatus.NOT_FOUND.value() == exception.getStatusCode().value()) {
                throw ControlApiExceptions.notFound(ControlErrorCode.TOOL_RESOURCE_NOT_FOUND);
            }
            throw exception;
        }
    }

    private Object parseContent(byte[] bytes, String mimeType) throws IOException {
        if (isJsonMimeType(mimeType)) {
            return objectMapper.readValue(bytes, Object.class);
        }
        return new String(bytes, StandardCharsets.UTF_8);
    }

    private boolean isReadableMimeType(String mimeType) {
        return mimeType != null
                && (mimeType.startsWith("text/")
                || isJsonMimeType(mimeType)
                || "application/xml".equalsIgnoreCase(mimeType)
                || "text/xml".equalsIgnoreCase(mimeType));
    }

    private boolean isJsonMimeType(String mimeType) {
        return "application/json".equalsIgnoreCase(mimeType)
                || (mimeType != null && mimeType.endsWith("+json"));
    }

    private String encode(ResourceDescriptor descriptor) {
        try {
            String json = objectMapper.writeValueAsString(descriptor);
            String encoded = Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(json.getBytes(StandardCharsets.UTF_8));
            return HANDLE_PREFIX + encoded;
        } catch (JsonProcessingException exception) {
            throw ControlApiExceptions.internal("JSON_SERIALIZATION_FAILED", exception);
        }
    }

    private ResourceDescriptor decode(String handle) {
        if (handle == null || handle.isBlank() || !handle.startsWith(HANDLE_PREFIX)) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_RESOURCE_INVALID);
        }
        try {
            byte[] decoded = Base64.getUrlDecoder().decode(handle.substring(HANDLE_PREFIX.length()));
            ResourceDescriptor descriptor = objectMapper.readValue(decoded, ResourceDescriptor.class);
            if (descriptor.kind() == null || descriptor.resourceId() == null || descriptor.attemptId() == null) {
                throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_RESOURCE_INVALID);
            }
            return descriptor;
        } catch (IllegalArgumentException | IOException exception) {
            throw ControlApiExceptions.badRequest(ControlErrorCode.TOOL_RESOURCE_INVALID);
        }
    }

    private record ResourceDescriptor(
            String kind,
            String attemptId,
            String resourceId,
            String mimeType,
            long sizeBytes,
            String fileName,
            String title
    ) {
    }

    public record ToolResourceDownload(
            String fileName,
            String mimeType,
            InputStream inputStream
    ) {
    }
}
