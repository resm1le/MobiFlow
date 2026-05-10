package com.example.platform.control.application;

import com.example.platform.control.api.McpApiModels;
import com.example.platform.control.api.ToolApiModels;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class McpFacadeServiceTest {

    @Test
    void toolsListMapsCatalogAndVirtualTools() {
        ToolFacadeService toolFacadeService = mock(ToolFacadeService.class);
        ToolResourceService resourceService = mock(ToolResourceService.class);
        when(toolFacadeService.catalog()).thenReturn(new ToolApiModels.ToolCatalogResponse(
                "tool-envelope-v2",
                List.of(new ToolApiModels.ToolCatalogItem(
                        "list_devices",
                        "List Devices",
                        "List devices.",
                        Map.of("type", "object"),
                        Map.of("type", "array"),
                        "inline",
                        "stable",
                        "read",
                        "DISCOVERY",
                        new ToolApiModels.ToolGovernance(false, null),
                        List.of("observation")
                ))
        ));
        McpFacadeService service = new McpFacadeService(toolFacadeService, resourceService, new ObjectMapper());

        McpApiModels.JsonRpcResponse response = service.handle(new McpApiModels.JsonRpcRequest(
                "2.0",
                "1",
                "tools/list",
                Map.of()
        ));

        assertNull(response.error());
        Map<?, ?> result = (Map<?, ?>) response.result();
        List<?> tools = (List<?>) result.get("tools");
        assertEquals(3, tools.size());
        Map<?, ?> first = (Map<?, ?>) tools.get(0);
        assertEquals("list_devices", first.get("name"));
        assertEquals(Map.of("type", "object"), first.get("inputSchema"));
        assertTrue(tools.stream().anyMatch(item -> ((Map<?, ?>) item).get("name").equals("resolve_confirmation")));
        assertTrue(tools.stream().anyMatch(item -> ((Map<?, ?>) item).get("name").equals("query_audits")));
    }

    @Test
    void toolsCallDelegatesExecuteAndReturnsStructuredContent() {
        ToolFacadeService toolFacadeService = mock(ToolFacadeService.class);
        ToolResourceService resourceService = mock(ToolResourceService.class);
        when(toolFacadeService.execute(any())).thenReturn(new ToolApiModels.ExecuteToolResponse(
                "tool-envelope-v2",
                "req-1",
                "session-1",
                "list_devices",
                "completed",
                List.of(Map.of("deviceId", "device-1")),
                List.of(),
                null,
                new ToolApiModels.ToolAudit("audit-1", "DISCOVERY"),
                new ToolApiModels.EntityRefs(null, null, null, null, null, List.of()),
                null
        ));
        McpFacadeService service = new McpFacadeService(toolFacadeService, resourceService, new ObjectMapper());

        McpApiModels.JsonRpcResponse response = service.handle(new McpApiModels.JsonRpcRequest(
                "2.0",
                "2",
                "tools/call",
                Map.of(
                        "name", "list_devices",
                        "requestId", "req-1",
                        "sessionId", "session-1",
                        "arguments", Map.of(),
                        "callerContext", Map.of("agentTaskId", "task-1", "turnId", "turn-1", "stepId", "step-1")
                )
        ));

        assertNull(response.error());
        Map<?, ?> result = (Map<?, ?>) response.result();
        assertFalse((Boolean) result.get("isError"));
        ToolApiModels.ExecuteToolResponse content =
                (ToolApiModels.ExecuteToolResponse) result.get("structuredContent");
        assertEquals("completed", content.status());
        assertEquals("audit-1", content.audit().auditId());
    }

    @Test
    void resolveConfirmationIsExposedAsToolCall() {
        ToolFacadeService toolFacadeService = mock(ToolFacadeService.class);
        ToolResourceService resourceService = mock(ToolResourceService.class);
        when(toolFacadeService.resolveConfirmation(any())).thenReturn(new ToolApiModels.ExecuteToolResponse(
                "tool-envelope-v2",
                "req-side",
                "session-1",
                "create_run",
                "completed",
                Map.of("runId", "run-1"),
                List.of(),
                null,
                new ToolApiModels.ToolAudit("audit-2", "EXECUTION"),
                new ToolApiModels.EntityRefs(null, "run-1", null, null, null, List.of()),
                null
        ));
        McpFacadeService service = new McpFacadeService(toolFacadeService, resourceService, new ObjectMapper());

        McpApiModels.JsonRpcResponse response = service.handle(new McpApiModels.JsonRpcRequest(
                "2.0",
                "3",
                "tools/call",
                Map.of(
                        "name", "resolve_confirmation",
                        "sessionId", "session-1",
                        "arguments", Map.of("confirmationId", "confirm-1", "decision", "approve"),
                        "callerContext", Map.of("agentTaskId", "task-1", "turnId", "turn-1", "stepId", "step-1")
                )
        ));

        assertNull(response.error());
        Map<?, ?> result = (Map<?, ?>) response.result();
        ToolApiModels.ExecuteToolResponse content =
                (ToolApiModels.ExecuteToolResponse) result.get("structuredContent");
        assertEquals("completed", content.status());
        assertNotNull(content.audit());
    }

    @Test
    void resourcesReadMapsMobiflowResourceUri() {
        ToolFacadeService toolFacadeService = mock(ToolFacadeService.class);
        ToolResourceService resourceService = mock(ToolResourceService.class);
        when(resourceService.read("rh_1")).thenReturn(new ToolApiModels.ReadResourceResponse(
                "rh_1",
                "attempt_artifact",
                "application/json",
                "artifact.json",
                Map.of("ok", true)
        ));
        McpFacadeService service = new McpFacadeService(toolFacadeService, resourceService, new ObjectMapper());

        McpApiModels.JsonRpcResponse response = service.handle(new McpApiModels.JsonRpcRequest(
                "2.0",
                "4",
                "resources/read",
                Map.of("uri", "mobiflow://resource/rh_1")
        ));

        assertNull(response.error());
        Map<?, ?> result = (Map<?, ?>) response.result();
        List<?> contents = (List<?>) result.get("contents");
        Map<?, ?> content = (Map<?, ?>) contents.get(0);
        assertEquals("application/json", content.get("mimeType"));
        assertEquals("{\"ok\":true}", content.get("text"));
    }
}
