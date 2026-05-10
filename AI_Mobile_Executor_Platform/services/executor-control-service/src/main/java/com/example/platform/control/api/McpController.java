package com.example.platform.control.api;

import com.example.platform.control.application.McpFacadeService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/mcp")
public class McpController {

    private final McpFacadeService mcpFacadeService;

    public McpController(McpFacadeService mcpFacadeService) {
        this.mcpFacadeService = mcpFacadeService;
    }

    @PostMapping
    public McpApiModels.JsonRpcResponse handle(@RequestBody McpApiModels.JsonRpcRequest request) {
        return mcpFacadeService.handle(request);
    }
}
