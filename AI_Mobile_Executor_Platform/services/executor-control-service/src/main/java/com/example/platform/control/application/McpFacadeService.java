package com.example.platform.control.application;

import com.example.platform.control.api.McpApiModels;
import com.example.platform.control.api.ToolApiModels;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class McpFacadeService {

    static final String JSONRPC_VERSION = "2.0";
    static final String MCP_PROTOCOL_VERSION = "2025-06-18";
    static final String DEFAULT_SESSION_ID = "mobiflow-mcp-agent";

    private static final int ERROR_METHOD_NOT_FOUND = -32601;
    private static final int ERROR_INVALID_PARAMS = -32602;
    private static final int ERROR_INTERNAL = -32603;

    private final ToolFacadeService toolFacadeService;
    private final ToolResourceService toolResourceService;
    private final ObjectMapper objectMapper;

    public McpFacadeService(ToolFacadeService toolFacadeService,
                            ToolResourceService toolResourceService,
                            ObjectMapper objectMapper) {
        this.toolFacadeService = toolFacadeService;
        this.toolResourceService = toolResourceService;
        this.objectMapper = objectMapper;
    }

    public McpApiModels.JsonRpcResponse handle(McpApiModels.JsonRpcRequest request) {
        if (request == null || request.method() == null || request.method().isBlank()) {
            return error(null, ERROR_INVALID_PARAMS, "JSON-RPC method is required.", null);
        }
        try {
            Object result = switch (request.method()) {
                case "initialize" -> initialize();
                case "tools/list" -> toolsList();
                case "tools/call" -> toolsCall(request);
                case "resources/read" -> resourcesRead(request);
                default -> null;
            };
            if (result == null) {
                return error(request.id(), ERROR_METHOD_NOT_FOUND, "Unsupported MCP method: " + request.method(), null);
            }
            return new McpApiModels.JsonRpcResponse(JSONRPC_VERSION, request.id(), result, null);
        } catch (IllegalArgumentException exception) {
            return error(request.id(), ERROR_INVALID_PARAMS, exception.getMessage(), null);
        } catch (Exception exception) {
            return error(request.id(), ERROR_INTERNAL, "MCP facade failed.", exception.getClass().getSimpleName());
        }
    }

    private Map<String, Object> initialize() {
        return Map.of(
                "protocolVersion", MCP_PROTOCOL_VERSION,
                "capabilities", Map.of(
                        "tools", Map.of(),
                        "resources", Map.of()
                ),
                "serverInfo", Map.of(
                        "name", "mobiflow-control-service",
                        "version", "0.1.0"
                )
        );
    }

    private Map<String, Object> toolsList() {
        List<Map<String, Object>> tools = new ArrayList<>();
        for (ToolApiModels.ToolCatalogItem item : toolFacadeService.catalog().tools()) {
            tools.add(toMcpTool(item));
        }
        tools.add(resolveConfirmationTool());
        tools.add(queryAuditsTool());
        return Map.of("tools", tools);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> toolsCall(McpApiModels.JsonRpcRequest request) {
        Map<String, Object> params = params(request);
        String name = requireString(params, "name");
        Map<String, Object> arguments = mapValue(params.get("arguments"));
        String sessionId = stringValue(params.get("sessionId"), DEFAULT_SESSION_ID);
        ToolApiModels.CallerContext callerContext = callerContext(params.get("callerContext"));

        Object envelope;
        if ("resolve_confirmation".equals(name)) {
            envelope = toolFacadeService.resolveConfirmation(new ToolApiModels.ResolveConfirmationRequest(
                    ToolFacadeService.PROTOCOL_VERSION,
                    requireString(arguments, "confirmationId"),
                    stringValue(arguments.get("decision"), "approve"),
                    sessionId,
                    callerContext
            ));
        } else if ("query_audits".equals(name)) {
            envelope = toolFacadeService.queryAudits(new ToolApiModels.AuditQueryRequest(
                    stringValue(arguments.get("sessionId"), null),
                    stringValue(arguments.get("agentTaskId"), null),
                    stringValue(arguments.get("turnId"), null),
                    stringValue(arguments.get("runId"), null),
                    stringValue(arguments.get("runTargetId"), null),
                    stringValue(arguments.get("attemptId"), null)
            ));
        } else {
            String requestId = stringValue(params.get("requestId"), "mcp:" + name + ":" + request.id());
            envelope = toolFacadeService.execute(new ToolApiModels.ExecuteToolRequest(
                    ToolFacadeService.PROTOCOL_VERSION,
                    requestId,
                    sessionId,
                    name,
                    arguments,
                    callerContext
            ));
        }
        return toolCallResult(envelope);
    }

    private Map<String, Object> resourcesRead(McpApiModels.JsonRpcRequest request) {
        Map<String, Object> params = params(request);
        String uri = requireString(params, "uri");
        String handle = resourceHandleFromUri(uri);
        ToolApiModels.ReadResourceResponse resource = toolResourceService.read(handle);
        Map<String, Object> content = new LinkedHashMap<>();
        content.put("uri", uri);
        content.put("mimeType", resource.mimeType());
        content.put("text", resource.content() instanceof String
                ? resource.content()
                : writeJson(resource.content()));
        return Map.of("contents", List.of(content));
    }

    private Map<String, Object> toolCallResult(Object envelope) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("content", List.of(Map.of(
                "type", "text",
                "text", writeJson(envelope)
        )));
        result.put("structuredContent", envelope);
        result.put("isError", isFailedEnvelope(envelope));
        return result;
    }

    private boolean isFailedEnvelope(Object envelope) {
        if (envelope instanceof ToolApiModels.ExecuteToolResponse response) {
            return "failed".equals(response.status());
        }
        return false;
    }

    private Map<String, Object> toMcpTool(ToolApiModels.ToolCatalogItem item) {
        Map<String, Object> tool = new LinkedHashMap<>();
        tool.put("name", item.name());
        tool.put("title", item.title());
        tool.put("description", item.description());
        tool.put("inputSchema", item.inputSchema());
        tool.put("_meta", mobiflowMeta(
                item.toolKind(),
                item.riskLevel(),
                item.governance(),
                item.semanticTags()
        ));
        tool.put("annotations", Map.of(
                "readOnlyHint", !"side_effect".equals(item.toolKind()),
                "destructiveHint", "EXECUTION".equals(item.riskLevel()),
                "idempotentHint", !"side_effect".equals(item.toolKind())
                        || item.semanticTags().contains("idempotent"),
                "openWorldHint", false
        ));
        return tool;
    }

    private Map<String, Object> resolveConfirmationTool() {
        return Map.of(
                "name", "resolve_confirmation",
                "title", "Resolve Confirmation",
                "description", "Approve or reject a pending governed tool confirmation.",
                "inputSchema", objectSchema(Map.of(
                        "confirmationId", stringSchema(),
                        "decision", enumSchema(List.of("approve", "reject"))
                ), List.of("confirmationId", "decision")),
                "_meta", mobiflowMeta(
                        "side_effect",
                        "EXECUTION",
                        new ToolApiModels.ToolGovernance(false, null),
                        List.of("governed", "approval")
                ),
                "annotations", Map.of(
                        "readOnlyHint", false,
                        "destructiveHint", false,
                        "idempotentHint", false,
                        "openWorldHint", false
                )
        );
    }

    private Map<String, Object> queryAuditsTool() {
        return Map.of(
                "name", "query_audits",
                "title", "Query Tool Audits",
                "description", "Query the platform tool audit timeline.",
                "inputSchema", objectSchema(Map.of(
                        "sessionId", stringSchema(),
                        "agentTaskId", stringSchema(),
                        "turnId", stringSchema(),
                        "runId", stringSchema(),
                        "runTargetId", stringSchema(),
                        "attemptId", stringSchema()
                ), List.of()),
                "_meta", mobiflowMeta(
                        "read",
                        "DISCOVERY",
                        new ToolApiModels.ToolGovernance(false, null),
                        List.of("audit", "lineage")
                ),
                "annotations", Map.of(
                        "readOnlyHint", true,
                        "destructiveHint", false,
                        "idempotentHint", true,
                        "openWorldHint", false
                )
        );
    }

    private Map<String, Object> mobiflowMeta(String toolKind,
                                             String riskLevel,
                                             ToolApiModels.ToolGovernance governance,
                                             List<String> semanticTags) {
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("mobiflow/toolKind", toolKind);
        meta.put("mobiflow/riskLevel", riskLevel);
        meta.put("mobiflow/governance", governance);
        meta.put("mobiflow/semanticTags", semanticTags == null ? List.of() : semanticTags);
        return meta;
    }

    private Map<String, Object> objectSchema(Map<String, Object> properties, List<String> required) {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");
        schema.put("properties", properties);
        schema.put("additionalProperties", false);
        if (!required.isEmpty()) {
            schema.put("required", required);
        }
        return schema;
    }

    private Map<String, Object> stringSchema() {
        return Map.of("type", "string");
    }

    private Map<String, Object> enumSchema(List<String> values) {
        return Map.of("type", "string", "enum", values);
    }

    private McpApiModels.JsonRpcResponse error(Object id, int code, String message, Object data) {
        return new McpApiModels.JsonRpcResponse(
                JSONRPC_VERSION,
                id,
                null,
                new McpApiModels.JsonRpcError(code, message, data)
        );
    }

    private Map<String, Object> params(McpApiModels.JsonRpcRequest request) {
        return request.params() == null ? Map.of() : request.params();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        if (value == null) {
            return Map.of();
        }
        if (value instanceof Map<?, ?> map) {
            return (Map<String, Object>) map;
        }
        throw new IllegalArgumentException("Expected object value.");
    }

    private String requireString(Map<String, Object> payload, String key) {
        String value = stringValue(payload.get(key), null);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing required string parameter: " + key);
        }
        return value;
    }

    private String stringValue(Object value, String defaultValue) {
        return value instanceof String text && !text.isBlank() ? text : defaultValue;
    }

    private ToolApiModels.CallerContext callerContext(Object value) {
        Map<String, Object> payload = mapValue(value);
        return new ToolApiModels.CallerContext(
                stringValue(payload.get("agentTaskId"), null),
                stringValue(payload.get("turnId"), null),
                stringValue(payload.get("stepId"), null)
        );
    }

    private String resourceHandleFromUri(String uri) {
        String prefix = "mobiflow://resource/";
        if (!uri.startsWith(prefix)) {
            throw new IllegalArgumentException("Unsupported MCP resource URI: " + uri);
        }
        return URLDecoder.decode(uri.substring(prefix.length()), StandardCharsets.UTF_8);
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("Could not serialize MCP payload.");
        }
    }
}
