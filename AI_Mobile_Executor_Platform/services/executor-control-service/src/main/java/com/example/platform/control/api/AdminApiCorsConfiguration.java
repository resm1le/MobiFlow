package com.example.platform.control.api;

import com.example.platform.control.application.ControlProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AdminApiCorsConfiguration implements WebMvcConfigurer {

    private final ControlProperties controlProperties;

    public AdminApiCorsConfiguration(ControlProperties controlProperties) {
        this.controlProperties = controlProperties;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        var allowedOrigins = controlProperties.getConsole().getAllowedOrigins();
        if (allowedOrigins == null || allowedOrigins.isEmpty()) {
            return;
        }
        registry.addMapping("/api/**")
                .allowedOrigins(allowedOrigins.toArray(String[]::new))
                .allowedMethods("GET", "POST", "OPTIONS")
                .allowedHeaders("*")
                .maxAge(3600);
    }
}
