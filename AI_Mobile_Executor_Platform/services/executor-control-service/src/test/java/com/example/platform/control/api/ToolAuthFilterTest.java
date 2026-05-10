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

class ToolAuthFilterTest {

    @Test
    void rejectsToolRequestsWithoutBearerToken() throws Exception {
        ControlProperties properties = new ControlProperties();
        properties.getAdmin().setAuthToken("secret-token");
        ToolAuthFilter filter = new ToolAuthFilter(properties, new ObjectMapper());
        FilterChain filterChain = mock(FilterChain.class);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/tools/catalog");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        assertTrue(response.getContentAsString().contains("TOOL_UNAUTHORIZED"));
        verifyNoInteractions(filterChain);
    }

    @Test
    void rejectsMcpRequestsWithoutBearerToken() throws Exception {
        ControlProperties properties = new ControlProperties();
        properties.getAdmin().setAuthToken("secret-token");
        ToolAuthFilter filter = new ToolAuthFilter(properties, new ObjectMapper());
        FilterChain filterChain = mock(FilterChain.class);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/mcp");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        assertTrue(response.getContentAsString().contains("TOOL_UNAUTHORIZED"));
        verifyNoInteractions(filterChain);
    }

    @Test
    void allowsToolRequestsWithMatchingBearerToken() throws Exception {
        ControlProperties properties = new ControlProperties();
        properties.getAdmin().setAuthToken("secret-token");
        ToolAuthFilter filter = new ToolAuthFilter(properties, new ObjectMapper());
        FilterChain filterChain = mock(FilterChain.class);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/tools/catalog");
        request.addHeader("Authorization", "Bearer secret-token");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        verify(filterChain).doFilter(request, response);
    }

    @Test
    void allowsMcpRequestsWithMatchingBearerToken() throws Exception {
        ControlProperties properties = new ControlProperties();
        properties.getAdmin().setAuthToken("secret-token");
        ToolAuthFilter filter = new ToolAuthFilter(properties, new ObjectMapper());
        FilterChain filterChain = mock(FilterChain.class);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/mcp");
        request.addHeader("Authorization", "Bearer secret-token");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        verify(filterChain).doFilter(request, response);
    }
}
