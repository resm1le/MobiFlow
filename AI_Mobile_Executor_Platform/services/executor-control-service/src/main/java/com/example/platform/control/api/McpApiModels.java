package com.example.platform.control.api;

import java.util.Map;

public final class McpApiModels {

    private McpApiModels() {
    }

    public record JsonRpcRequest(
            String jsonrpc,
            Object id,
            String method,
            Map<String, Object> params
    ) {
    }

    public record JsonRpcResponse(
            String jsonrpc,
            Object id,
            Object result,
            JsonRpcError error
    ) {
    }

    public record JsonRpcError(
            int code,
            String message,
            Object data
    ) {
    }
}
