package com.example.platform.control.api;

import com.example.platform.control.application.AiFailureTriageService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class RunTargetFailureTriageController {

    private final AiFailureTriageService aiFailureTriageService;

    public RunTargetFailureTriageController(AiFailureTriageService aiFailureTriageService) {
        this.aiFailureTriageService = aiFailureTriageService;
    }

    @PostMapping("/run-targets/{runTargetId}/failure-triage")
    public AiFailureTriageApiModels.FailureTriageResponse create(@PathVariable String runTargetId) {
        return aiFailureTriageService.createFailureTriage(runTargetId);
    }

    @GetMapping("/run-targets/{runTargetId}/failure-triage/latest")
    public AiFailureTriageApiModels.FailureTriageResponse latest(@PathVariable String runTargetId) {
        return aiFailureTriageService.getLatestFailureTriage(runTargetId);
    }

    @GetMapping("/failure-triage/{triageResultId}")
    public AiFailureTriageApiModels.FailureTriageResponse get(@PathVariable String triageResultId) {
        return aiFailureTriageService.getFailureTriage(triageResultId);
    }
}
