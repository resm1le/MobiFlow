package com.example.platform.control.application;

public final class ArtifactObjectKeys {

    private ArtifactObjectKeys() {
    }

    public static String build(String taskId, String attemptId, String artifactId, String fileName) {
        return "artifacts/" + taskId + "/" + attemptId + "/" + artifactId + "/" + sanitize(normalize(fileName));
    }

    public static String normalize(String fileName) {
        if (fileName == null || fileName.isBlank()) {
            return "artifact.bin";
        }
        return fileName;
    }

    public static String sanitize(String fileName) {
        String sanitized = fileName
                .replace("\\", "_")
                .replace("/", "_")
                .replaceAll("[\\r\\n\\t]+", "_")
                .replaceAll("[^A-Za-z0-9._-]", "_");
        return sanitized.isBlank() ? "artifact.bin" : sanitized;
    }
}
