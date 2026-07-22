package com.example.platform.control.integration;

import com.example.platform.control.ExecutorControlServiceApplication;
import com.example.platform.control.api.AdminApiModels.CreateHeterogeneousRunRequest;
import com.example.platform.control.api.AdminApiModels.DeviceSelector;
import com.example.platform.control.api.AdminApiModels.ExperimentRunDetailResponse;
import com.example.platform.control.api.AdminApiModels.HeterogeneousDispatchEntry;
import com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy;
import com.example.platform.control.api.ExecutorApiModels.ClaimTaskResponse;
import com.example.platform.control.api.ExecutorApiModels.ClaimedTask;
import com.example.platform.control.api.ExecutorApiModels.RunConfig;
import com.example.platform.control.application.ExperimentRunService;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.RunEventEntity;
import com.example.platform.control.infrastructure.mapper.RunEventMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ExecutorControlServiceApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@ActiveProfiles("test")
@Testcontainers(disabledWithoutDocker = true)
class MockExecutorRunIntegrationTest {

    private static final String DEVICE_7 = "dev-7";
    private static final String DEVICE_9 = "dev-9";
    private static final String TOKEN_7 = "integration-token-7";
    private static final String TOKEN_9 = "integration-token-9";
    private static final String PROFILE = "com.tencent.mm";

    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("executor_platform")
            .withUsername("test")
            .withPassword("test");

    @Container
    static final GenericContainer<?> REDIS = new GenericContainer<>("redis:7.4-alpine")
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
        registry.add("platform.control.auth.device-tokens[dev-7]", () -> TOKEN_7);
        registry.add("platform.control.auth.device-tokens[dev-9]", () -> TOKEN_9);
        registry.add("platform.control.jobs.run-maintenance-interval-ms", () -> 60_000_000L);
    }

    @LocalServerPort
    private int port;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private ExperimentRunService experimentRunService;

    @Autowired
    private RunEventMapper runEventMapper;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @AfterEach
    void cleanDatabase() {
        jdbcTemplate.update("DELETE FROM outbox_jobs");
        jdbcTemplate.update("DELETE FROM ai_run_summary_results");
        jdbcTemplate.update("DELETE FROM ai_failure_triage_results");
        jdbcTemplate.update("DELETE FROM ai_run_plan_results");
        jdbcTemplate.update("DELETE FROM ai_run_plan_requests");
        jdbcTemplate.update("DELETE FROM artifact_upload_sessions");
        jdbcTemplate.update("DELETE FROM artifacts");
        jdbcTemplate.update("DELETE FROM run_events");
        jdbcTemplate.update("DELETE FROM device_commands");
        jdbcTemplate.update("DELETE FROM task_attempts");
        jdbcTemplate.update("DELETE FROM experiment_run_targets");
        jdbcTemplate.update("DELETE FROM experiment_runs");
        jdbcTemplate.update("DELETE FROM device_pools");
        jdbcTemplate.update("DELETE FROM tasks");
        jdbcTemplate.update("DELETE FROM device_runtime_state");
        jdbcTemplate.update("DELETE FROM devices");
    }

    @Test
    void signedDevicesCompletePinnedRunAndReplayWaypointEvidenceSafely() throws Exception {
        register(DEVICE_7, TOKEN_7);
        register(DEVICE_9, TOKEN_9);
        ExperimentRunDetailResponse created = createRun(0, List.of(
                dispatch("wechat.text_chat.v1", "wechat_text_chat", DEVICE_7),
                dispatch("wechat.video_call.v1", "wechat_video_call", DEVICE_9)
        ));

        ClaimedTask task7 = requireClaim(DEVICE_7, TOKEN_7);
        ClaimedTask task9 = requireClaim(DEVICE_9, TOKEN_9);
        assertEquals("wechat.text_chat.v1", sequenceId(task7));
        assertEquals("wechat.video_call.v1", sequenceId(task9));
        assertNotEquals(task7.taskId(), task9.taskId());

        start(DEVICE_7, TOKEN_7, task7);
        start(DEVICE_9, TOKEN_9, task9);
        finish(DEVICE_7, TOKEN_7, task7, "SUCCESS");
        finish(DEVICE_9, TOKEN_9, task9, "SUCCESS");

        HttpResponse<byte[]> wrongOwner = waypoint(
                DEVICE_9, TOKEN_9, task7.attemptId(), "logged_in", "wechat_text_chat", true);
        assertEquals(HttpStatus.BAD_REQUEST.value(), wrongOwner.statusCode());

        HttpResponse<byte[]> recorded7 = waypoint(
                DEVICE_7, TOKEN_7, task7.attemptId(), "logged_in", "wechat_text_chat", true);
        HttpResponse<byte[]> recorded9 = waypoint(
                DEVICE_9, TOKEN_9, task9.attemptId(), "video_ready", "wechat_video_call", true);
        assertEquals(HttpStatus.OK.value(), recorded7.statusCode());
        assertEquals(HttpStatus.OK.value(), recorded9.statusCode());
        assertEquals(1, json(recorded7).get("recordedCount").asInt());

        HttpResponse<byte[]> replay = waypoint(
                DEVICE_7, TOKEN_7, task7.attemptId(), "logged_in", "wechat_text_chat", true);
        assertEquals(HttpStatus.OK.value(), replay.statusCode());
        HttpResponse<byte[]> conflictingReplay = waypointAt(
                DEVICE_7,
                TOKEN_7,
                task7.attemptId(),
                "logged_in",
                "wechat_text_chat",
                true,
                1_780_000_001_000L
        );
        assertEquals(HttpStatus.CONFLICT.value(), conflictingReplay.statusCode());
        assertEquals(1, runEventMapper.findByAttemptId(task7.attemptId()).stream()
                .filter(event -> "WAYPOINT_SEGMENT".equals(event.getEventType()))
                .count());

        String replayNonce = "nonce-replay-" + UUID.randomUUID();
        long replayTimestamp = System.currentTimeMillis();
        Map<String, Object> heartbeat = identity(DEVICE_7, null);
        HttpResponse<byte[]> firstNonceUse = signedPost(
                DEVICE_7, TOKEN_7, "/executor/heartbeat", heartbeat, replayNonce, replayTimestamp);
        HttpResponse<byte[]> secondNonceUse = signedPost(
                DEVICE_7, TOKEN_7, "/executor/heartbeat", heartbeat, replayNonce, replayTimestamp);
        assertEquals(HttpStatus.OK.value(), firstNonceUse.statusCode());
        assertEquals(HttpStatus.UNAUTHORIZED.value(), secondNonceUse.statusCode());
        assertTrue(new String(secondNonceUse.body(), StandardCharsets.UTF_8)
                .contains("EXECUTOR_NONCE_REPLAYED"));

        ExperimentRunDetailResponse completed = experimentRunService.getRun(created.run().runId());
        assertEquals(DomainValues.RUN_STATUS_TERMINAL, completed.run().status());
        assertEquals(DomainValues.RUN_FINAL_STATE_SUCCEEDED, completed.run().finalState());
        assertTrue(completed.targets().stream().allMatch(target ->
                DomainValues.RUN_TARGET_STATUS_SUCCEEDED.equals(target.status())));
    }

    @Test
    void failedAttemptAndSuccessfulRetryKeepIndependentWaypointEvidence() throws Exception {
        register(DEVICE_7, TOKEN_7);
        ExperimentRunDetailResponse created = createRun(1, List.of(
                dispatch("wechat.text_chat.v1", "wechat_text_chat", DEVICE_7)
        ));

        ClaimedTask failed = requireClaim(DEVICE_7, TOKEN_7);
        start(DEVICE_7, TOKEN_7, failed);
        finish(DEVICE_7, TOKEN_7, failed, "FAILED");
        assertEquals(HttpStatus.OK.value(), waypoint(
                DEVICE_7, TOKEN_7, failed.attemptId(), "logged_in", "wechat_text_chat", false
        ).statusCode());

        ClaimedTask retried = requireClaim(DEVICE_7, TOKEN_7);
        assertNotEquals(failed.attemptId(), retried.attemptId());
        assertNotEquals(failed.taskId(), retried.taskId());
        start(DEVICE_7, TOKEN_7, retried);
        finish(DEVICE_7, TOKEN_7, retried, "SUCCESS");
        assertEquals(HttpStatus.OK.value(), waypoint(
                DEVICE_7, TOKEN_7, retried.attemptId(), "logged_in", "wechat_text_chat", true
        ).statusCode());

        List<RunEventEntity> failedEvents = runEventMapper.findByAttemptId(failed.attemptId());
        List<RunEventEntity> retryEvents = runEventMapper.findByAttemptId(retried.attemptId());
        assertEquals(1, failedEvents.size());
        assertEquals(1, retryEvents.size());
        assertEquals("INTERRUPTED", failedEvents.get(0).getState());
        assertEquals("COMPLETE", retryEvents.get(0).getState());
        assertEquals("waypoint:0", failedEvents.get(0).getEventKey());
        assertEquals("waypoint:0", retryEvents.get(0).getEventKey());

        ExperimentRunDetailResponse completed = experimentRunService.getRun(created.run().runId());
        assertEquals(DomainValues.RUN_STATUS_TERMINAL, completed.run().status());
        assertEquals(DomainValues.RUN_FINAL_STATE_SUCCEEDED, completed.run().finalState());
        assertEquals(2, completed.targets().get(0).attemptCount());
        assertEquals(retried.attemptId(), completed.targets().get(0).latestAttemptId());
    }

    private void register(String deviceId, String token) throws Exception {
        HttpResponse<byte[]> response = signedPost(
                deviceId, token, "/executor/register", identity(deviceId, null));
        assertEquals(HttpStatus.OK.value(), response.statusCode(), responseBody(response));
    }

    private ClaimedTask requireClaim(String deviceId, String token) throws Exception {
        HttpResponse<byte[]> response = signedPost(
                deviceId, token, "/executor/tasks/claim", identity(deviceId, null));
        assertEquals(HttpStatus.OK.value(), response.statusCode(), responseBody(response));
        ClaimTaskResponse claim = objectMapper.readValue(response.body(), ClaimTaskResponse.class);
        assertTrue(claim.hasTask());
        assertNotNull(claim.task());
        return claim.task();
    }

    private void start(String deviceId, String token, ClaimedTask task) throws Exception {
        HttpResponse<byte[]> response = signedPost(deviceId, token,
                "/executor/tasks/" + task.attemptId() + "/start",
                Map.of(
                        "taskId", task.taskId(),
                        "attemptId", task.attemptId(),
                        "runId", task.runId(),
                        "profilePackage", task.profilePackage(),
                        "taskType", task.taskType(),
                        "source", task.source()
                ));
        assertTrue(isSuccessful(response), responseBody(response));
    }

    private void finish(String deviceId, String token, ClaimedTask task, String status) throws Exception {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("taskId", task.taskId());
        payload.put("attemptId", task.attemptId());
        payload.put("runId", task.runId());
        payload.put("status", status);
        payload.put("preflightSummary", null);
        payload.put("failureDetail", "FAILED".equals(status) ? Map.of(
                "failureCode", "SIMULATED_FAILURE",
                "failureStage", "mock_execution",
                "lastError", "deterministic failure",
                "capturedAt", System.currentTimeMillis()
        ) : null);
        payload.put("message", "SIMULATED EXECUTOR - NO DEVICE UI EXECUTED");
        HttpResponse<byte[]> response = signedPost(
                deviceId, token, "/executor/tasks/" + task.attemptId() + "/finish", payload);
        assertTrue(isSuccessful(response), responseBody(response));
    }

    private HttpResponse<byte[]> waypoint(String deviceId,
                                          String token,
                                          String attemptId,
                                          String stepId,
                                          String behaviorLabel,
                                          boolean complete) throws Exception {
        return waypointAt(
                deviceId, token, attemptId, stepId, behaviorLabel, complete, 1_780_000_000_000L);
    }

    private HttpResponse<byte[]> waypointAt(String deviceId,
                                            String token,
                                            String attemptId,
                                            String stepId,
                                            String behaviorLabel,
                                            boolean complete,
                                            long enteredAt) throws Exception {
        Map<String, Object> segment = new LinkedHashMap<>();
        segment.put("step_id", stepId);
        segment.put("behavior_label", behaviorLabel);
        segment.put("entered_at_ms", enteredAt);
        segment.put("arrived_at_ms", complete ? enteredAt + 400 : null);
        segment.put("dwell_ms", complete ? 400 : null);
        return signedPost(
                deviceId,
                token,
                "/executor/tasks/" + attemptId + "/waypoint-segments",
                Map.of("waypointSegments", List.of(segment))
        );
    }

    private ExperimentRunDetailResponse createRun(int maxRetries, List<HeterogeneousDispatchEntry> dispatch) {
        return experimentRunService.createHeterogeneousRun(new CreateHeterogeneousRunRequest(
                "mock executor integration",
                "SIMULATED EXECUTOR - NO DEVICE UI EXECUTED",
                "PLUGIN_RUN",
                new RunConfig(1, 300_000, 0, false, 15_000, 30_000),
                new ArtifactPolicy(false, false, false),
                100,
                List.of("p2-3c", "simulated_executor"),
                "integration-test",
                "integration-test",
                maxRetries,
                300_000L,
                dispatch
        ));
    }

    private HeterogeneousDispatchEntry dispatch(String sequenceId, String behaviorLabel, String deviceId) {
        String waypointId = sequenceId.contains("video_call") ? "video_ready" : "logged_in";
        return new HeterogeneousDispatchEntry(
                sequenceId,
                PROFILE,
                Map.of(
                        "goal", "simulated executor integration",
                        "waypoint_sequence", Map.of(
                                "sequence_id", sequenceId,
                                "behavior_label", behaviorLabel,
                                "profile_package", PROFILE,
                                "waypoints", List.of(Map.of(
                                        "waypoint_id", waypointId,
                                        "description", "Reach " + waypointId,
                                        "arrival_spec", Map.of(
                                                "verification_id", "verify:" + waypointId,
                                                "target_kind", "task",
                                                "target_id", waypointId,
                                                "success_checks", List.of(Map.of(
                                                        "check_id", waypointId + "-visible",
                                                        "description", waypointId + " is visible"
                                                ))
                                        )
                                ))
                        )
                ),
                new DeviceSelector(null, List.of(deviceId), null, null)
        );
    }

    @SuppressWarnings("unchecked")
    private String sequenceId(ClaimedTask task) {
        Map<String, Object> sequence = (Map<String, Object>) task.taskPayload().get("waypoint_sequence");
        return (String) sequence.get("sequence_id");
    }

    private Map<String, Object> identity(String deviceId, String currentAttemptId) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("deviceId", deviceId);
        payload.put("protocolVersion", "v1");
        payload.put("executorVersion", "mock-executor/integration");
        payload.put("brand", "MobiFlow");
        payload.put("model", "SimulatedExecutor");
        payload.put("androidVersion", "mock");
        payload.put("screenWidth", 1080);
        payload.put("screenHeight", 2400);
        payload.put("capabilities", Map.of(
                "accessibilityEnabled", true,
                "rootAvailable", false,
                "shellAvailable", false,
                "networkIsolationAvailable", false,
                "screenshotCapable", false,
                "uiDumpCapable", false
        ));
        payload.put("installedProfiles", List.of(PROFILE));
        payload.put("tags", List.of("android13", "simulated_executor"));
        payload.put("hostGroup", "mock");
        payload.put("healthSnapshot", null);
        payload.put("currentAttemptId", currentAttemptId);
        return payload;
    }

    private HttpResponse<byte[]> signedPost(String deviceId,
                                            String token,
                                            String path,
                                            Map<String, Object> payload) throws Exception {
        return signedPost(
                deviceId, token, path, payload, UUID.randomUUID().toString(), System.currentTimeMillis());
    }

    private HttpResponse<byte[]> signedPost(String deviceId,
                                            String token,
                                            String path,
                                            Map<String, Object> payload,
                                            String nonce,
                                            long timestamp) throws Exception {
        byte[] body = objectMapper.writeValueAsBytes(payload);
        String timestampValue = Long.toString(timestamp);
        String bodyHash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body));
        String canonical = "POST" + path + timestampValue + nonce + bodyHash;
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(token.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        String signature = HexFormat.of().formatHex(mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8)));
        HttpRequest request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .header("X-Executor-DeviceId", deviceId)
                .header("X-Executor-Protocol-Version", "v1")
                .header("X-Executor-Timestamp", timestampValue)
                .header("X-Executor-Nonce", nonce)
                .header("X-Executor-Signature", signature)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
        return httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
    }

    private com.fasterxml.jackson.databind.JsonNode json(HttpResponse<byte[]> response) throws Exception {
        return objectMapper.readTree(response.body());
    }

    private boolean isSuccessful(HttpResponse<byte[]> response) {
        return response.statusCode() >= 200 && response.statusCode() < 300;
    }

    private String responseBody(HttpResponse<byte[]> response) {
        return new String(response.body(), StandardCharsets.UTF_8);
    }
}
