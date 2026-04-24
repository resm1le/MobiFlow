package com.example.platform.ai.error;

import com.example.platform.ai.app.AiServiceException;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handleValidation(MethodArgumentNotValidException exception) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("error", "REQUEST_VALIDATION_FAILED");
        body.put("message", "Request validation failed");
        body.put("status", HttpStatus.BAD_REQUEST.value());
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, Object>> handleUnreadableBody(HttpMessageNotReadableException exception) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("error", "REQUEST_BODY_INVALID");
        body.put("message", "Request body could not be parsed");
        body.put("status", HttpStatus.BAD_REQUEST.value());
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(AiServiceException.class)
    public ResponseEntity<Map<String, Object>> handleAiServiceException(AiServiceException exception) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("error", exception.getErrorCode());
        body.put("message", exception.getMessage());
        body.put("status", exception.getStatus().value());
        return ResponseEntity.status(exception.getStatus()).body(body);
    }
}
