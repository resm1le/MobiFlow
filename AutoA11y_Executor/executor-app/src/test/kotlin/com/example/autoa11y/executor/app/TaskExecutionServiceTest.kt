package com.example.autoa11y.executor.app

import android.content.Context
import android.content.Intent
import androidx.test.core.app.ApplicationProvider
import com.example.autoa11y.executor.control.ExecutorCapabilities
import com.example.autoa11y.executor.control.ExecutorClient
import com.example.autoa11y.executor.control.ClientCallResult
import com.example.autoa11y.executor.control.FinalTaskState
import com.example.autoa11y.executor.control.HeartbeatResponse
import com.example.autoa11y.executor.control.ExecutorIdentity
import com.example.autoa11y.executor.control.ArtifactDescriptor
import com.example.autoa11y.executor.control.RemoteTask
import com.example.autoa11y.executor.control.RunEventDto
import com.example.autoa11y.executor.reporting.ExecutorHealthSnapshot
import com.example.autoa11y.executor.reporting.ExecutorRuntimeState
import com.example.autoa11y.executor.reporting.LocalDeliveryStore
import com.example.autoa11y.drivers.shell.ShellBridge
import com.example.autoa11y.env.DeviceEnv
import com.example.autoa11y.env.EnvReport
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.android.controller.ServiceController
import java.io.File
import java.util.ArrayDeque
import java.util.concurrent.AbstractExecutorService
import java.util.concurrent.Callable
import java.util.concurrent.Delayed
import java.util.concurrent.Future
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

@RunWith(RobolectricTestRunner::class)
class TaskExecutionServiceTest {
    @After
    fun tearDown() {
        ExecutorRuntimeDependenciesHolder.reset()
    }

    @Test
    fun registerFailureTransitionsToDegradedAfterThreshold() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val client = FakeExecutorClient(context).apply {
            registerResponses.add(false)
            registerResponses.add(false)
            registerResponses.add(false)
        }
        val clock = MutableClock(1_000L)
        val deps = FakeRuntimeDependencies(client, clock)

        withService(deps) { service ->
            service.runControlTickForTest()
            assertEquals(ExecutorRuntimeState.RECOVERING, service.snapshotForTest().state)
            assertFalse(service.snapshotForTest().registered)

            clock.nowMs += 5_000L
            service.runControlTickForTest()
            assertEquals(ExecutorRuntimeState.RECOVERING, service.snapshotForTest().state)

            clock.nowMs += 10_000L
            service.runControlTickForTest()
            assertEquals(ExecutorRuntimeState.DEGRADED, service.snapshotForTest().state)
            assertEquals("register_failed", service.snapshotForTest().lastError)
        }
    }

    @Test
    fun successfulRegisterAndEmptyClaimLeavesServicePolling() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val client = FakeExecutorClient(context).apply {
            registerResponses.add(true)
            heartbeatResponses.add(true)
        }
        val deps = FakeRuntimeDependencies(client, MutableClock(5_000L))

        withService(deps) { service ->
            service.runControlTickForTest()

            val snapshot = service.snapshotForTest()
            assertTrue(snapshot.registered)
            assertEquals(ExecutorRuntimeState.POLLING, snapshot.state)
            assertEquals("idle", snapshot.lastMessage)
            assertTrue(snapshot.health.backendReachable)
            assertTrue(snapshot.health.lastRegisterOk)
            assertTrue(snapshot.health.lastHeartbeatOk)
        }
    }

    @Test
    fun registerReportsInstalledProfilesAsPackageNames() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val client = FakeExecutorClient(context).apply {
            registerResponses.add(true)
            heartbeatResponses.add(true)
        }
        val deps = FakeRuntimeDependencies(client, MutableClock(6_000L))

        withService(deps) { service ->
            service.runControlTickForTest()

            val identity = client.registerCalls.single()
            assertEquals(
                listOf(
                    "com.google.android.apps.maps",
                    "com.zhiliaoapp.musically",
                    "com.zzkko"
                ),
                identity.installedProfiles
            )
        }
    }

    @Test
    fun stopActionMarksServiceIdle() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val deps = FakeRuntimeDependencies(FakeExecutorClient(context), MutableClock(9_000L))

        withService(deps) { service ->
            val intent = Intent(context, TaskExecutionService::class.java).apply {
                action = TaskExecutionService.ACTION_STOP_EXECUTOR_LOOP
            }

            service.onStartCommand(intent, 0, 1)

            val snapshot = service.snapshotForTest()
            assertEquals(ExecutorRuntimeState.IDLE, snapshot.state)
            assertEquals("executor stopped by user", snapshot.lastMessage)
        }
    }

    @Test
    fun runTaskWithMissingAccessibilityDegradesAndReportsFailure() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val client = FakeExecutorClient(context)
        val clock = MutableClock(12_000L)
        val deps = FakeRuntimeDependencies(client, clock).apply {
            capabilities = healthyCapabilities(accessibilityEnabled = false)
            health = healthyHealth(clock = clock, accessibilityEnabled = false)
            packageInstalled = true
        }

        withService(deps) { service ->
            val task = RemoteTask(
                taskId = "task-1",
                attemptId = "attempt-1",
                runId = "run-from-claim",
                profilePackage = "com.google.android.apps.maps"
            )
            val intent = Intent(context, TaskExecutionService::class.java).apply {
                action = TaskExecutionService.ACTION_RUN_TASK
                putExtra("extra_task_json", task.toJson().toString())
            }

            service.onStartCommand(intent, 0, 1)

            val snapshot = service.snapshotForTest()
            assertEquals(ExecutorRuntimeState.DEGRADED, snapshot.state)
            assertEquals("a11y_unavailable", snapshot.lastError)
            assertEquals(1, client.finishCalls.size)
            assertEquals("run-from-claim", client.finishCalls.single().runId)
            assertEquals(FinalTaskState.PRECHECK_FAILED, client.finishCalls.single().status)
            assertEquals("a11y unavailable", client.finishCalls.single().message)
        }
    }

    @Test
    fun runTaskWithExpiredLeaseFailsBeforeExecution() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val client = FakeExecutorClient(context)
        val clock = MutableClock(20_000L)
        val deps = FakeRuntimeDependencies(client, clock).apply {
            capabilities = healthyCapabilities()
            health = healthyHealth(clock = clock)
            packageInstalled = true
        }

        withService(deps) { service ->
            val task = RemoteTask(
                taskId = "task-expired",
                attemptId = "attempt-expired",
                profilePackage = "com.google.android.apps.maps",
                leaseExpireAt = 19_000L
            )
            val intent = Intent(context, TaskExecutionService::class.java).apply {
                action = TaskExecutionService.ACTION_RUN_TASK
                putExtra("extra_task_json", task.toJson().toString())
            }

            service.onStartCommand(intent, 0, 1)

            val snapshot = service.snapshotForTest()
            assertEquals(ExecutorRuntimeState.DEGRADED, snapshot.state)
            assertEquals("lease_expired", snapshot.lastError)
        }
    }

    private fun withService(
        deps: FakeRuntimeDependencies,
        block: (TaskExecutionService) -> Unit
    ) {
        ExecutorRuntimeDependenciesHolder.current = deps
        val controller: ServiceController<TaskExecutionService> =
            Robolectric.buildService(TaskExecutionService::class.java).create()
        val service = controller.get()
        try {
            block(service)
        } finally {
            controller.destroy()
        }
    }

    private class MutableClock(var nowMs: Long)

    private class FakeRuntimeDependencies(
        private val client: FakeExecutorClient,
        private val clock: MutableClock
    ) : ExecutorRuntimeDependencies {
        var capabilities: ExecutorCapabilities = healthyCapabilities()
        var health: ExecutorHealthSnapshot = healthyHealth(clock)
        var packageInstalled: Boolean = true
        private val controlExecutor = NoOpScheduledExecutorService()

        override fun createExecutorClient(context: Context): ExecutorClient = client

        override fun createDeliveryStore(context: Context): LocalDeliveryStore =
            LocalDeliveryStore(File(context.filesDir, "test-buffer-${clock.nowMs}"))

        override fun createShellBridge(context: Context): ShellBridge = ShellBridge(context)

        override fun createDeviceEnv(context: Context, shell: ShellBridge): DeviceEnv =
            object : DeviceEnv {
                override fun prepare(): EnvReport = EnvReport(ok = true, details = emptyMap())
                override fun restore(): EnvReport = EnvReport(ok = true, details = emptyMap())
            }

        override fun createTaskExecutor() = ImmediateExecutorService()

        override fun createControlExecutor(): ScheduledExecutorService = controlExecutor

        override fun collectCapabilities(context: Context, forceRefresh: Boolean): ExecutorCapabilities =
            capabilities

        override fun collectHealth(
            context: Context,
            backendReachable: Boolean,
            lastRegisterOk: Boolean,
            lastHeartbeatOk: Boolean,
            degradedReason: String?,
            forceRefresh: Boolean
        ): ExecutorHealthSnapshot = health.copy(
            backendReachable = backendReachable,
            lastRegisterOk = lastRegisterOk,
            lastHeartbeatOk = lastHeartbeatOk,
            degradedReason = degradedReason,
            lastCheckedAt = nowMs()
        )

        override fun isPackageInstalled(context: Context, packageName: String): Boolean = packageInstalled

        override fun nowMs(): Long = clock.nowMs

        override fun shouldAutoStartLoop(): Boolean = false
    }

    private class FakeExecutorClient(context: Context) : ExecutorClient(context) {
        val registerResponses = ArrayDeque<Boolean>()
        val heartbeatResponses = ArrayDeque<Boolean>()
        val claimResponses = ArrayDeque<RemoteTask?>()
        val finishCalls = mutableListOf<FinishCall>()
        val registerCalls = mutableListOf<ExecutorIdentity>()

        data class FinishCall(
            val attemptId: String,
            val taskId: String,
            val runId: String,
            val status: FinalTaskState,
            val message: String,
            val preflightSummary: com.example.autoa11y.executor.control.PreflightSummary? = null,
            val failureDetail: com.example.autoa11y.executor.control.FailureDetail? = null
        )

        override fun registerDetailed(identity: ExecutorIdentity): ClientCallResult<org.json.JSONObject> =
            ClientCallResult(
                ok = if (registerResponses.isEmpty()) true else registerResponses.removeFirst(),
                body = org.json.JSONObject(),
                retryable = true
            ).also {
                registerCalls += identity
            }

        override fun heartbeatDetailed(identity: ExecutorIdentity, currentAttemptId: String?): ClientCallResult<HeartbeatResponse> =
            ClientCallResult(
                ok = if (heartbeatResponses.isEmpty()) true else heartbeatResponses.removeFirst(),
                body = HeartbeatResponse(registered = true),
                retryable = true
            )

        override fun claimTaskDetailed(identity: ExecutorIdentity): ClientCallResult<RemoteTask?> =
            ClientCallResult(
                ok = true,
                body = if (claimResponses.isEmpty()) null else claimResponses.removeFirst(),
                retryable = false
            )

        override fun reportTaskStartDetailed(task: RemoteTask, runId: String): ClientCallResult<org.json.JSONObject> =
            ClientCallResult(ok = true, body = org.json.JSONObject(), retryable = false)

        override fun reportEventsDetailed(attemptId: String, events: List<RunEventDto>): ClientCallResult<org.json.JSONObject> =
            ClientCallResult(ok = true, body = org.json.JSONObject(), retryable = false)

        override fun reportTaskFinishDetailed(
            attemptId: String,
            taskId: String,
            runId: String,
            status: FinalTaskState,
            message: String
        ): ClientCallResult<org.json.JSONObject> {
            finishCalls += FinishCall(attemptId, taskId, runId, status, message)
            return ClientCallResult(ok = true, body = org.json.JSONObject(), retryable = false)
        }

        override fun reportTaskFinishDetailed(
            attemptId: String,
            taskId: String,
            runId: String,
            status: FinalTaskState,
            message: String,
            preflightSummary: com.example.autoa11y.executor.control.PreflightSummary?,
            failureDetail: com.example.autoa11y.executor.control.FailureDetail?
        ): ClientCallResult<org.json.JSONObject> {
            finishCalls += FinishCall(attemptId, taskId, runId, status, message, preflightSummary, failureDetail)
            return ClientCallResult(ok = true, body = org.json.JSONObject(), retryable = false)
        }

        override fun uploadArtifactDetailed(attemptId: String, artifact: ArtifactDescriptor): ClientCallResult<Unit> =
            ClientCallResult(ok = true, body = Unit, retryable = false)
    }

    private class ImmediateExecutorService : AbstractExecutorService() {
        @Volatile
        private var shutdown = false

        override fun shutdown() {
            shutdown = true
        }

        override fun shutdownNow(): MutableList<Runnable> {
            shutdown = true
            return mutableListOf()
        }

        override fun isShutdown(): Boolean = shutdown

        override fun isTerminated(): Boolean = shutdown

        override fun awaitTermination(timeout: Long, unit: TimeUnit): Boolean = true

        override fun execute(command: Runnable) {
            check(!shutdown) { "executor already shutdown" }
            command.run()
        }
    }

    private class NoOpScheduledExecutorService : ScheduledExecutorService {
        @Volatile
        private var shutdown = false

        override fun shutdown() {
            shutdown = true
        }

        override fun shutdownNow(): MutableList<Runnable> {
            shutdown = true
            return mutableListOf()
        }

        override fun isShutdown(): Boolean = shutdown

        override fun isTerminated(): Boolean = shutdown

        override fun awaitTermination(timeout: Long, unit: TimeUnit): Boolean = true

        override fun <T : Any?> submit(task: Callable<T>): Future<T> = CompletedFuture(task.call())

        override fun <T : Any?> submit(task: Runnable, result: T): Future<T> {
            task.run()
            return CompletedFuture(result)
        }

        override fun submit(task: Runnable): Future<*> {
            task.run()
            return CompletedFuture(Unit)
        }

        override fun <T : Any?> invokeAll(tasks: MutableCollection<out Callable<T>>): MutableList<Future<T>> =
            tasks.map { CompletedFuture(it.call()) }.toMutableList()

        override fun <T : Any?> invokeAll(
            tasks: MutableCollection<out Callable<T>>,
            timeout: Long,
            unit: TimeUnit
        ): MutableList<Future<T>> = invokeAll(tasks)

        override fun <T : Any?> invokeAny(tasks: MutableCollection<out Callable<T>>): T =
            tasks.first().call()

        override fun <T : Any?> invokeAny(
            tasks: MutableCollection<out Callable<T>>,
            timeout: Long,
            unit: TimeUnit
        ): T = invokeAny(tasks)

        override fun execute(command: Runnable) {
            command.run()
        }

        override fun schedule(command: Runnable, delay: Long, unit: TimeUnit): ScheduledFuture<*> =
            CompletedScheduledFuture(Unit)

        override fun <V : Any?> schedule(callable: Callable<V>, delay: Long, unit: TimeUnit): ScheduledFuture<V> =
            CompletedScheduledFuture(callable.call())

        override fun scheduleAtFixedRate(
            command: Runnable,
            initialDelay: Long,
            period: Long,
            unit: TimeUnit
        ): ScheduledFuture<*> = CompletedScheduledFuture(Unit)

        override fun scheduleWithFixedDelay(
            command: Runnable,
            initialDelay: Long,
            delay: Long,
            unit: TimeUnit
        ): ScheduledFuture<*> = CompletedScheduledFuture(Unit)
    }

    private class CompletedFuture<T>(private val value: T) : Future<T> {
        override fun cancel(mayInterruptIfRunning: Boolean): Boolean = false
        override fun isCancelled(): Boolean = false
        override fun isDone(): Boolean = true
        override fun get(): T = value
        override fun get(timeout: Long, unit: TimeUnit): T = value
    }

    private class CompletedScheduledFuture<T>(private val value: T) : ScheduledFuture<T> {
        override fun getDelay(unit: TimeUnit): Long = 0L
        override fun compareTo(other: Delayed): Int = 0
        override fun cancel(mayInterruptIfRunning: Boolean): Boolean = false
        override fun isCancelled(): Boolean = false
        override fun isDone(): Boolean = true
        override fun get(): T = value
        override fun get(timeout: Long, unit: TimeUnit): T = value
    }

    companion object {
        private fun healthyCapabilities(accessibilityEnabled: Boolean = true): ExecutorCapabilities =
            ExecutorCapabilities(
                accessibilityEnabled = accessibilityEnabled,
                rootAvailable = true,
                shellAvailable = true,
                networkIsolationAvailable = true
            )

        private fun healthyHealth(
            clock: MutableClock,
            accessibilityEnabled: Boolean = true
        ): ExecutorHealthSnapshot = ExecutorHealthSnapshot(
            accessibilityEnabled = accessibilityEnabled,
            rootAvailable = true,
            shellAvailable = true,
            networkIsolationAvailable = true,
            backendReachable = false,
            lastRegisterOk = false,
            lastHeartbeatOk = false,
            authConfigured = false,
            bufferedDeliveryCount = 0,
            degradedReason = null,
            lastCheckedAt = clock.nowMs
        )
    }
}
