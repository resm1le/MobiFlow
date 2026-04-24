package com.example.platform.control.api;

import com.example.platform.control.application.ControlProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class AdminAuthFilterTest {

    @Test
    void rejectsApiRequestsWithoutBearerToken() throws Exception {
        ControlProperties properties = new ControlProperties();
        properties.getAdmin().setAuthToken("secret-token");
        AdminAuthFilter filter = new AdminAuthFilter(properties, new ObjectMapper());
        FilterChain filterChain = mock(FilterChain.class);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/devices");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        assertTrue(response.getContentAsString().contains("ADMIN_UNAUTHORIZED"));
        verifyNoInteractions(filterChain);
    }

    @Test
    void allowsApiRequestsWithMatchingBearerToken() throws Exception {
        ControlProperties properties = new ControlProperties();
        properties.getAdmin().setAuthToken("secret-token");
        AdminAuthFilter filter = new AdminAuthFilter(properties, new ObjectMapper());
        FilterChain filterChain = mock(FilterChain.class);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/devices");
        request.addHeader("Authorization", "Bearer secret-token");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        verify(filterChain).doFilter(request, response);
    }
}
