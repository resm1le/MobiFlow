package com.example.platform.control.application;

import io.minio.MinioClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

@Configuration
public class ArtifactStorageConfiguration {

    @Bean
    ArtifactObjectStore artifactObjectStore(ControlProperties properties) {
        String backend = properties.getArtifacts().getBackend();
        if (backend == null || backend.isBlank() || "disabled".equalsIgnoreCase(backend)) {
            return new DisabledArtifactObjectStore();
        }
        if (!"minio".equalsIgnoreCase(backend)) {
            throw new IllegalStateException("Unsupported artifact storage backend: " + backend);
        }

        ControlProperties.Minio minio = properties.getArtifacts().getMinio();
        if (isBlank(minio.getEndpoint()) || isBlank(minio.getAccessKey())
                || isBlank(minio.getSecretKey()) || isBlank(minio.getBucket())) {
            throw new IllegalStateException("MinIO artifact storage configuration is incomplete");
        }

        MinioArtifactObjectStore store = new MinioArtifactObjectStore(
                MinioClient.builder()
                        .endpoint(minio.getEndpoint())
                        .credentials(minio.getAccessKey(), minio.getSecretKey())
                        .build(),
                minio.getBucket()
        );
        store.ensureBucket();
        return store;
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static final class DisabledArtifactObjectStore implements ArtifactObjectStore {

        @Override
        public long put(String objectKey, java.io.InputStream inputStream, String contentType) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "ARTIFACT_STORAGE_DISABLED");
        }

        @Override
        public PresignedUpload presignPut(String objectKey, String contentType, long expiresAt) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "ARTIFACT_STORAGE_DISABLED");
        }

        @Override
        public StoredObjectMetadata stat(String objectKey) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "ARTIFACT_STORAGE_DISABLED");
        }

        @Override
        public java.io.InputStream open(String objectKey) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "ARTIFACT_STORAGE_DISABLED");
        }

        @Override
        public void delete(String objectKey) {
        }
    }
}
