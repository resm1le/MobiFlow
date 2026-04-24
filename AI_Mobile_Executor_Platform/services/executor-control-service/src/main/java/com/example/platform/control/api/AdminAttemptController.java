package com.example.platform.control.api;

import com.example.platform.control.api.AdminApiModels.AttemptDetailResponse;
import com.example.platform.control.api.AdminApiModels.AttemptSummary;
import com.example.platform.control.api.AdminApiModels.ArtifactResponse;
import com.example.platform.control.api.AdminApiModels.RunEventResponse;
import com.example.platform.control.application.AdminApiService;
import com.example.platform.control.application.ControlApiExceptions;
import com.example.platform.control.application.ControlErrorCode;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.util.List;

@RestController
@RequestMapping("/api/attempts")
public class AdminAttemptController {

    private final AdminApiService adminApiService;

    public AdminAttemptController(AdminApiService adminApiService) {
        this.adminApiService = adminApiService;
    }

    @GetMapping
    public List<AttemptSummary> list() {
        return adminApiService.listAttempts();
    }

    @GetMapping("/{attemptId}")
    public AttemptDetailResponse get(@PathVariable String attemptId) {
        return adminApiService.getAttempt(attemptId);
    }

    @GetMapping("/{attemptId}/events")
    public List<RunEventResponse> events(@PathVariable String attemptId) {
        return adminApiService.getAttemptEvents(attemptId);
    }

    @GetMapping("/{attemptId}/artifacts")
    public List<ArtifactResponse> artifacts(@PathVariable String attemptId) {
        return adminApiService.getAttemptArtifacts(attemptId);
    }

    @GetMapping("/{attemptId}/artifacts/{artifactId}/download")
    public ResponseEntity<InputStreamResource> download(@PathVariable String attemptId,
                                                        @PathVariable String artifactId) {
        AdminApiService.ArtifactDownload artifact = adminApiService.downloadAttemptArtifact(attemptId, artifactId);
        return ResponseEntity.ok()
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename(artifact.fileName(), StandardCharsets.UTF_8)
                                .build()
                                .toString()
                )
                .contentType(MediaType.parseMediaType(artifact.mimeType()))
                .body(new InputStreamResource(artifact.inputStream()));
    }

    @PostMapping("/{attemptId}/summary")
    public void summarize(@PathVariable String attemptId) {
        throw ControlApiExceptions.gone(ControlErrorCode.LEGACY_AI_ATTEMPT_SUMMARY_REMOVED);
    }

    @PostMapping("/{attemptId}/failure-analysis")
    public void analyzeFailure(@PathVariable String attemptId) {
        throw ControlApiExceptions.gone(ControlErrorCode.LEGACY_AI_ATTEMPT_FAILURE_ANALYSIS_REMOVED);
    }
}
