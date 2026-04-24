package com.example.platform.control.api;

import com.example.platform.control.application.ControlErrorCode;
import com.example.platform.control.application.ControlProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

@Component
public class ToolAuthFilter extends OncePerRequestFilter {

    private final ControlProperties controlProperties;
    private final ObjectMapper objectMapper;

    public ToolAuthFilter(ControlProperties controlProperties, ObjectMapper objectMapper) {
        this.controlProperties = controlProperties;
        this.objectMapper = objectMapper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/tools/")
                || "OPTIONS".equalsIgnoreCase(request.getMethod());
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String configuredToken = controlProperties.getAdmin().getAuthToken();
        String authorization = request.getHeader("Authorization");
        String bearerToken = extractBearerToken(authorization);
        if (configuredToken == null
                || configuredToken.isBlank()
                || bearerToken == null
                || !MessageDigest.isEqual(
                configuredToken.getBytes(StandardCharsets.UTF_8),
                bearerToken.getBytes(StandardCharsets.UTF_8))) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            objectMapper.writeValue(response.getWriter(), Map.of(
                    "code", ControlErrorCode.TOOL_UNAUTHORIZED,
                    "message", ControlErrorCode.TOOL_UNAUTHORIZED
            ));
            return;
        }
        filterChain.doFilter(request, response);
    }

    private String extractBearerToken(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            return null;
        }
        String token = authorization.substring("Bearer ".length()).trim();
        return token.isEmpty() ? null : token;
    }
}
