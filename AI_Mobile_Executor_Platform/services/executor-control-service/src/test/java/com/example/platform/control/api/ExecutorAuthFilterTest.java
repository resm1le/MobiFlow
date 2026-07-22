package com.example.platform.control.api;

import com.example.platform.control.application.ExecutorAuthService;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ExecutorAuthFilterTest {

    @Test
    void waypointEvidenceRouteRequiresExecutorAuthentication() throws Exception {
        ExecutorAuthService executorAuthService = mock(ExecutorAuthService.class);
        ExecutorAuthFilter filter = new ExecutorAuthFilter(executorAuthService, new ObjectMapper());
        FilterChain filterChain = mock(FilterChain.class);
        MockHttpServletRequest request = new MockHttpServletRequest(
                "POST", "/executor/tasks/attempt-1/waypoint-segments");
        request.setContent("{\"waypointSegments\":[]}".getBytes());
        MockHttpServletResponse response = new MockHttpServletResponse();
        ExecutorAuthContext context = new ExecutorAuthContext(
                "device-1", "v1", 1000L, "nonce-1", true);
        when(executorAuthService.authenticate(
                anyString(), anyString(), any(), any(), any(), any(), any(), any()
        )).thenReturn(context);

        filter.doFilter(request, response, filterChain);

        verify(executorAuthService).authenticate(
                anyString(), anyString(), any(), any(), any(), any(), any(), any()
        );
        verify(filterChain).doFilter(any(), any());
    }

    @Test
    void removedArtifactUploadRouteSkipsExecutorAuthentication() throws Exception {
        ExecutorAuthService executorAuthService = mock(ExecutorAuthService.class);
        ExecutorAuthFilter filter = new ExecutorAuthFilter(executorAuthService, new ObjectMapper());
        FilterChain filterChain = mock(FilterChain.class);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/executor/tasks/attempt-1/artifacts");
        request.setContent("legacy-body".getBytes());
        request.setParameter("artifactType", "run_log");
        request.setParameter("fileName", "run.log");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        verify(executorAuthService, never()).authenticate(
                anyString(),
                anyString(),
                any(),
                any(),
                any(),
                any(),
                any(),
                any()
        );
        verify(filterChain).doFilter(request, response);
    }
}
