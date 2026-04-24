package com.example.platform.control.application;

import java.io.InputStream;
import java.util.Map;

public interface ArtifactObjectStore {

    record PresignedUpload(String uploadUrl, Map<String, String> requiredHeaders, long expiresAt) {
    }

    record StoredObjectMetadata(long sizeBytes, String contentType, String etag) {
    }

    long put(String objectKey, InputStream inputStream, String contentType);

    PresignedUpload presignPut(String objectKey, String contentType, long expiresAt);

    StoredObjectMetadata stat(String objectKey);

    InputStream open(String objectKey);

    void delete(String objectKey);
}
