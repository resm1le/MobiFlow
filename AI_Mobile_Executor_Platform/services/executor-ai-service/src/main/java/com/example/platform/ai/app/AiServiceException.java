package com.example.platform.ai.app;

import org.springframework.http.HttpStatus;

public class AiServiceException extends RuntimeException {

    private final String errorCode;
    private final HttpStatus status;

    public AiServiceException(String errorCode, HttpStatus status, String message) {
        super(message);
        this.errorCode = errorCode;
        this.status = status;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public HttpStatus getStatus() {
        return status;
    }

    public static AiServiceException requestInvalid(String message) {
        return new AiServiceException("REQUEST_INVALID", HttpStatus.BAD_REQUEST, message);
    }

    public static AiServiceException providerUnavailable(String message) {
        return new AiServiceException("PROVIDER_UNAVAILABLE", HttpStatus.SERVICE_UNAVAILABLE, message);
    }

    public static AiServiceException providerFailed(String message) {
        return new AiServiceException("PROVIDER_FAILED", HttpStatus.BAD_GATEWAY, message);
    }

    public static AiServiceException providerOutputInvalid(String message) {
        return new AiServiceException("PROVIDER_OUTPUT_INVALID", HttpStatus.BAD_GATEWAY, message);
    }
}
