package com.example.platform.ai.api;

import com.example.platform.ai.api.dto.FailureTriageContext;
import com.example.platform.ai.api.dto.FailureTriageResponse;
import com.example.platform.ai.app.FailureTriageService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/failure-triage")
public class FailureTriageController {

    private final FailureTriageService failureTriageService;

    public FailureTriageController(FailureTriageService failureTriageService) {
        this.failureTriageService = failureTriageService;
    }

    @PostMapping
    public FailureTriageResponse create(@Valid @RequestBody FailureTriageContext context) {
        return failureTriageService.createFailureTriage(context);
    }
}
