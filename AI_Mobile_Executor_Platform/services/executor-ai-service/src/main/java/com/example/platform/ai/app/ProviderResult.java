package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.ModelMetaDto;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.List;

public record ProviderResult(
        JsonNode payload,
        List<String> warnings,
        ModelMetaDto modelMeta
) {
}
