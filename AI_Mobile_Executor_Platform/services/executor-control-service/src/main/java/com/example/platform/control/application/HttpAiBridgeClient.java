package com.example.platform.control.application;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

import java.time.Duration;
import java.util.List;
import java.util.Map;

@Component
public class HttpAiBridgeClient implements AiBridgeClient {

    private final RestClient restClient;

    public HttpAiBridgeClient(RestClient.Builder restClientBuilder, ControlProperties controlProperties) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofMillis(controlProperties.getAi().getConnectTimeoutMs()));
        requestFactory.setReadTimeout(Duration.ofMillis(controlProperties.getAi().getReadTimeoutMs()));
        this.restClient = restClientBuilder
                .requestFactory(requestFactory)
                .baseUrl(controlProperties.getAi().getBaseUrl())
                .build();
    }

    @Override
    public AiBridgeModels.RunPlanResponse createRunPlan(Phase3AiModels.RunPlanningContext request) {
        try {
            RunPlanProviderResponse response = restClient.post()
                    .uri("/internal/run-plans")
                    .body(request)
                    .retrieve()
                    .body(RunPlanProviderResponse.class);
            if (response == null || response.runDraft() == null) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "AI_PROVIDER_FAILURE");
            }
            return new AiBridgeModels.RunPlanResponse(
                    response.runDraft(),
                    response.warnings() == null ? List.of() : response.warnings(),
                    response.reviewHints() == null ? List.of() : response.reviewHints(),
                    response.modelMeta() == null ? Map.of() : response.modelMeta()
            );
        } catch (RestClientException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "AI_PROVIDER_FAILURE", exception);
        }
    }

    @Override
    public AiBridgeModels.FailureTriageResponse createFailureTriage(Phase3AiModels.FailureTriageContext request) {
        try {
            FailureTriageProviderResponse response = restClient.post()
                    .uri("/internal/failure-triage")
                    .body(request)
                    .retrieve()
                    .body(FailureTriageProviderResponse.class);
            if (response == null || response.result() == null) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "AI_PROVIDER_FAILURE");
            }
            return new AiBridgeModels.FailureTriageResponse(
                    response.result(),
                    response.modelMeta() == null ? Map.of() : response.modelMeta()
            );
        } catch (RestClientException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "AI_PROVIDER_FAILURE", exception);
        }
    }

    @Override
    public AiBridgeModels.RunSummaryResponse createRunSummary(Phase3AiModels.RunSummaryContext request) {
        try {
            RunSummaryProviderResponse response = restClient.post()
                    .uri("/internal/run-summaries")
                    .body(request)
                    .retrieve()
                    .body(RunSummaryProviderResponse.class);
            if (response == null || response.result() == null) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "AI_PROVIDER_FAILURE");
            }
            return new AiBridgeModels.RunSummaryResponse(
                    response.result(),
                    response.modelMeta() == null ? Map.of() : response.modelMeta()
            );
        } catch (RestClientException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "AI_PROVIDER_FAILURE", exception);
        }
    }

    private record RunPlanProviderResponse(
            Phase3AiModels.RunDraft runDraft,
            List<String> warnings,
            List<String> reviewHints,
            Map<String, Object> modelMeta
    ) {
    }

    private record FailureTriageProviderResponse(
            Phase3AiModels.FailureTriageResult result,
            Map<String, Object> modelMeta
    ) {
    }

    private record RunSummaryProviderResponse(
            Phase3AiModels.RunSummaryResult result,
            Map<String, Object> modelMeta
    ) {
    }
}
