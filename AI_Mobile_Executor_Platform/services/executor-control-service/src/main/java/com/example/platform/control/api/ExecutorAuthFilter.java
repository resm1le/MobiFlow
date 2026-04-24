package com.example.platform.control.api;

import com.example.platform.control.application.ExecutorAuthService;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StreamUtils;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

@Component
public class ExecutorAuthFilter extends OncePerRequestFilter {

    private final ExecutorAuthService executorAuthService;
    private final ObjectMapper objectMapper;

    public ExecutorAuthFilter(ExecutorAuthService executorAuthService, ObjectMapper objectMapper) {
        this.executorAuthService = executorAuthService;
        this.objectMapper = objectMapper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/executor/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        if (isRemovedArtifactUploadRoute(request)) {
            filterChain.doFilter(request, response);
            return;
        }
        byte[] body = StreamUtils.copyToByteArray(request.getInputStream());
        CachedBodyHttpServletRequest wrappedRequest = new CachedBodyHttpServletRequest(request, body);

        try {
            ExecutorAuthContext context = executorAuthService.authenticate(
                    request.getMethod(),
                    request.getRequestURI(),
                    request.getHeader(ExecutorAuthService.HEADER_DEVICE_ID),
                    request.getHeader(ExecutorAuthService.HEADER_PROTOCOL_VERSION),
                    request.getHeader(ExecutorAuthService.HEADER_TIMESTAMP),
                    request.getHeader(ExecutorAuthService.HEADER_NONCE),
                    request.getHeader(ExecutorAuthService.HEADER_SIGNATURE),
                    body
            );
            wrappedRequest.setAttribute(ExecutorAuthContext.REQUEST_ATTRIBUTE, context);
        } catch (ResponseStatusException exception) {
            writeError(response, exception);
            return;
        }
        filterChain.doFilter(wrappedRequest, response);
    }

    private boolean isRemovedArtifactUploadRoute(HttpServletRequest request) {
        if (!"POST".equalsIgnoreCase(request.getMethod())) {
            return false;
        }
        String uri = request.getRequestURI();
        return uri.startsWith("/executor/tasks/")
                && uri.endsWith("/artifacts")
                && !uri.endsWith("/artifacts/uploads");
    }

    private void writeError(HttpServletResponse response, ResponseStatusException exception) throws IOException {
        int statusCode = exception.getStatusCode().value();
        String code = exception.getReason() == null ? "EXECUTOR_AUTH_FAILED" : exception.getReason();
        response.setStatus(statusCode);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        objectMapper.writeValue(response.getWriter(), Map.of(
                "code", code,
                "message", code
        ));
    }
}
