package com.example.platform.control.application;

public class ArtifactObjectMissingException extends ArtifactObjectStoreException {

    public ArtifactObjectMissingException(String message, Throwable cause) {
        super(message, cause);
    }

    public ArtifactObjectMissingException(String message) {
        super(message);
    }
}
