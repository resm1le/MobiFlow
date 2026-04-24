package com.example.platform.control.application;

import io.minio.BucketExistsArgs;
import io.minio.GetObjectArgs;
import io.minio.GetObjectResponse;
import io.minio.GetPresignedObjectUrlArgs;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.RemoveObjectArgs;
import io.minio.StatObjectArgs;
import io.minio.StatObjectResponse;
import io.minio.errors.ErrorResponseException;
import io.minio.http.Method;

import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public class MinioArtifactObjectStore implements ArtifactObjectStore {

    private static final long UNKNOWN_SIZE = -1L;
    private static final long PART_SIZE = 10L * 1024L * 1024L;

    private final MinioClient minioClient;
    private final String bucket;

    public MinioArtifactObjectStore(MinioClient minioClient, String bucket) {
        this.minioClient = minioClient;
        this.bucket = bucket;
    }

    public void ensureBucket() {
        try {
            boolean exists = minioClient.bucketExists(
                    BucketExistsArgs.builder().bucket(bucket).build()
            );
            if (!exists) {
                minioClient.makeBucket(MakeBucketArgs.builder().bucket(bucket).build());
            }
        } catch (Exception exception) {
            throw new ArtifactObjectStoreException("Failed to initialize MinIO bucket", exception);
        }
    }

    @Override
    public long put(String objectKey, InputStream inputStream, String contentType) {
        try {
            CountingInputStream countingInputStream = new CountingInputStream(
                    inputStream == null ? InputStream.nullInputStream() : inputStream
            );
            minioClient.putObject(
                    PutObjectArgs.builder()
                            .bucket(bucket)
                            .object(objectKey)
                            .stream(countingInputStream, UNKNOWN_SIZE, PART_SIZE)
                            .contentType(contentType)
                            .build()
            );
            return countingInputStream.count();
        } catch (Exception exception) {
            throw new ArtifactObjectStoreException("Failed to upload artifact object", exception);
        }
    }

    @Override
    public PresignedUpload presignPut(String objectKey, String contentType, long expiresAt) {
        try {
            long ttlMillis = Math.max(1000L, expiresAt - System.currentTimeMillis());
            int expirySeconds = (int) Math.max(1L, TimeUnit.MILLISECONDS.toSeconds(ttlMillis));
            Map<String, String> requiredHeaders = Map.of("Content-Type", contentType);
            String url = minioClient.getPresignedObjectUrl(
                    GetPresignedObjectUrlArgs.builder()
                            .method(Method.PUT)
                            .bucket(bucket)
                            .object(objectKey)
                            .expiry(expirySeconds)
                            .extraHeaders(requiredHeaders)
                            .build()
            );
            return new PresignedUpload(url, requiredHeaders, expiresAt);
        } catch (Exception exception) {
            throw new ArtifactObjectStoreException("Failed to presign artifact upload", exception);
        }
    }

    @Override
    public StoredObjectMetadata stat(String objectKey) {
        try {
            StatObjectResponse response = minioClient.statObject(
                    StatObjectArgs.builder()
                            .bucket(bucket)
                            .object(objectKey)
                            .build()
            );
            return new StoredObjectMetadata(response.size(), response.contentType(), response.etag());
        } catch (ErrorResponseException exception) {
            String code = exception.errorResponse() == null ? null : exception.errorResponse().code();
            if ("NoSuchKey".equals(code) || "NoSuchObject".equals(code)) {
                throw new ArtifactObjectMissingException("Artifact object missing: " + objectKey, exception);
            }
            throw new ArtifactObjectStoreException("Failed to stat artifact object", exception);
        } catch (Exception exception) {
            throw new ArtifactObjectStoreException("Failed to stat artifact object", exception);
        }
    }

    @Override
    public InputStream open(String objectKey) {
        try {
            GetObjectResponse response = minioClient.getObject(
                    GetObjectArgs.builder()
                            .bucket(bucket)
                            .object(objectKey)
                            .build()
            );
            return response;
        } catch (ErrorResponseException exception) {
            String code = exception.errorResponse() == null ? null : exception.errorResponse().code();
            if ("NoSuchKey".equals(code) || "NoSuchObject".equals(code)) {
                throw new ArtifactObjectMissingException("Artifact object missing: " + objectKey, exception);
            }
            throw new ArtifactObjectStoreException("Failed to open artifact object", exception);
        } catch (Exception exception) {
            throw new ArtifactObjectStoreException("Failed to open artifact object", exception);
        }
    }

    @Override
    public void delete(String objectKey) {
        try {
            minioClient.removeObject(
                    RemoveObjectArgs.builder()
                            .bucket(bucket)
                            .object(objectKey)
                            .build()
            );
        } catch (ErrorResponseException exception) {
            String code = exception.errorResponse() == null ? null : exception.errorResponse().code();
            if ("NoSuchKey".equals(code) || "NoSuchObject".equals(code)) {
                return;
            }
            throw new ArtifactObjectStoreException("Failed to delete artifact object", exception);
        } catch (Exception exception) {
            throw new ArtifactObjectStoreException("Failed to delete artifact object", exception);
        }
    }

    private static final class CountingInputStream extends FilterInputStream {
        private long count;

        private CountingInputStream(InputStream in) {
            super(in);
        }

        @Override
        public int read() throws IOException {
            int value = super.read();
            if (value >= 0) {
                count++;
            }
            return value;
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            int read = super.read(b, off, len);
            if (read > 0) {
                count += read;
            }
            return read;
        }

        private long count() {
            return count;
        }
    }
}
