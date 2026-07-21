package com.example.platform.control.api;

import com.example.platform.control.api.AdminApiModels.CreateExperimentRunRequest;
import com.example.platform.control.api.AdminApiModels.CreateHeterogeneousRunRequest;
import com.example.platform.control.api.AdminApiModels.ExperimentRunDetailResponse;
import com.example.platform.control.api.AdminApiModels.ExperimentRunSummaryResponse;
import com.example.platform.control.application.ExperimentRunService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/runs")
public class AdminRunController {

    private final ExperimentRunService experimentRunService;

    public AdminRunController(ExperimentRunService experimentRunService) {
        this.experimentRunService = experimentRunService;
    }

    @GetMapping
    public List<ExperimentRunSummaryResponse> list() {
        return experimentRunService.listRuns();
    }

    @PostMapping
    public ExperimentRunDetailResponse create(@Valid @RequestBody CreateExperimentRunRequest request) {
        return experimentRunService.createRun(request);
    }

    @PostMapping("/heterogeneous")
    public ExperimentRunDetailResponse createHeterogeneous(@Valid @RequestBody CreateHeterogeneousRunRequest request) {
        return experimentRunService.createHeterogeneousRun(request);
    }

    @GetMapping("/{runId}")
    public ExperimentRunDetailResponse get(@PathVariable String runId) {
        return experimentRunService.getRun(runId);
    }

    @PostMapping("/{runId}/cancel")
    public void cancel(@PathVariable String runId) {
        experimentRunService.cancelRun(runId);
    }
}
