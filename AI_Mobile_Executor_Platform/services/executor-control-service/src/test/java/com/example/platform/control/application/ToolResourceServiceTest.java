package com.example.platform.control.application;

import com.example.platform.control.api.AdminApiModels;
import com.example.platform.control.api.ToolApiModels;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ToolResourceServiceTest {

    private AdminApiService adminApiService;
    private ToolResourceService toolResourceService;

    @BeforeEach
    void setUp() {
        adminApiService = mock(AdminApiService.class);
        toolResourceService = new ToolResourceService(adminApiService, new ObjectMapper());
    }

    @Test
    void createAttemptArtifactHandleAndReadJsonContent() {
        AdminApiModels.ArtifactResponse artifact = new AdminApiModels.ArtifactResponse(
                "artifact-1",
                "attempt-1",
                "task-1",
                "run-1",
                "LOG",
                "result.json",
                "application/json",
                16L,
                "obj",
                "/api/attempts/attempt-1/artifacts/artifact-1/download",
                1L
        );
        ToolApiModels.ResourceHandle handle = toolResourceService.createAttemptArtifactHandle(artifact);
        when(adminApiService.downloadAttemptArtifact("attempt-1", "artifact-1")).thenReturn(
                new AdminApiService.ArtifactDownload(
                        "result.json",
                        "application/json",
                        new ByteArrayInputStream("{\"ok\":true}".getBytes(StandardCharsets.UTF_8))
                )
        );

        ToolApiModels.ReadResourceResponse response = toolResourceService.read(handle.handle());

        assertEquals("attempt_artifact", response.kind());
        assertEquals(true, ((java.util.Map<?, ?>) response.content()).get("ok"));
    }

    @Test
    void rejectsInvalidHandle() {
        assertThrows(org.springframework.web.server.ResponseStatusException.class, () ->
                toolResourceService.read("bad-handle")
        );
    }
}
