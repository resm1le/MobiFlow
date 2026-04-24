package com.example.platform.ai.api;

import com.example.platform.ai.api.dto.RunSummaryContext;
import com.example.platform.ai.api.dto.RunSummaryResponse;
import com.example.platform.ai.app.RunSummaryService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/run-summaries")
public class RunSummaryController {

    private final RunSummaryService runSummaryService;

    public RunSummaryController(RunSummaryService runSummaryService) {
        this.runSummaryService = runSummaryService;
    }

    @PostMapping
    public RunSummaryResponse createRunSummary(@Valid @RequestBody RunSummaryContext context) {
        return runSummaryService.createRunSummary(context);
    }
}
