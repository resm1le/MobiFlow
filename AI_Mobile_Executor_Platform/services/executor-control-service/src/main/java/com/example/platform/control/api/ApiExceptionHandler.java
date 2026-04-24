package com.example.platform.control.api;

import jakarta.validation.ConstraintViolationException;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.validation.BindException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String, Object>> handleResponseStatus(ResponseStatusException exception) {
        HttpStatus status = HttpStatus.valueOf(exception.getStatusCode().value());
        return ResponseEntity.status(status).body(Map.of(
                "code", exception.getReason() == null ? status.name() : exception.getReason(),
                "message", exception.getReason() == null ? status.getReasonPhrase() : exception.getReason()
        ));
    }

    @ExceptionHandler({
            MethodArgumentNotValidException.class,
            BindException.class,
            ConstraintViolationException.class
    })
    public ResponseEntity<Map<String, Object>> handleValidation(Exception exception, HttpServletRequest request) {
        String code = resolveValidationCode(exception, request == null ? null : request.getRequestURI());
        return ResponseEntity.badRequest().body(Map.of(
                "code", code,
                "message", code
        ));
    }

    private String resolveValidationCode(Exception exception, String requestUri) {
        if (containsFieldMessage(exception, "PROFILE_PACKAGE_INVALID")) {
            return "PROFILE_PACKAGE_INVALID";
        }
        if (requestUri == null) {
            return "TASK_STATE_INVALID";
        }
        if (requestUri.startsWith("/api/devices/") && requestUri.endsWith("/commands")) {
            return "COMMAND_NOT_ALLOWED";
        }
        if (requestUri.startsWith("/api/devices/") && requestUri.endsWith("/resume")) {
            return "DEVICE_STATE_INVALID";
        }
        if (requestUri.startsWith("/api/attempts/")) {
            return "ATTEMPT_STATE_INVALID";
        }
        if (requestUri.startsWith("/api/ai/run-plans")) {
            return "AI_RUN_PLAN_INVALID";
        }
        if (requestUri.startsWith("/api/tasks")) {
            return "TASK_STATE_INVALID";
        }
        if (requestUri.startsWith("/executor/tasks/")) {
            return "ATTEMPT_STATE_INVALID";
        }
        if (requestUri.startsWith("/executor/")) {
            return "DEVICE_STATE_INVALID";
        }
        return "TASK_STATE_INVALID";
    }

    private boolean containsFieldMessage(Exception exception, String expectedMessage) {
        if (exception instanceof MethodArgumentNotValidException methodArgumentNotValidException) {
            return fieldErrors(methodArgumentNotValidException.getBindingResult().getFieldErrors(), expectedMessage);
        }
        if (exception instanceof BindException bindException) {
            return fieldErrors(bindException.getBindingResult().getFieldErrors(), expectedMessage);
        }
        return false;
    }

    private boolean fieldErrors(List<FieldError> errors, String expectedMessage) {
        return errors.stream()
                .map(FieldError::getDefaultMessage)
                .anyMatch(expectedMessage::equals);
    }
}
