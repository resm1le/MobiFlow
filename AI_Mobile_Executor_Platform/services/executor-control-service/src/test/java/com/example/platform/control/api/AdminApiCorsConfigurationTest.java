package com.example.platform.control.api;

import com.example.platform.control.application.ControlProperties;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.servlet.config.annotation.CorsRegistration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class AdminApiCorsConfigurationTest {

    @Test
    void addsConfiguredOriginsForAdminApiRoutes() {
        ControlProperties properties = new ControlProperties();
        properties.getConsole().setAllowedOrigins(List.of(
                "http://127.0.0.1:5173",
                "http://localhost:5173"
        ));
        AdminApiCorsConfiguration configuration = new AdminApiCorsConfiguration(properties);
        CorsRegistry registry = new CorsRegistry();

        configuration.addCorsMappings(registry);

        @SuppressWarnings("unchecked")
        List<CorsRegistration> registrations = (List<CorsRegistration>) ReflectionTestUtils.getField(registry, "registrations");
        assertThat(registrations).hasSize(1);

        CorsRegistration registration = registrations.get(0);
        assertThat(ReflectionTestUtils.getField(registration, "pathPattern")).isEqualTo("/api/**");

        CorsConfiguration corsConfiguration =
                (CorsConfiguration) ReflectionTestUtils.getField(registration, "config");
        assertThat(corsConfiguration).isNotNull();
        assertThat(corsConfiguration.getAllowedOrigins()).containsExactly(
                "http://127.0.0.1:5173",
                "http://localhost:5173"
        );
        assertThat(corsConfiguration.getAllowedMethods()).containsExactly("GET", "POST", "OPTIONS");
        assertThat(corsConfiguration.getAllowedHeaders()).containsExactly("*");
        assertThat(corsConfiguration.getMaxAge()).isEqualTo(3600L);
    }
}
