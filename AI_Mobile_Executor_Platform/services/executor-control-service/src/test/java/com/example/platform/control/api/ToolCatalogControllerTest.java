package com.example.platform.control.api;

import com.example.platform.control.application.ToolFacadeService;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;
import java.util.Map;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ToolCatalogControllerTest {

    @Test
    void catalogReturnsMachineReadableSchemas() throws Exception {
        ToolFacadeService service = mock(ToolFacadeService.class);
        when(service.catalog()).thenReturn(new ToolApiModels.ToolCatalogResponse(
                "tool-envelope-v2",
                List.of(new ToolApiModels.ToolCatalogItem(
                        "list_devices",
                        "List Devices",
                        "List devices",
                        Map.of("type", "object", "properties", Map.of()),
                        Map.of("type", "array"),
                        "inline",
                        "stable",
                        "read",
                        "DISCOVERY",
                        new ToolApiModels.ToolGovernance(false, null),
                        List.of("observation")
                ))
        ));

        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new ToolCatalogController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(get("/tools/catalog"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value("tool-envelope-v2"))
                .andExpect(jsonPath("$.tools[0].name").value("list_devices"))
                .andExpect(jsonPath("$.tools[0].title").value("List Devices"))
                .andExpect(jsonPath("$.tools[0].inputSchema.type").value("object"))
                .andExpect(jsonPath("$.tools[0].stability").value("stable"))
                .andExpect(jsonPath("$.tools[0].toolKind").value("read"))
                .andExpect(jsonPath("$.tools[0].governance.requiresApproval").value(false))
                .andExpect(jsonPath("$.tools[0].enabled").doesNotExist());
    }
}
