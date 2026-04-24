package com.example.platform.ai.api;

import java.time.Instant;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    private final String serviceName;

    public HealthController(@Value("${spring.application.name:executor-ai-service}") String serviceName) {
        this.serviceName = serviceName;
    }

    @GetMapping("/internal/health")
    public Map<String, Object> health() {
        return Map.of(
                "service", serviceName,
                "status", "UP",
                "timestamp", Instant.now().toEpochMilli()
        );
    }
}
