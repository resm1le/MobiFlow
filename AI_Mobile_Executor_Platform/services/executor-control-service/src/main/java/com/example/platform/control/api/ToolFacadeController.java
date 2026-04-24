package com.example.platform.control.api;

import com.example.platform.control.application.ToolFacadeService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/tools")
public class ToolFacadeController {

    private final ToolFacadeService toolFacadeService;

    public ToolFacadeController(ToolFacadeService toolFacadeService) {
        this.toolFacadeService = toolFacadeService;
    }

    @PostMapping("/execute")
    public ToolApiModels.ExecuteToolResponse execute(@RequestBody ToolApiModels.ExecuteToolRequest request) {
        return toolFacadeService.execute(request);
    }

    @PostMapping("/confirmations/resolve")
    public ToolApiModels.ExecuteToolResponse resolve(@RequestBody ToolApiModels.ResolveConfirmationRequest request) {
        return toolFacadeService.resolveConfirmation(request);
    }

    @PostMapping("/audits/query")
    public ToolApiModels.AuditQueryResponse queryAudits(@RequestBody ToolApiModels.AuditQueryRequest request) {
        return toolFacadeService.queryAudits(request);
    }
}
