package com.example.platform.control.api;

import com.example.platform.control.api.AdminApiModels.ExperimentRunDetailResponse;
import com.example.platform.control.application.AiRunPlanningService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/ai/run-plans")
public class AiRunPlanController {

    private final AiRunPlanningService aiRunPlanningService;

    public AiRunPlanController(AiRunPlanningService aiRunPlanningService) {
        this.aiRunPlanningService = aiRunPlanningService;
    }

    @PostMapping
    public AiRunPlanApiModels.CreateRunPlanResponse create(@Valid @RequestBody AiRunPlanApiModels.CreateRunPlanRequest request) {
        return aiRunPlanningService.createRunPlan(request);
    }

    @PostMapping("/{requestId}/materialize")
    public ExperimentRunDetailResponse materialize(@PathVariable String requestId,
                                                   @Valid @RequestBody AiRunPlanApiModels.MaterializeRunPlanRequest request) {
        return aiRunPlanningService.materializeRunPlan(requestId, request.createdBy());
    }
}
