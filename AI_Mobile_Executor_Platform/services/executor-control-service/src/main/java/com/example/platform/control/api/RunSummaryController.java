package com.example.platform.control.api;

import com.example.platform.control.application.AiRunSummaryService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class RunSummaryController {

    private final AiRunSummaryService aiRunSummaryService;

    public RunSummaryController(AiRunSummaryService aiRunSummaryService) {
        this.aiRunSummaryService = aiRunSummaryService;
    }

    @PostMapping("/runs/{runId}/summary")
    public AiRunSummaryApiModels.RunSummaryResponse create(@PathVariable String runId) {
        return aiRunSummaryService.createRunSummary(runId);
    }

    @GetMapping("/runs/{runId}/summary/latest")
    public AiRunSummaryApiModels.RunSummaryResponse latest(@PathVariable String runId) {
        return aiRunSummaryService.getLatestRunSummary(runId);
    }

    @GetMapping("/run-summaries/{summaryId}")
    public AiRunSummaryApiModels.RunSummaryResponse get(@PathVariable String summaryId) {
        return aiRunSummaryService.getRunSummary(summaryId);
    }
}
