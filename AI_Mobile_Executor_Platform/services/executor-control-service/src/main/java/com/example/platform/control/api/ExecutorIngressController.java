package com.example.platform.control.api;

import com.example.platform.control.api.ExecutorApiModels.ExecutorAckResponse;
import com.example.platform.control.api.ExecutorApiModels.ExecutorIdentityRequest;
import com.example.platform.control.api.ExecutorApiModels.ArtifactUploadFinalizeRequest;
import com.example.platform.control.api.ExecutorApiModels.ArtifactUploadFinalizeResponse;
import com.example.platform.control.api.ExecutorApiModels.ArtifactUploadTicketRequest;
import com.example.platform.control.api.ExecutorApiModels.ArtifactUploadTicketResponse;
import com.example.platform.control.api.ExecutorApiModels.ClaimTaskResponse;
import com.example.platform.control.api.ExecutorApiModels.EventsRequest;
import com.example.platform.control.api.ExecutorApiModels.FinishRequest;
import com.example.platform.control.api.ExecutorApiModels.HeartbeatResponse;
import com.example.platform.control.api.ExecutorApiModels.StartRequest;
import com.example.platform.control.application.ArtifactUploadService;
import com.example.platform.control.application.ControlApiExceptions;
import com.example.platform.control.application.ControlErrorCode;
import com.example.platform.control.application.ControlPlaneService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ExecutorIngressController {

    private final ControlPlaneService controlPlaneService;
    private final ArtifactUploadService artifactUploadService;

    public ExecutorIngressController(ControlPlaneService controlPlaneService, ArtifactUploadService artifactUploadService) {
        this.controlPlaneService = controlPlaneService;
        this.artifactUploadService = artifactUploadService;
    }

    @PostMapping("/executor/register")
    public ExecutorAckResponse register(HttpServletRequest servletRequest, @Valid @RequestBody ExecutorIdentityRequest request) {
        return controlPlaneService.register(ExecutorAuthContext.required(servletRequest), request);
    }

    @PostMapping("/executor/heartbeat")
    public HeartbeatResponse heartbeat(HttpServletRequest servletRequest, @Valid @RequestBody ExecutorIdentityRequest request) {
        return controlPlaneService.heartbeat(ExecutorAuthContext.required(servletRequest), request);
    }

    @PostMapping("/executor/tasks/claim")
    public ClaimTaskResponse claim(HttpServletRequest servletRequest, @Valid @RequestBody ExecutorIdentityRequest request) {
        return controlPlaneService.claim(ExecutorAuthContext.required(servletRequest), request);
    }

    @PostMapping("/executor/tasks/{attemptId}/start")
    public void start(@PathVariable String attemptId, HttpServletRequest servletRequest, @Valid @RequestBody StartRequest request) {
        controlPlaneService.start(ExecutorAuthContext.required(servletRequest), attemptId, request);
    }

    @PostMapping("/executor/tasks/{attemptId}/events")
    public void events(@PathVariable String attemptId, HttpServletRequest servletRequest, @Valid @RequestBody EventsRequest request) {
        controlPlaneService.recordEvents(ExecutorAuthContext.required(servletRequest), attemptId, request);
    }

    @PostMapping("/executor/tasks/{attemptId}/finish")
    public void finish(@PathVariable String attemptId, HttpServletRequest servletRequest, @Valid @RequestBody FinishRequest request) {
        controlPlaneService.finish(ExecutorAuthContext.required(servletRequest), attemptId, request);
    }

    @PostMapping("/executor/tasks/{attemptId}/artifacts")
    public void artifacts(@PathVariable String attemptId) {
        throw ControlApiExceptions.gone(ControlErrorCode.ARTIFACT_UPLOAD_V1_REMOVED);
    }

    @PostMapping("/executor/tasks/{attemptId}/artifacts/uploads")
    public ArtifactUploadTicketResponse requestArtifactUploadTicket(@PathVariable String attemptId,
                                                                    HttpServletRequest servletRequest,
                                                                    @Valid @RequestBody ArtifactUploadTicketRequest request) {
        return artifactUploadService.requestUploadTicket(ExecutorAuthContext.required(servletRequest), attemptId, request);
    }

    @PostMapping("/executor/tasks/{attemptId}/artifacts/uploads/{artifactId}/finalize")
    public ArtifactUploadFinalizeResponse finalizeArtifactUpload(@PathVariable String attemptId,
                                                                 @PathVariable String artifactId,
                                                                 HttpServletRequest servletRequest,
                                                                 @Valid @RequestBody ArtifactUploadFinalizeRequest request) {
        return artifactUploadService.finalizeUpload(ExecutorAuthContext.required(servletRequest), attemptId, artifactId, request);
    }
}
