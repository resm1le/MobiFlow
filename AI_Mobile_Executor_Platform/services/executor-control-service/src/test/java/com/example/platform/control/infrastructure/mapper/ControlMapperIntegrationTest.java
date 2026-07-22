package com.example.platform.control.infrastructure.mapper;

import com.example.platform.control.ExecutorControlServiceApplication;
import com.example.platform.control.application.JsonCodec;
import com.example.platform.control.domain.DomainValues;
import com.example.platform.control.domain.PersistenceModels.AiFailureTriageResultEntity;
import com.example.platform.control.domain.PersistenceModels.AiRunSummaryResultEntity;
import com.example.platform.control.domain.PersistenceModels.ArtifactUploadSessionEntity;
import com.example.platform.control.domain.PersistenceModels.DeviceRuntimeStateEntity;
import com.example.platform.control.domain.PersistenceModels.ExperimentRunEntity;
import com.example.platform.control.domain.PersistenceModels.ExperimentRunTargetEntity;
import com.example.platform.control.domain.PersistenceModels.RunEventEntity;
import com.example.platform.control.domain.PersistenceModels.TaskAttemptEntity;
import com.example.platform.control.domain.PersistenceModels.TaskEntity;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ExecutorControlServiceApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("test")
@Testcontainers(disabledWithoutDocker = true)
class ControlMapperIntegrationTest {

    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("executor_platform")
            .withUsername("test")
            .withPassword("test");

    private static ExecutorService executorService;

    @Autowired
    private TaskMapper taskMapper;

    @Autowired
    private TaskAttemptMapper taskAttemptMapper;

    @Autowired
    private DeviceRuntimeStateMapper deviceRuntimeStateMapper;

    @Autowired
    private ExperimentRunMapper experimentRunMapper;

    @Autowired
    private ExperimentRunTargetMapper experimentRunTargetMapper;

    @Autowired
    private RunEventMapper runEventMapper;

    @Autowired
    private ArtifactUploadSessionMapper artifactUploadSessionMapper;

    @Autowired
    private AiRunSummaryResultMapper aiRunSummaryResultMapper;

    @Autowired
    private AiFailureTriageResultMapper aiFailureTriageResultMapper;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private Flyway flyway;

    private final JsonCodec jsonCodec = new JsonCodec(new com.fasterxml.jackson.databind.ObjectMapper());

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
    }

    @BeforeAll
    static void beforeAll() {
        executorService = Executors.newCachedThreadPool();
    }

    @AfterAll
    static void afterAll() {
        if (executorService != null) {
            executorService.shutdownNow();
        }
    }

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
    void claimQueryFiltersQueuedTasksByPriorityAndAge() {
        insertTask(task("task-queued-old-high", 100, 100L, DomainValues.TASK_STATUS_QUEUED));
        insertTask(task("task-queued-new-high", 100, 200L, DomainValues.TASK_STATUS_QUEUED));
        insertTask(task("task-queued-low", 10, 300L, DomainValues.TASK_STATUS_QUEUED));
        insertTask(task("task-running", 999, 50L, DomainValues.TASK_STATUS_RUNNING));

        List<String> taskIds = inNewTransaction(() -> taskMapper.findClaimableQueuedTasks("device-1", 10))
                .stream()
                .map(TaskEntity::getTaskId)
                .toList();

        assertEquals(List.of("task-queued-old-high", "task-queued-new-high", "task-queued-low"), taskIds);
    }

    @Test
    void claimQueryRespectsTargetDeviceBinding() {
        TaskEntity sharedTask = task("task-shared", 100, 100L, DomainValues.TASK_STATUS_QUEUED);
        TaskEntity pinnedTask = task("task-pinned", 90, 200L, DomainValues.TASK_STATUS_QUEUED);
        pinnedTask.setTargetDeviceId("device-1");
        TaskEntity otherDeviceTask = task("task-other-device", 95, 150L, DomainValues.TASK_STATUS_QUEUED);
        otherDeviceTask.setTargetDeviceId("device-2");
        insertTask(sharedTask);
        insertTask(pinnedTask);
        insertTask(otherDeviceTask);

        List<String> taskIds = inNewTransaction(() -> taskMapper.findClaimableQueuedTasks("device-1", 10))
                .stream()
                .map(TaskEntity::getTaskId)
                .toList();

        assertEquals(List.of("task-shared", "task-pinned"), taskIds);
    }

    @Test
    void heterogeneousPinnedTasksKeepTheirProfileAndPayloadAtClaim() {
        TaskEntity textChat = task("task-text-chat", 100, 100L, DomainValues.TASK_STATUS_QUEUED);
        textChat.setTargetDeviceId("device-1");
        textChat.setProfilePackage("com.tencent.mm");
        textChat.setTaskPayloadJson("{\"goal\":\"text chat\",\"waypoint_sequence\":{\"sequence_id\":\"wechat.text_chat.v1\"}}");
        TaskEntity videoCall = task("task-video-call", 100, 100L, DomainValues.TASK_STATUS_QUEUED);
        videoCall.setTargetDeviceId("device-2");
        videoCall.setProfilePackage("com.demo.video");
        videoCall.setTaskPayloadJson("{\"goal\":\"video call\",\"waypoint_sequence\":{\"sequence_id\":\"demo.video_call.v1\"}}");
        insertTask(textChat);
        insertTask(videoCall);

        TaskEntity deviceOneTask = inNewTransaction(() -> taskMapper.findClaimableQueuedTasks("device-1", 1)).get(0);
        TaskEntity deviceTwoTask = inNewTransaction(() -> taskMapper.findClaimableQueuedTasks("device-2", 1)).get(0);

        assertEquals("task-text-chat", deviceOneTask.getTaskId());
        assertEquals("com.tencent.mm", deviceOneTask.getProfilePackage());
        assertEquals("wechat.text_chat.v1", jsonCodec.readMap(
                jsonCodec.write(jsonCodec.readMap(deviceOneTask.getTaskPayloadJson()).get("waypoint_sequence"))
        ).get("sequence_id"));
        assertEquals("task-video-call", deviceTwoTask.getTaskId());
        assertEquals("com.demo.video", deviceTwoTask.getProfilePackage());
        assertEquals("demo.video_call.v1", jsonCodec.readMap(
                jsonCodec.write(jsonCodec.readMap(deviceTwoTask.getTaskPayloadJson()).get("waypoint_sequence"))
        ).get("sequence_id"));
    }

    @Test
    void claimQuerySkipsLockedRowsAcrossTransactions() throws Exception {
        insertTask(task("task-1", 100, 100L, DomainValues.TASK_STATUS_QUEUED));
        insertTask(task("task-2", 100, 200L, DomainValues.TASK_STATUS_QUEUED));

        CountDownLatch rowLocked = new CountDownLatch(1);
        CountDownLatch releaseLock = new CountDownLatch(1);

        Future<List<String>> firstSelection = executorService.submit(() -> inNewTransaction(() -> {
            List<TaskEntity> tasks = taskMapper.findClaimableQueuedTasks("device-1", 1);
            rowLocked.countDown();
            awaitLatch(releaseLock);
            return tasks.stream().map(TaskEntity::getTaskId).toList();
        }));

        assertTrue(rowLocked.await(5, TimeUnit.SECONDS));

        List<String> secondSelection = inNewTransaction(() -> taskMapper.findClaimableQueuedTasks("device-1", 20))
                .stream()
                .map(TaskEntity::getTaskId)
                .toList();

        releaseLock.countDown();

        assertEquals(List.of("task-1"), firstSelection.get(5, TimeUnit.SECONDS));
        assertFalse(secondSelection.contains("task-1"));
    }

    @Test
    void concurrentPinnedClaimsSelectDifferentDeviceTasks() throws Exception {
        TaskEntity deviceOneTask = task("task-device-1", 100, 100L, DomainValues.TASK_STATUS_QUEUED);
        deviceOneTask.setTargetDeviceId("device-1");
        TaskEntity deviceTwoTask = task("task-device-2", 100, 100L, DomainValues.TASK_STATUS_QUEUED);
        deviceTwoTask.setTargetDeviceId("device-2");
        insertTask(deviceOneTask);
        insertTask(deviceTwoTask);

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        Future<String> deviceOneClaim = executorService.submit(() -> {
            ready.countDown();
            awaitLatch(start);
            return inNewTransaction(() -> taskMapper.findClaimableQueuedTasks("device-1", 1).get(0).getTaskId());
        });
        Future<String> deviceTwoClaim = executorService.submit(() -> {
            ready.countDown();
            awaitLatch(start);
            return inNewTransaction(() -> taskMapper.findClaimableQueuedTasks("device-2", 1).get(0).getTaskId());
        });

        assertTrue(ready.await(5, TimeUnit.SECONDS));
        start.countDown();

        assertEquals("task-device-1", deviceOneClaim.get(5, TimeUnit.SECONDS));
        assertEquals("task-device-2", deviceTwoClaim.get(5, TimeUnit.SECONDS));
    }

    @Test
    void attemptMapperRenewsLeaseAndFinishesOnlyActiveAttempts() {
        long now = System.currentTimeMillis();
        TaskAttemptEntity activeAttempt = attempt("attempt-active", DomainValues.ATTEMPT_STATUS_RUNNING, now + 60_000L);
        TaskAttemptEntity finishedAttempt = attempt("attempt-finished", DomainValues.ATTEMPT_STATUS_SUCCEEDED, now + 60_000L);
        taskAttemptMapper.insert(activeAttempt);
        taskAttemptMapper.insert(finishedAttempt);

        assertEquals(1, taskAttemptMapper.countActiveAttempt("device-1", "attempt-active"));
        assertEquals(0, taskAttemptMapper.countActiveAttempt("device-1", "attempt-finished"));

        inNewTransaction(() -> taskAttemptMapper.renewLease("attempt-active", "device-1", now + 120_000L, now + 1_000L));
        inNewTransaction(() -> taskAttemptMapper.renewLease("attempt-finished", "device-1", now + 120_000L, now + 1_000L));
        assertEquals(now + 120_000L, leaseExpireAt("attempt-active"));
        assertEquals(now + 60_000L, leaseExpireAt("attempt-finished"));

        inNewTransaction(() -> taskAttemptMapper.finishIfActive(
                "attempt-active",
                DomainValues.ATTEMPT_STATUS_LEASE_EXPIRED,
                "LEASE_EXPIRED",
                "lease expired",
                null,
                null,
                now + 2_000L,
                now + 2_000L
        ));
        inNewTransaction(() -> taskAttemptMapper.finishIfActive(
                "attempt-finished",
                DomainValues.ATTEMPT_STATUS_LEASE_EXPIRED,
                "LEASE_EXPIRED",
                "lease expired",
                null,
                null,
                now + 2_000L,
                now + 2_000L
        ));

        assertEquals(DomainValues.ATTEMPT_STATUS_LEASE_EXPIRED, attemptStatus("attempt-active"));
        assertEquals("LEASE_EXPIRED", finalState("attempt-active"));
        assertEquals(DomainValues.ATTEMPT_STATUS_SUCCEEDED, attemptStatus("attempt-finished"));
    }

    @Test
    void runtimeMapperHonorsLockConditionalUpdateAndOfflineReconcile() throws Exception {
        long now = System.currentTimeMillis();
        deviceRuntimeStateMapper.upsert(runtime("device-1", DomainValues.DEVICE_STATUS_ONLINE, true, "attempt-1", now - 1_000L));
        deviceRuntimeStateMapper.upsert(runtime("device-2", DomainValues.DEVICE_STATUS_ONLINE, true, null, now - 1_000L));
        deviceRuntimeStateMapper.upsert(runtime("device-3", DomainValues.DEVICE_STATUS_QUIESCED, true, null, now - 1_000L));

        CountDownLatch rowLocked = new CountDownLatch(1);
        CountDownLatch releaseLock = new CountDownLatch(1);

        Future<Void> locker = executorService.submit(() -> {
            inNewTransaction(() -> {
                assertNotNull(deviceRuntimeStateMapper.lockByDeviceId("device-1"));
                rowLocked.countDown();
                awaitLatch(releaseLock);
                return null;
            });
            return null;
        });

        assertTrue(rowLocked.await(5, TimeUnit.SECONDS));

        Future<Integer> blockedUpdate = executorService.submit(() -> inNewTransaction(() ->
                deviceRuntimeStateMapper.updateAssignmentIfCurrent(
                        "device-1",
                        "attempt-1",
                        false,
                        DomainValues.DEVICE_STATUS_ONLINE,
                        null,
                        null,
                        null,
                        null,
                        now + 500L
                )));

        Thread.sleep(300L);
        assertFalse(blockedUpdate.isDone());
        releaseLock.countDown();

        locker.get(5, TimeUnit.SECONDS);
        assertEquals(1, blockedUpdate.get(5, TimeUnit.SECONDS));
        assertEquals(0, deviceRuntimeStateMapper.updateAssignmentIfCurrent(
                "device-1",
                "attempt-mismatch",
                false,
                DomainValues.DEVICE_STATUS_ONLINE,
                null,
                null,
                null,
                null,
                now + 750L
        ));
        assertEquals(1, deviceRuntimeStateMapper.updateAssignmentIfCurrent(
                "device-2",
                null,
                false,
                DomainValues.DEVICE_STATUS_ONLINE,
                null,
                null,
                null,
                null,
                now + 800L
        ));

        assertEquals(3, deviceRuntimeStateMapper.findAll().size());
        assertEquals(3, deviceRuntimeStateMapper.markOfflineStale(now - 500L, now + 1_000L));
        assertEquals(DomainValues.DEVICE_STATUS_OFFLINE, deviceRuntimeStateMapper.findById("device-1").getStatus());
        assertEquals(DomainValues.DEVICE_STATUS_OFFLINE, deviceRuntimeStateMapper.findById("device-2").getStatus());
        assertEquals(DomainValues.DEVICE_STATUS_QUIESCED, deviceRuntimeStateMapper.findById("device-3").getStatus());

        assertEquals(1, deviceRuntimeStateMapper.refreshHeartbeat(
                "device-3",
                "cfg-v2",
                2000L,
                now + 2_000L,
                "CANCEL_ATTEMPT",
                "{\"authConfigured\":true}",
                now + 2_000L
        ));
        DeviceRuntimeStateEntity refreshed = deviceRuntimeStateMapper.findById("device-3");
        assertEquals(DomainValues.DEVICE_STATUS_QUIESCED, refreshed.getStatus());
        assertTrue(refreshed.isOnline());
        assertEquals("cfg-v2", refreshed.getConfigVersion());
    }

    @Test
    void experimentRunMapperAllowsNullPoolIdForSingleDeviceRuns() {
        ExperimentRunEntity run = new ExperimentRunEntity();
        run.setRunId("run-single-device");
        run.setName("single-device");
        run.setDescription("single device run");
        run.setPoolId(null);
        run.setStatus(DomainValues.RUN_STATUS_QUEUED);
        run.setFinalState(null);
        run.setTaskType("PLUGIN_RUN");
        run.setProfilePackage("com.zhiliaoapp.musically");
        run.setTaskPayloadJson("{\"goal\":\"smoke\"}");
        run.setRunConfigJson("{\"loopCount\":1,\"budgetMs\":60000,\"loopIntervalMs\":0,\"networkIsolationEnabled\":false,\"pollIntervalMs\":15000,\"heartbeatIntervalMs\":30000}");
        run.setArtifactPolicyJson("{\"uploadLog\":true,\"uploadScreenshot\":true,\"uploadDump\":true}");
        run.setPriority(100);
        run.setLabelsJson("[\"single-device\"]");
        run.setSource("manual");
        run.setCreatedBy("tester");
        run.setMaxRetriesPerDevice(0);
        run.setQueueTimeoutMs(90000L);
        run.setCancelRequested(false);
        run.setCreatedAt(1_000L);
        run.setUpdatedAt(1_000L);

        experimentRunMapper.insert(run);

        ExperimentRunEntity persisted = experimentRunMapper.findById("run-single-device");
        assertNotNull(persisted);
        assertEquals("run-single-device", persisted.getRunId());
        assertEquals(null, persisted.getPoolId());
        assertEquals("PLUGIN_RUN", persisted.getTaskType());
    }

    @Test
    void heterogeneousRunAndTargetSequenceRoundTrip() {
        ExperimentRunEntity run = new ExperimentRunEntity();
        run.setRunId("run-heterogeneous");
        run.setName("heterogeneous");
        run.setPoolId(null);
        run.setStatus(DomainValues.RUN_STATUS_QUEUED);
        run.setTaskType("PLUGIN_RUN");
        run.setProfilePackage(null);
        run.setTaskPayloadJson("{}");
        run.setRunConfigJson("{\"loopCount\":1}");
        run.setArtifactPolicyJson("{\"uploadLog\":true}");
        run.setPriority(100);
        run.setLabelsJson("[]");
        run.setSource("agent");
        run.setCreatedBy("agent");
        run.setMaxRetriesPerDevice(1);
        run.setQueueTimeoutMs(300_000);
        run.setCreatedAt(1_000);
        run.setUpdatedAt(1_000);
        experimentRunMapper.insert(run);

        ExperimentRunTargetEntity target = new ExperimentRunTargetEntity();
        target.setRunTargetId("target-heterogeneous");
        target.setRunId(run.getRunId());
        target.setDeviceId("device-1");
        target.setSequenceId("wechat.text_chat.v1");
        target.setStatus(DomainValues.RUN_TARGET_STATUS_QUEUED);
        target.setAttemptCount(1);
        target.setCreatedAt(1_000);
        target.setUpdatedAt(1_000);
        experimentRunTargetMapper.insert(target);

        assertEquals(null, experimentRunMapper.findById(run.getRunId()).getProfilePackage());
        ExperimentRunTargetEntity persisted = experimentRunTargetMapper.findById(target.getRunTargetId());
        assertEquals("wechat.text_chat.v1", persisted.getSequenceId());
        assertEquals("wechat.text_chat.v1", experimentRunTargetMapper.lockById(target.getRunTargetId()).getSequenceId());
        assertEquals("wechat.text_chat.v1", experimentRunTargetMapper.findByRunId(run.getRunId()).get(0).getSequenceId());
    }

    @Test
    void runEventMapperBatchInsertPersistsMultipleRowsInOrder() {
        List<RunEventEntity> events = List.of(
                event("attempt-1", "task-1", "device-1", "run-1", "STEP_END", "first", 1000L),
                event("attempt-1", "task-1", "device-1", "run-1", "ACTION_END", "second", 1001L)
        );

        runEventMapper.insertBatch(events);

        List<RunEventEntity> persisted = runEventMapper.findByAttemptId("attempt-1");
        assertEquals(2, persisted.size());
        assertEquals(List.of("STEP_END", "ACTION_END"), persisted.stream().map(RunEventEntity::getEventType).toList());
        assertTrue(persisted.stream().allMatch(event -> event.getEventKey() == null));
        assertTrue(persisted.stream().allMatch(event -> event.getPayloadJson() == null));
    }

    @Test
    void runEventMapperPersistsJsonAndNoMutationUpsertPreservesFirstEvent() {
        RunEventEntity original = event(
                "attempt-waypoint",
                "task-waypoint",
                "device-waypoint",
                "run-waypoint",
                "WAYPOINT_SEGMENT",
                "waypoint_segment:0:COMPLETE",
                1_500L
        );
        original.setEventKey("waypoint:0");
        original.setState("COMPLETE");
        original.setStepIndex(0);
        original.setActionIndex(null);
        original.setPayloadJson("{\"sequence_id\":\"sequence-1\",\"step_id\":\"logged_in\",\"deviceId\":\"device-waypoint\"}");
        runEventMapper.insertBatchNoMutation(List.of(original));
        runEventMapper.insertBatchNoMutation(List.of(original));

        RunEventEntity conflicting = event(
                "attempt-waypoint",
                "task-waypoint",
                "device-waypoint",
                "run-waypoint",
                "WAYPOINT_SEGMENT",
                "conflicting-message",
                9_999L
        );
        conflicting.setEventKey("waypoint:0");
        conflicting.setState("INCOMPLETE");
        conflicting.setStepIndex(0);
        conflicting.setActionIndex(null);
        conflicting.setPayloadJson("{\"sequence_id\":\"sequence-1\",\"step_id\":\"different\",\"deviceId\":\"device-waypoint\"}");
        runEventMapper.insertBatchNoMutation(List.of(conflicting));

        List<RunEventEntity> persisted = runEventMapper.findByAttemptIdAndEventKeys(
                "attempt-waypoint",
                List.of("waypoint:0")
        );
        assertEquals(1, persisted.size());
        RunEventEntity event = persisted.get(0);
        assertEquals("waypoint_segment:0:COMPLETE", event.getMessage());
        assertEquals("COMPLETE", event.getState());
        assertEquals(1_500L, event.getTs());
        assertEquals(
                Map.of(
                        "sequence_id", "sequence-1",
                        "step_id", "logged_in",
                        "deviceId", "device-waypoint"
                ),
                jsonCodec.readMap(event.getPayloadJson())
        );

        RunEventEntity retryAttemptEvent = event(
                "attempt-waypoint-retry",
                "task-waypoint-retry",
                "device-waypoint",
                "run-waypoint",
                "WAYPOINT_SEGMENT",
                "waypoint_segment:0:COMPLETE",
                2_500L
        );
        retryAttemptEvent.setEventKey("waypoint:0");
        retryAttemptEvent.setState("COMPLETE");
        retryAttemptEvent.setStepIndex(0);
        retryAttemptEvent.setActionIndex(null);
        retryAttemptEvent.setPayloadJson(original.getPayloadJson());
        runEventMapper.insertBatchNoMutation(List.of(retryAttemptEvent));

        assertEquals(1, runEventMapper.findByAttemptId("attempt-waypoint").size());
        assertEquals(1, runEventMapper.findByAttemptId("attempt-waypoint-retry").size());
    }

    @Test
    void flywayAppliesWaypointLineageMigrations() {
        assertEquals("11", flyway.info().current().getVersion().getVersion());
        assertEquals(1, jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM information_schema.columns " +
                        "WHERE table_schema = DATABASE() AND table_name = 'run_events' AND column_name = 'event_key'",
                Integer.class
        ));
        assertEquals(1, jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM information_schema.statistics " +
                        "WHERE table_schema = DATABASE() AND table_name = 'run_events' " +
                        "AND index_name = 'uk_run_events_attempt_event_key'",
                Integer.class
        ));
    }

    @Test
    void taskAttemptLockSerializesSameAttemptWithoutBlockingDifferentAttempt() throws Exception {
        long now = System.currentTimeMillis();
        taskAttemptMapper.insert(attempt("attempt-lock-a", DomainValues.ATTEMPT_STATUS_SUCCEEDED, now));
        taskAttemptMapper.insert(attempt("attempt-lock-b", DomainValues.ATTEMPT_STATUS_SUCCEEDED, now));
        CountDownLatch rowLocked = new CountDownLatch(1);
        CountDownLatch releaseLock = new CountDownLatch(1);

        Future<Void> locker = executorService.submit(() -> {
            inNewTransaction(() -> {
                assertNotNull(taskAttemptMapper.lockById("attempt-lock-a"));
                rowLocked.countDown();
                awaitLatch(releaseLock);
                return null;
            });
            return null;
        });
        assertTrue(rowLocked.await(5, TimeUnit.SECONDS));

        Future<TaskAttemptEntity> sameAttempt = executorService.submit(() ->
                inNewTransaction(() -> taskAttemptMapper.lockById("attempt-lock-a"))
        );
        TaskAttemptEntity differentAttempt = inNewTransaction(() -> taskAttemptMapper.lockById("attempt-lock-b"));
        assertNotNull(differentAttempt);
        assertEquals("attempt-lock-b", differentAttempt.getAttemptId());
        Thread.sleep(300L);
        assertFalse(sameAttempt.isDone());

        releaseLock.countDown();
        locker.get(5, TimeUnit.SECONDS);
        assertEquals("attempt-lock-a", sameAttempt.get(5, TimeUnit.SECONDS).getAttemptId());
    }

    @Test
    void artifactUploadSessionMapperPersistsRefreshesAndExpiresSessions() {
        ArtifactUploadSessionEntity session = new ArtifactUploadSessionEntity();
        session.setArtifactId("artifact-1");
        session.setAttemptId("attempt-1");
        session.setTaskId("task-1");
        session.setDeviceId("device-1");
        session.setRunId("run-1");
        session.setArtifactType("screenshot");
        session.setFileName("screen.png");
        session.setMimeType("image/png");
        session.setDeclaredSizeBytes(100L);
        session.setObjectKey("artifacts/task-1/attempt-1/artifact-1/screen.png");
        session.setStatus("AUTHORIZED");
        session.setUploadExpiresAt(5_000L);
        session.setCreatedAt(1_000L);
        session.setUpdatedAt(1_000L);

        artifactUploadSessionMapper.insert(session);
        ArtifactUploadSessionEntity persisted = artifactUploadSessionMapper.findByArtifactId("artifact-1");
        assertNotNull(persisted);
        assertEquals("AUTHORIZED", persisted.getStatus());

        persisted.setStatus("AUTHORIZED");
        persisted.setUploadExpiresAt(10_000L);
        persisted.setUpdatedAt(2_000L);
        artifactUploadSessionMapper.update(persisted);
        assertEquals(10_000L, artifactUploadSessionMapper.findByArtifactId("artifact-1").getUploadExpiresAt());

        assertEquals(0, artifactUploadSessionMapper.findExpiredAuthorized(9_000L, 10).size());
        assertEquals(1, artifactUploadSessionMapper.findExpiredAuthorized(10_001L, 10).size());

        artifactUploadSessionMapper.markFinalized("artifact-1", 11_000L, 11_000L);
        assertEquals("FINALIZED", artifactUploadSessionMapper.findByArtifactId("artifact-1").getStatus());

        persisted.setStatus("AUTHORIZED");
        persisted.setUploadExpiresAt(12_000L);
        persisted.setUpdatedAt(12_000L);
        persisted.setFinalizedAt(null);
        artifactUploadSessionMapper.update(persisted);
        artifactUploadSessionMapper.markExpired("artifact-1", 13_000L);
        assertEquals("EXPIRED", artifactUploadSessionMapper.findByArtifactId("artifact-1").getStatus());
    }

    @Test
    void aiRunSummaryResultMapperFindsLatestCompletedSummaryByRunId() {
        AiRunSummaryResultEntity older = new AiRunSummaryResultEntity();
        older.setSummaryId("summary-old");
        older.setRunId("run-1");
        older.setContextJson("{\"runId\":\"run-1\"}");
        older.setResultJson("{\"summaryText\":\"older\"}");
        older.setValidationJson("{\"valid\":true,\"errors\":[],\"warnings\":[]}");
        older.setModelMetaJson("{\"provider\":\"stub\"}");
        older.setStatus(DomainValues.AI_RUN_SUMMARY_STATUS_READY);
        older.setCreatedAt(1_000L);
        older.setUpdatedAt(1_000L);
        aiRunSummaryResultMapper.insert(older);

        AiRunSummaryResultEntity latest = new AiRunSummaryResultEntity();
        latest.setSummaryId("summary-new");
        latest.setRunId("run-1");
        latest.setContextJson("{\"runId\":\"run-1\"}");
        latest.setResultJson("{\"summaryText\":\"latest\"}");
        latest.setValidationJson("{\"valid\":true,\"errors\":[],\"warnings\":[]}");
        latest.setModelMetaJson("{\"provider\":\"stub\"}");
        latest.setStatus(DomainValues.AI_RUN_SUMMARY_STATUS_READY);
        latest.setCreatedAt(2_000L);
        latest.setUpdatedAt(2_100L);
        aiRunSummaryResultMapper.insert(latest);

        AiRunSummaryResultEntity persisted = aiRunSummaryResultMapper.findLatestByRunId("run-1");
        assertNotNull(persisted);
        assertEquals("summary-new", persisted.getSummaryId());
        assertEquals("run-1", persisted.getRunId());
        assertEquals(Map.of("summaryText", "latest"), jsonCodec.readMap(persisted.getResultJson()));
        assertEquals(
                Map.of("valid", true, "errors", List.of(), "warnings", List.of()),
                jsonCodec.readMap(persisted.getValidationJson())
        );
    }

    @Test
    void aiFailureTriageResultMapperFindsLatestCompletedTriageByRunTargetId() {
        AiFailureTriageResultEntity older = new AiFailureTriageResultEntity();
        older.setTriageResultId("triage-old");
        older.setRunId("run-1");
        older.setRunTargetId("target-1");
        older.setAttemptId("attempt-1");
        older.setContextJson("{\"runTargetId\":\"target-1\"}");
        older.setResultJson("{\"failureCategory\":\"UNKNOWN\"}");
        older.setValidationJson("{\"valid\":true,\"errors\":[],\"warnings\":[]}");
        older.setModelMetaJson("{\"provider\":\"stub\"}");
        older.setStatus(DomainValues.AI_TRIAGE_STATUS_READY);
        older.setCreatedAt(3_000L);
        older.setUpdatedAt(3_000L);
        aiFailureTriageResultMapper.insert(older);

        AiFailureTriageResultEntity latest = new AiFailureTriageResultEntity();
        latest.setTriageResultId("triage-new");
        latest.setRunId("run-1");
        latest.setRunTargetId("target-1");
        latest.setAttemptId("attempt-2");
        latest.setContextJson("{\"runTargetId\":\"target-1\"}");
        latest.setResultJson("{\"failureCategory\":\"RUN_CANCELLED\"}");
        latest.setValidationJson("{\"valid\":true,\"errors\":[],\"warnings\":[]}");
        latest.setModelMetaJson("{\"provider\":\"stub\"}");
        latest.setStatus(DomainValues.AI_TRIAGE_STATUS_READY);
        latest.setCreatedAt(4_000L);
        latest.setUpdatedAt(4_100L);
        aiFailureTriageResultMapper.insert(latest);

        AiFailureTriageResultEntity persisted = aiFailureTriageResultMapper.findLatestByRunTargetId("target-1");
        assertNotNull(persisted);
        assertEquals("triage-new", persisted.getTriageResultId());
        assertEquals("target-1", persisted.getRunTargetId());
        assertEquals("run-1", persisted.getRunId());
        assertEquals(Map.of("failureCategory", "RUN_CANCELLED"), jsonCodec.readMap(persisted.getResultJson()));
        assertEquals(
                Map.of("valid", true, "errors", List.of(), "warnings", List.of()),
                jsonCodec.readMap(persisted.getValidationJson())
        );
    }

    private void insertTask(TaskEntity task) {
        taskMapper.insert(task);
    }

    private TaskEntity task(String taskId, int priority, long createdAt, String status) {
        TaskEntity task = new TaskEntity();
        task.setTaskId(taskId);
        task.setTaskType("PLUGIN_RUN");
        task.setProfilePackage("com.google.android.apps.maps");
        task.setTaskPayloadJson("{\"goal\":\"navigate\"}");
        task.setRunConfigJson("{\"loopCount\":1,\"budgetMs\":60000,\"loopIntervalMs\":0,\"networkIsolationEnabled\":false,\"pollIntervalMs\":15000,\"heartbeatIntervalMs\":30000}");
        task.setArtifactPolicyJson("{\"uploadLog\":true,\"uploadScreenshot\":true,\"uploadDump\":false}");
        task.setPriority(priority);
        task.setLabelsJson("[\"demo\"]");
        task.setSource("manual");
        task.setScheduleVersion("sched-v1");
        task.setIdempotencyKey("idem-" + taskId);
        task.setStatus(status);
        task.setCreatedBy("tester");
        task.setCreatedAt(createdAt);
        task.setUpdatedAt(createdAt);
        return task;
    }

    private TaskAttemptEntity attempt(String attemptId, String status, long leaseExpireAt) {
        TaskAttemptEntity attempt = new TaskAttemptEntity();
        attempt.setAttemptId(attemptId);
        attempt.setTaskId("task-1");
        attempt.setDeviceId("device-1");
        attempt.setRunId("run-" + attemptId);
        attempt.setStatus(status);
        attempt.setLeaseExpireAt(leaseExpireAt);
        attempt.setCreatedAt(1L);
        attempt.setUpdatedAt(1L);
        return attempt;
    }

    private Long leaseExpireAt(String attemptId) {
        return jdbcTemplate.queryForObject(
                "SELECT lease_expire_at FROM task_attempts WHERE attempt_id = ?",
                Long.class,
                attemptId
        );
    }

    private String attemptStatus(String attemptId) {
        return jdbcTemplate.queryForObject(
                "SELECT status FROM task_attempts WHERE attempt_id = ?",
                String.class,
                attemptId
        );
    }

    private String finalState(String attemptId) {
        return jdbcTemplate.queryForObject(
                "SELECT final_state FROM task_attempts WHERE attempt_id = ?",
                String.class,
                attemptId
        );
    }

    private DeviceRuntimeStateEntity runtime(String deviceId,
                                             String status,
                                             boolean online,
                                             String currentAttemptId,
                                             long lastHeartbeatAt) {
        DeviceRuntimeStateEntity runtime = new DeviceRuntimeStateEntity();
        runtime.setDeviceId(deviceId);
        runtime.setRegistered(true);
        runtime.setOnline(online);
        runtime.setBusy(currentAttemptId != null);
        runtime.setStatus(status);
        runtime.setCurrentTaskId(currentAttemptId == null ? null : "task-1");
        runtime.setCurrentAttemptId(currentAttemptId);
        runtime.setCurrentTaskType(currentAttemptId == null ? null : "PLUGIN_RUN");
        runtime.setConfigVersion("cfg-v1");
        runtime.setLeaseExpireAt(currentAttemptId == null ? null : 1000L);
        runtime.setLastHeartbeatAt(lastHeartbeatAt);
        runtime.setLastCommand(null);
        runtime.setHealthJson("{\"authConfigured\":true}");
        runtime.setUpdatedAt(lastHeartbeatAt);
        return runtime;
    }

    private RunEventEntity event(String attemptId,
                                 String taskId,
                                 String deviceId,
                                 String runId,
                                 String eventType,
                                 String message,
                                 long ts) {
        RunEventEntity event = new RunEventEntity();
        event.setAttemptId(attemptId);
        event.setTaskId(taskId);
        event.setDeviceId(deviceId);
        event.setRunId(runId);
        event.setScenarioId("scenario-1");
        event.setStepIndex(1);
        event.setActionIndex(1);
        event.setEventType(eventType);
        event.setState("ok");
        event.setCode(null);
        event.setMessage(message);
        event.setTs(ts);
        return event;
    }

    private <T> T inNewTransaction(TransactionWork<T> work) {
        TransactionTemplate transactionTemplate = new TransactionTemplate(transactionManager);
        transactionTemplate.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        return transactionTemplate.execute(status -> work.run());
    }

    private void awaitLatch(CountDownLatch latch) {
        try {
            assertTrue(latch.await(5, TimeUnit.SECONDS));
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while waiting for latch", exception);
        }
    }

    @FunctionalInterface
    private interface TransactionWork<T> {
        T run();
    }
}
