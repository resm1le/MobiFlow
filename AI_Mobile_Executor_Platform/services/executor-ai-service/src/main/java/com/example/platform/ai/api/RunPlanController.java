package com.example.platform.ai.api;

import com.example.platform.ai.api.dto.RunPlanResponse;
import com.example.platform.ai.api.dto.RunPlanningContext;
import com.example.platform.ai.app.RunPlanningService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/run-plans")
public class RunPlanController {

    private final RunPlanningService runPlanningService;

    public RunPlanController(RunPlanningService runPlanningService) {
        this.runPlanningService = runPlanningService;
    }

    @PostMapping
    public RunPlanResponse createRunPlan(@Valid @RequestBody RunPlanningContext context) {
        return runPlanningService.createRunPlan(context);
    }
}
