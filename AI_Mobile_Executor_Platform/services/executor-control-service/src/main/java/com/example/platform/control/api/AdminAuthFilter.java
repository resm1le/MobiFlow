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
public class AdminAuthFilter extends OncePerRequestFilter {

    private final ControlProperties controlProperties;
    private final ObjectMapper objectMapper;

    public AdminAuthFilter(ControlProperties controlProperties, ObjectMapper objectMapper) {
        this.controlProperties = controlProperties;
        this.objectMapper = objectMapper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/api/")
                || "OPTIONS".equalsIgnoreCase(request.getMethod());
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String configuredToken = controlProperties.getAdmin().getAuthToken();
        String authorization = request.getHeader("Authorization");
        String bearerToken = extractBearerToken(authorization);
        if (configuredToken == null
                || configuredToken.isBlank()
                || bearerToken == null
                || !MessageDigest.isEqual(
                configuredToken.getBytes(StandardCharsets.UTF_8),
                bearerToken.getBytes(StandardCharsets.UTF_8))) {
            writeUnauthorized(response, request);
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

    private void writeUnauthorized(HttpServletResponse response, HttpServletRequest request) throws IOException {
        String origin = request.getHeader("Origin");
        if (origin != null && controlProperties.getConsole().getAllowedOrigins().contains(origin)) {
            response.setHeader("Access-Control-Allow-Origin", origin);
            response.setHeader("Vary", "Origin");
            response.setHeader("Access-Control-Allow-Credentials", "true");
        }
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        objectMapper.writeValue(response.getWriter(), Map.of(
                "code", ControlErrorCode.ADMIN_UNAUTHORIZED,
                "message", ControlErrorCode.ADMIN_UNAUTHORIZED
        ));
    }
}
