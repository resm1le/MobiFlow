package com.example.platform.control.application;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;

import static org.junit.jupiter.api.Assertions.assertEquals;

class HttpAiBridgeClientTest {

    private HttpServer server;

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void createRunPlanMapsStructuredProviderResponse() throws IOException {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/internal/run-plans", this::handleRunPlanRequest);
        server.setExecutor(Executors.newSingleThreadExecutor());
        server.start();

        ControlProperties properties = new ControlProperties();
        properties.getAi().setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());

        HttpAiBridgeClient client = new HttpAiBridgeClient(RestClient.builder(), properties);
        AiBridgeModels.RunPlanResponse response = client.createRunPlan(new Phase3AiModels.RunPlanningContext(
                "navigate to ikea",
                Map.of(),
                List.of(new Phase3AiModels.AvailableDevicePool("pool-1", "Pool 1", "default", 1, List.of(), List.of())),
                List.of(new Phase3AiModels.AvailableProfile(
                        "com.google.android.apps.maps",
                        1,
                        List.of("PLUGIN_RUN"),
                        List.of("goal"),
                        Map.of(),
                        List.of()
                )),
                new Phase3AiModels.DefaultRunPolicy(
                        100,
                        0,
                        300000,
                        Map.of(
                                "loopCount", 1,
                                "budgetMs", 60000,
                                "loopIntervalMs", 0,
                                "networkIsolationEnabled", false,
                                "pollIntervalMs", 15000,
                                "heartbeatIntervalMs", 30000
                        ),
                        Map.of(
                                "uploadLog", true,
                                "uploadScreenshot", true,
                                "uploadDump", false
                        )
                ),
                List.of("PLUGIN_RUN")
        ));

        assertEquals("AI run", response.runDraft().name());
        assertEquals("pool-1", response.runDraft().devicePoolId());
        assertEquals("openai-compatible", response.modelMeta().get("provider"));
    }

    @Test
    void createRunSummaryMapsStructuredProviderResponse() throws IOException {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/internal/run-summaries", this::handleRunSummaryRequest);
        server.setExecutor(Executors.newSingleThreadExecutor());
        server.start();

        ControlProperties properties = new ControlProperties();
        properties.getAi().setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());

        HttpAiBridgeClient client = new HttpAiBridgeClient(RestClient.builder(), properties);
        AiBridgeModels.RunSummaryResponse response = client.createRunSummary(new Phase3AiModels.RunSummaryContext(
                new Phase3AiModels.RunSummary(
                        "run-1",
                        "pool-1",
                        "TERMINAL",
                        "SUCCEEDED",
                        "PLUGIN_RUN",
                        "com.zhiliaoapp.musically",
                        100,
                        List.of("ai"),
                        0,
                        300000,
                        false,
                        1L,
                        2L
                ),
                new Phase3AiModels.RunCounts(1, 0, 0, 0, 1, 0, 0),
                List.of(),
                List.of(),
                List.of(),
                List.of()
        ));

        assertEquals("Summary ok", response.result().summaryText());
        assertEquals("Launch", response.result().keyMoments().get(0).title());
        assertEquals("openai-compatible", response.modelMeta().get("provider"));
    }

    private void handleRunPlanRequest(HttpExchange exchange) throws IOException {
        String body = """
                {
                  "runDraft": {
                    "name": "AI run",
                    "description": "navigate to ikea",
                    "devicePoolId": "pool-1",
                    "taskType": "PLUGIN_RUN",
                    "profilePackage": "com.google.android.apps.maps",
                    "taskPayload": {
                      "goal": "navigate to ikea"
                    },
                    "runConfig": {
                      "loopCount": 1,
                      "budgetMs": 60000,
                      "loopIntervalMs": 0,
                      "networkIsolationEnabled": false,
                      "pollIntervalMs": 15000,
                      "heartbeatIntervalMs": 30000
                    },
                    "artifactPolicy": {
                      "uploadLog": true,
                      "uploadScreenshot": true,
                      "uploadDump": false
                    },
                    "priority": 100,
                    "labels": ["ai"],
                    "maxRetriesPerDevice": 0,
                    "queueTimeoutMs": 300000
                  },
                  "warnings": ["soft warning"],
                  "reviewHints": ["review pool"],
                  "modelMeta": {
                    "provider": "openai-compatible",
                    "model": "deepseek-chat",
                    "generatedAt": 1774082202706
                  }
                }
                """;
        byte[] payload = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(200, payload.length);
        try (OutputStream outputStream = exchange.getResponseBody()) {
            outputStream.write(payload);
        }
    }

    private void handleRunSummaryRequest(HttpExchange exchange) throws IOException {
        String body = """
                {
                  "result": {
                    "summaryText": "Summary ok",
                    "keyMoments": [
                      {
                        "title": "Launch",
                        "eventType": "run_start",
                        "stepIndex": 0,
                        "message": "task started"
                      }
                    ],
                    "finalJudgement": "Healthy run",
                    "evidence": ["event:run_start:task started"]
                  },
                  "modelMeta": {
                    "provider": "openai-compatible",
                    "model": "deepseek-chat",
                    "generatedAt": 1774082202706
                  }
                }
                """;
        byte[] payload = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(200, payload.length);
        try (OutputStream outputStream = exchange.getResponseBody()) {
            outputStream.write(payload);
        }
    }
}
