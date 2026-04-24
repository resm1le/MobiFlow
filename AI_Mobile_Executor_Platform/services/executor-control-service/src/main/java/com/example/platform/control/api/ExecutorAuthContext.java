package com.example.platform.control.api;

import com.example.platform.control.application.ControlApiExceptions;
import com.example.platform.control.application.ControlErrorCode;
import jakarta.servlet.http.HttpServletRequest;

public record ExecutorAuthContext(
        String deviceId,
        String protocolVersion,
        long timestamp,
        String nonce,
        boolean authConfigured
) {
    public static final String REQUEST_ATTRIBUTE = ExecutorAuthContext.class.getName();

    public static ExecutorAuthContext required(HttpServletRequest request) {
        Object value = request.getAttribute(REQUEST_ATTRIBUTE);
        if (value instanceof ExecutorAuthContext context) {
            return context;
        }
        throw ControlApiExceptions.unauthorized(ControlErrorCode.EXECUTOR_UNAUTHORIZED);
    }
}
