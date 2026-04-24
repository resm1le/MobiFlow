package com.example.platform.control.api;

import com.example.platform.control.application.ToolFacadeService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/tools")
public class ToolCatalogController {

    private final ToolFacadeService toolFacadeService;

    public ToolCatalogController(ToolFacadeService toolFacadeService) {
        this.toolFacadeService = toolFacadeService;
    }

    @GetMapping("/catalog")
    public ToolApiModels.ToolCatalogResponse catalog() {
        return toolFacadeService.catalog();
    }
}
