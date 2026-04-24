package com.example.autoa11y.executor.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.example.autoa11y.executor.control.ExecutorClient
import com.example.autoa11y.executor.control.ExecutorControlCommandType
import com.example.autoa11y.executor.control.ExecutorIdentity
import com.example.autoa11y.executor.control.ArtifactDescriptor
import com.example.autoa11y.executor.control.DeviceRegistrar
import com.example.autoa11y.executor.control.FailureDetail
import com.example.autoa11y.executor.control.FinalTaskState
import com.example.autoa11y.executor.control.HealthSnapshotPayload
import com.example.autoa11y.executor.control.PreflightSummary
import com.example.autoa11y.executor.control.RemoteTask
import com.example.autoa11y.executor.control.RunEventDto
import com.example.autoa11y.executor.control.TaskDispatcher
import com.example.autoa11y.executor.control.TaskPoller
import com.example.autoa11y.executor.reporting.ArtifactUploader
import com.example.autoa11y.executor.reporting.DeliveryFlusher
import com.example.autoa11y.executor.reporting.EventReporter
import com.example.autoa11y.executor.reporting.ExecutorHealthSnapshot
import com.example.autoa11y.executor.reporting.ExecutorRuntimeState
import com.example.autoa11y.executor.reporting.LocalDeliveryStore
import com.example.autoa11y.executor.reporting.RuntimeSnapshotStore
import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.drivers.a11y.A11yDriver
import com.example.autoa11y.drivers.a11y.A11yServiceHolder
import com.example.autoa11y.drivers.shell.ShellBridge
import com.example.autoa11y.drivers.shell.ShellDriver
import com.example.autoa11y.engine.TimeBoxedRunner
import com.example.autoa11y.env.NetworkIsolationManager
import com.example.autoa11y.monitor.RunLogger
import com.example.autoa11y.shared.AppConfig
import com.example.autoa11y.shared.Time
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

class TaskExecutionService : Service() {

    companion object {
        private const val TAG = "TaskExecutionService"
        private const val NOTIFICATION_ID = 31
        private const val CHANNEL_ID = "executor_exec_ch"
        private const val DEGRADED_THRESHOLD = 3

        const val ACTION_START_EXECUTOR_LOOP = "com.example.autoa11y.executor.app.START_EXECUTOR_LOOP"
        const val ACTION_STOP_EXECUTOR_LOOP = "com.example.autoa11y.executor.app.STOP_EXECUTOR_LOOP"
        const val ACTION_RUN_TASK = "com.example.autoa11y.executor.app.RUN_TASK"
        const val ACTION_RUN_FAKE_TASK = "com.example.autoa11y.executor.app.RUN_FAKE_TASK"
        const val ACTION_FORCE_HEALTH_CHECK = "com.example.autoa11y.executor.app.FORCE_HEALTH_CHECK"

        private const val EXTRA_TASK_JSON = "extra_task_json"
        private const val EXTRA_PROFILE_PACKAGE = "extra_profile_package"

        fun startExecutionLoop(context: android.content.Context) {
            AutomationSafetyManager.enableCurrentAutomation(context)
            val intent = Intent(context, TaskExecutionService::class.java).apply {
                action = ACTION_START_EXECUTOR_LOOP
            }
            context.startForegroundService(intent)
        }

        fun stopExecutionLoop(context: android.content.Context) {
            val intent = Intent(context, TaskExecutionService::class.java).apply {
                action = ACTION_STOP_EXECUTOR_LOOP
            }
            context.startService(intent)
        }

        fun requestHealthCheck(context: android.content.Context) {
            AutomationSafetyManager.enforceExclusiveOwner(context)
            val intent = Intent(context, TaskExecutionService::class.java).apply {
                action = ACTION_FORCE_HEALTH_CHECK
            }
            context.startForegroundService(intent)
        }

        fun runFakeTask(context: android.content.Context, profilePackage: String) {
            AutomationSafetyManager.enableCurrentAutomation(context)
            val intent = Intent(context, TaskExecutionService::class.java).apply {
                action = ACTION_RUN_FAKE_TASK
                putExtra(EXTRA_PROFILE_PACKAGE, profilePackage)
            }
            context.startForegroundService(intent)
        }
    }

    private data class PreflightResult(
        val ok: Boolean,
        val message: String,
        val error: String? = null,
        val targetProfilePackage: String,
        val networkIsolationRequired: Boolean,
        val capturedAt: Long = System.currentTimeMillis()
    ) {
        fun toSummary(): PreflightSummary = PreflightSummary(
            ok = ok,
            failureCode = error ?: "preflight_failed",
            failureMessage = message,
            targetProfilePackage = targetProfilePackage,
            networkIsolationRequired = networkIsolationRequired,
            capturedAt = capturedAt
        )
    }

    private lateinit var notificationManager: NotificationManager
    private lateinit var snapshotStore: RuntimeSnapshotStore
    private lateinit var client: ExecutorClient
    private lateinit var deliveryStore: LocalDeliveryStore
    private lateinit var eventReporter: EventReporter
    private lateinit var artifactUploader: ArtifactUploader
    private lateinit var deliveryFlusher: DeliveryFlusher
    private lateinit var dispatcher: TaskDispatcher
    private lateinit var registrar: DeviceRegistrar
    private lateinit var poller: TaskPoller
    private lateinit var runtimeDependencies: ExecutorRuntimeDependencies
    private lateinit var taskExecutor: ExecutorService
    private lateinit var controlExecutor: ScheduledExecutorService

    private val controlLoopState = ExecutorControlLoopState()

    @Volatile
    private var registered = false

    @Volatile
    private var controlLoopStarted = false

    @Volatile
    private var backendReachable = false

    @Volatile
    private var lastRegisterOk = false

    @Volatile
    private var lastHeartbeatOk = false

    @Volatile
    private var degradedReason: String? = null

    @Volatile
    private var configVersion: String? = null

    @Volatile
    private var lastHeartbeatAt: Long = 0L

    @Volatile
    private var lastCommand: String? = null

    @Volatile
    private var loopSuppressed = false

    @Volatile
    private var quiesced = false

    @Volatile
    private var cancelAttemptId: String? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        notificationManager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        AutomationSafetyManager.enforceExclusiveOwner(this)
        runtimeDependencies = ExecutorRuntimeDependenciesHolder.current
        snapshotStore = RuntimeSnapshotStore(this)
        client = runtimeDependencies.createExecutorClient(this)
        deliveryStore = runtimeDependencies.createDeliveryStore(this)
        eventReporter = EventReporter(client, deliveryStore)
        artifactUploader = ArtifactUploader(client, deliveryStore) { snapshotStore.read().deviceId }
        deliveryFlusher = DeliveryFlusher(client, deliveryStore)
        dispatcher = TaskDispatcher()
        registrar = DeviceRegistrar(client) { currentIdentity() }
        poller = TaskPoller(client) { currentIdentity() }
        taskExecutor = runtimeDependencies.createTaskExecutor()
        controlExecutor = runtimeDependencies.createControlExecutor()
        snapshotStore.updateLoopConfig(
            controlLoopState.config.pollIntervalMs,
            controlLoopState.config.heartbeatIntervalMs
        )
        refreshIdentityMetadata(forceRefresh = true)
        refreshHealth(forceRefresh = true)
        snapshotStore.updateState(ExecutorRuntimeState.IDLE, "executor created")
        startForegroundInternal("Executor idle")
        if (runtimeDependencies.shouldAutoStartLoop()) {
            ensureExecutorLoopRunning()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START_EXECUTOR_LOOP -> {
                loopSuppressed = false
                quiesced = false
                ensureExecutorLoopRunning()
            }

            ACTION_STOP_EXECUTOR_LOOP -> {
                loopSuppressed = true
                snapshotStore.markIdle("executor stopped by user")
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
                return START_NOT_STICKY
            }

            ACTION_FORCE_HEALTH_CHECK -> {
                ensureExecutorLoopRunning()
                safeControlTick(forceHealthRefresh = true)
            }

            ACTION_RUN_FAKE_TASK -> {
                loopSuppressed = false
                quiesced = false
                ensureExecutorLoopRunning()
                val profilePackage = intent.getStringExtra(EXTRA_PROFILE_PACKAGE)
                if (!profilePackage.isNullOrBlank()) {
                    val task = RemoteTask.fake(profilePackage)
                    applyControlConfig(task)
                    tryDispatch(task)
                }
            }

            ACTION_RUN_TASK -> {
                loopSuppressed = false
                quiesced = false
                ensureExecutorLoopRunning()
                val taskJson = intent.getStringExtra(EXTRA_TASK_JSON)
                if (!taskJson.isNullOrBlank()) {
                    runCatching { org.json.JSONObject(taskJson) }
                        .map(RemoteTask.Companion::fromJson)
                        .onSuccess {
                            applyControlConfig(it)
                            tryDispatch(it)
                        }
                        .onFailure { Log.w(TAG, "invalid task json err=${it.message}") }
                }
            }

            else -> ensureExecutorLoopRunning()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        controlLoopStarted = false
        controlExecutor.shutdownNow()
        taskExecutor.shutdownNow()
        eventReporter.close()
        NetworkIsolationManager.restore(applicationContext)
        super.onDestroy()
    }

    private fun ensureExecutorLoopRunning() {
        if (controlLoopStarted) return
        controlLoopStarted = true
        controlExecutor.scheduleWithFixedDelay(
            { safeControlTick() },
            0L,
            controlLoopState.config.tickIntervalMs,
            TimeUnit.MILLISECONDS
        )
    }

    private fun safeControlTick(forceHealthRefresh: Boolean = false) {
        runCatching {
            controlTick(forceHealthRefresh)
        }.onFailure { throwable ->
            Log.e(TAG, "controlTick failed: ${throwable.message}", throwable)
            degradedReason = throwable.message ?: "control_tick_failed"
            refreshHealth(forceRefresh = true)
            if (controlLoopState.consecutiveFailures() >= DEGRADED_THRESHOLD) {
                snapshotStore.markDegraded("control degraded", degradedReason ?: "control_tick_failed")
            } else {
                snapshotStore.updateState(
                    ExecutorRuntimeState.RECOVERING,
                    "control recovering",
                    error = degradedReason
                )
            }
        }
    }

    private fun controlTick(forceHealthRefresh: Boolean) {
        val now = runtimeDependencies.nowMs()
        val identity = currentIdentity(forceHealthRefresh)

        refreshIdentityMetadata(identity)
        snapshotStore.updateBackend(client.baseUrl, identity.deviceId)
        snapshotStore.updateLoopConfig(
            controlLoopState.config.pollIntervalMs,
            controlLoopState.config.heartbeatIntervalMs
        )
        refreshHealth(forceRefresh = forceHealthRefresh)
        deliveryFlusher.flush()
        snapshotStore.updateControlMetadata(configVersion, lastHeartbeatAt, lastCommand, dispatcher.currentLeaseExpireAt())

        if (loopSuppressed) {
            snapshotStore.updateState(ExecutorRuntimeState.IDLE, "loop suppressed")
            return
        }

        if (!registered && controlLoopState.shouldAttemptRegister(now)) {
            snapshotStore.updateState(ExecutorRuntimeState.REGISTERING, "registering")
            val ok = registrar.register()
            lastRegisterOk = ok
            backendReachable = ok
            if (ok) {
                registered = true
                degradedReason = null
                controlLoopState.onRegisterSuccess(now)
                snapshotStore.updateRegistration(true, "registered")
                refreshHealth(forceRefresh = true)
            } else {
                controlLoopState.onRegisterFailure(now)
                handleControlFailure("register_failed")
                return
            }
        }

        if (registered && controlLoopState.shouldSendHeartbeat(now)) {
            val response = client.heartbeatDetailed(identity, dispatcher.currentAttemptId())
            lastHeartbeatAt = now
            lastHeartbeatOk = response.ok
            backendReachable = response.ok
            if (response.ok) {
                configVersion = response.body?.configVersion ?: configVersion
                controlLoopState.onHeartbeatSuccess(now)
                degradedReason = null
                response.body?.runConfig?.let(controlLoopState::apply)
                response.body?.commands?.forEach { command ->
                    lastCommand = command.type.name
                    handleControlCommand(command.type, command.attemptId, now)
                }
                snapshotStore.updateRegistration(true, "heartbeat_ok")
            } else {
                controlLoopState.onHeartbeatFailure(now)
                handleControlFailure("heartbeat_failed")
                return
            }
            refreshHealth(forceRefresh = true)
        }

        if (registered && !quiesced && dispatcher.isIdle() && controlLoopState.shouldPoll(now)) {
            snapshotStore.updateState(ExecutorRuntimeState.POLLING, "polling")
            controlLoopState.onPoll(now)
            poller.claim()?.let { task ->
                applyControlConfig(task)
                tryDispatch(task)
                return
            }
            snapshotStore.updateState(ExecutorRuntimeState.POLLING, "idle")
        } else if (registered && quiesced && dispatcher.isIdle()) {
            snapshotStore.updateState(ExecutorRuntimeState.IDLE, "quiesced")
        } else if (!registered) {
            snapshotStore.updateState(ExecutorRuntimeState.RECOVERING, "waiting to register", degradedReason)
        }
    }

    private fun handleControlFailure(reason: String) {
        degradedReason = reason
        refreshHealth(forceRefresh = true)
        snapshotStore.updateRegistration(registered, reason, error = reason)
        if (controlLoopState.consecutiveFailures() >= DEGRADED_THRESHOLD) {
            snapshotStore.markDegraded("executor degraded", reason)
        } else {
            snapshotStore.updateState(ExecutorRuntimeState.RECOVERING, "retrying after $reason", error = reason)
        }
    }

    private fun applyControlConfig(task: RemoteTask) {
        controlLoopState.apply(task.configSnapshot)
        snapshotStore.updateLoopConfig(
            controlLoopState.config.pollIntervalMs,
            controlLoopState.config.heartbeatIntervalMs
        )
    }

    private fun tryDispatch(task: RemoteTask) {
        if (!dispatcher.tryBegin(task)) {
            snapshotStore.markIdle("busy, skip ${task.attemptId}")
            return
        }
        cancelAttemptId = cancelAttemptId.takeIf { it != task.attemptId }
        taskExecutor.execute { executeTask(task) }
    }

    private fun executeTask(task: RemoteTask) {
        val runId = task.runId ?: Time.runId()
        val identity = currentIdentity()
        if (isLeaseExpiredBeforeExecution(task)) {
            snapshotStore.markDegraded("lease expired", "lease_expired")
            eventReporter.reportTaskFinish(
                task.attemptId,
                task.taskId,
                identity.deviceId,
                runId,
                FinalTaskState.LEASE_EXPIRED,
                "lease expired before execution",
                failureDetail = failureDetail("lease_expired", "dispatch", "lease expired before execution")
            )
            dispatcher.finish(task.attemptId)
            return
        }
        val profile = ExecutorProfileRegistry.findByPackage(this, task.profilePackage)
        if (profile == null) {
            snapshotStore.markDegraded("profile missing", "profile_missing ${task.profilePackage}")
            eventReporter.reportTaskFinish(
                task.attemptId,
                task.taskId,
                identity.deviceId,
                runId,
                FinalTaskState.PRECHECK_FAILED,
                "profile missing",
                preflightSummary = preflightSummary("profile_missing", "profile missing", task.profilePackage, task.configSnapshot.networkIsolationEnabled)
            )
            dispatcher.finish(task.attemptId)
            return
        }

        val runConfig = task.configSnapshot
        val preflight = preflight(task.profilePackage, runConfig.networkIsolationEnabled)
        if (!preflight.ok) {
            snapshotStore.markDegraded(preflight.message, preflight.error ?: preflight.message)
            eventReporter.reportTaskFinish(
                task.attemptId,
                task.taskId,
                identity.deviceId,
                runId,
                FinalTaskState.PRECHECK_FAILED,
                preflight.message,
                preflightSummary = preflight.toSummary()
            )
            dispatcher.finish(task.attemptId)
            return
        }

        val a11ySvc = A11yServiceHolder.service ?: run {
            snapshotStore.markDegraded("a11y unavailable", "a11y_unavailable")
            eventReporter.reportTaskFinish(
                task.attemptId,
                task.taskId,
                identity.deviceId,
                runId,
                FinalTaskState.PRECHECK_FAILED,
                "a11y unavailable",
                preflightSummary = preflightSummary("a11y_unavailable", "a11y unavailable", task.profilePackage, runConfig.networkIsolationEnabled)
            )
            dispatcher.finish(task.attemptId)
            return
        }

        val shell = runtimeDependencies.createShellBridge(this)
        val deviceEnv = runtimeDependencies.createDeviceEnv(applicationContext, shell)
        val prepareReport = deviceEnv.prepare()
        if (!prepareReport.ok) {
            snapshotStore.markDegraded("device env prepare failed", "device_env_prepare_failed")
            eventReporter.reportTaskFinish(
                task.attemptId,
                task.taskId,
                identity.deviceId,
                runId,
                FinalTaskState.SYSTEM_ABORTED,
                "device env prepare failed",
                failureDetail = failureDetail("device_env_prepare_failed", "prepare", "device env prepare failed")
            )
            dispatcher.finish(task.attemptId)
            return
        }

        val logger = RunLogger(this, runId, profile.packageName)
        val observer = ExecutorExecutionObserver(task.attemptId, task.taskId, identity.deviceId, runId, eventReporter)
        val driver: Driver = A11yDriver(a11ySvc)
        val shellDriver = ShellDriver(this, shell)
        var finalState = FinalTaskState.SUCCESS
        var finalMessage = "run completed"

        snapshotStore.markTaskRunning(task, runId, "running ${task.profilePackage}")
        startForegroundInternal("Running ${task.profilePackage}")
        eventReporter.reportTaskStart(task, runId)
        eventReporter.reportEvent(
            RunEventDto(
                attemptId = task.attemptId,
                taskId = task.taskId,
                deviceId = identity.deviceId,
                runId = runId,
                eventType = "run_start",
                state = snapshotStore.read().state.name,
                message = "task started source=${task.source}"
            )
        )

        try {
            logger.logHeader(
                mapOf(
                    "attemptId" to task.attemptId,
                    "taskId" to task.taskId,
                    "profilePackage" to task.profilePackage,
                    "source" to task.source,
                    "backendUrl" to client.baseUrl,
                    "executorState" to snapshotStore.read().state.name,
                    "backendReachable" to backendReachable.toString(),
                    "registerOk" to lastRegisterOk.toString(),
                    "heartbeatOk" to lastHeartbeatOk.toString()
                )
            )
            logger.logRunStart()
            if (runConfig.networkIsolationEnabled && currentIdentity().capabilities.networkIsolationAvailable) {
                NetworkIsolationManager.enable(
                    applicationContext,
                    profile.packageName,
                    profile.extraNetworkPackages
                )
            }
            val runner = TimeBoxedRunner(
                driver = driver,
                fallback = shellDriver,
                profile = profile,
                logger = logger,
                appStarter = {
                    val pmIntent = packageManager.getLaunchIntentForPackage(profile.packageName)
                    if (pmIntent != null) {
                        pmIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        startActivity(pmIntent)
                    } else {
                        shell.amStart(profile.packageName)
                    }
                    if (runConfig.networkIsolationEnabled && currentIdentity().capabilities.networkIsolationAvailable) {
                        NetworkIsolationManager.enable(
                            applicationContext,
                            profile.packageName,
                            profile.extraNetworkPackages
                        )
                    }
                },
                appKiller = { shell.amForceStop(profile.packageName) },
                isAlive = {
                    !taskExecutor.isShutdown &&
                        !isAttemptCancelled(task.attemptId)
                },
                observer = observer
            )
            repeat(runConfig.loopCount.coerceAtLeast(1)) { index ->
                runner.runLoop(index, runConfig.budgetMs)
                if (index < runConfig.loopCount - 1 && runConfig.loopIntervalMs > 0L) {
                    Thread.sleep(runConfig.loopIntervalMs)
                }
                if (isAttemptCancelled(task.attemptId)) {
                    return@repeat
                }
            }
            if (isAttemptCancelled(task.attemptId)) {
                finalState = FinalTaskState.CANCELLED
                finalMessage = "attempt cancelled"
                snapshotStore.markIdle("cancelled $runId")
            } else {
                snapshotStore.markIdle("completed $runId")
            }
            logger.logRunEnd()
            maybeUploadArtifacts(task, runId, profile.packageName, shell)
            eventReporter.reportTaskFinishAndAwait(
                attemptId = task.attemptId,
                taskId = task.taskId,
                deviceId = identity.deviceId,
                runId = runId,
                status = finalState,
                message = finalMessage
            )
        } catch (t: Throwable) {
            Log.e(TAG, "executeTask failed attempt=${task.attemptId}: ${t.message}", t)
            logger.logRunEnd()
            maybeUploadArtifacts(task, runId, profile.packageName, shell)
            eventReporter.reportEvent(
                RunEventDto(
                    attemptId = task.attemptId,
                    taskId = task.taskId,
                    deviceId = identity.deviceId,
                    runId = runId,
                    eventType = "run_error",
                    state = ExecutorRuntimeState.DEGRADED.name,
                    code = "execution_error",
                    message = t.message ?: "execution error"
                )
            )
            eventReporter.reportTaskFinishAndAwait(
                attemptId = task.attemptId,
                taskId = task.taskId,
                deviceId = identity.deviceId,
                runId = runId,
                status = FinalTaskState.SYSTEM_ABORTED,
                message = t.message ?: "execution error",
                failureDetail = failureDetail("execution_error", "execution", t.message ?: "execution error")
            )
            snapshotStore.markDegraded("run failed", t.message ?: "execution error")
        } finally {
            NetworkIsolationManager.restore(applicationContext)
            deviceEnv.restore()
            if (cancelAttemptId == task.attemptId) {
                cancelAttemptId = null
            }
            dispatcher.finish(task.attemptId)
            startForegroundInternal("Executor idle")
            refreshHealth(forceRefresh = true)
            snapshotStore.updateControlMetadata(configVersion, lastHeartbeatAt, lastCommand, dispatcher.currentLeaseExpireAt())
        }
    }

    private fun preflight(profilePackage: String, networkIsolationRequired: Boolean): PreflightResult {
        val health = runtimeDependencies.collectHealth(
            context = this,
            backendReachable = backendReachable,
            lastRegisterOk = lastRegisterOk,
            lastHeartbeatOk = lastHeartbeatOk,
            degradedReason = degradedReason,
            forceRefresh = true
        )
        snapshotStore.updateHealth(health)
        return when {
            !health.accessibilityEnabled -> PreflightResult(false, "a11y unavailable", "a11y_unavailable", profilePackage, networkIsolationRequired)
            !health.rootAvailable -> PreflightResult(false, "root unavailable", "root_unavailable", profilePackage, networkIsolationRequired)
            !health.shellAvailable -> PreflightResult(false, "shell unavailable", "shell_unavailable", profilePackage, networkIsolationRequired)
            !runtimeDependencies.isPackageInstalled(this, profilePackage) ->
                PreflightResult(false, "target package missing", "package_missing", profilePackage, networkIsolationRequired)
            networkIsolationRequired && !health.networkIsolationAvailable ->
                PreflightResult(false, "network isolation unavailable", "network_isolation_unavailable", profilePackage, networkIsolationRequired)

            else -> PreflightResult(true, "ok", null, profilePackage, networkIsolationRequired)
        }
    }

    private fun maybeUploadArtifacts(task: RemoteTask, runId: String, packageName: String, shell: ShellBridge) {
        val targetTag = packageName.ifBlank { "unknown" }
            .replace(Regex("[^A-Za-z0-9._-]"), "_")
        val runDir = File(filesDir, AppConfig.RUN_DIR_PREFIX).apply { mkdirs() }

        if (task.artifactPolicy.uploadLog) {
            val logFile = File(runDir, "${runId}_${targetTag}.txt")
            if (logFile.exists()) {
                artifactUploader.upload(
                    attemptId = task.attemptId,
                    artifact = ArtifactDescriptor(
                        attemptId = task.attemptId,
                        taskId = task.taskId,
                        runId = runId,
                        artifactType = "run_log",
                        localPath = logFile.absolutePath,
                        mimeType = "text/plain"
                    )
                )
            }
        }

        if (task.artifactPolicy.uploadScreenshot) {
            val screenshot = File(runDir, "${runId}_${targetTag}.png")
            if (shell.screenCap(screenshot.absolutePath) && screenshot.exists()) {
                artifactUploader.upload(
                    attemptId = task.attemptId,
                    artifact = ArtifactDescriptor(
                        attemptId = task.attemptId,
                        taskId = task.taskId,
                        runId = runId,
                        artifactType = "screenshot",
                        localPath = screenshot.absolutePath,
                        mimeType = "image/png"
                    )
                )
            }
        }

        if (task.artifactPolicy.uploadDump) {
            val dump = File(runDir, "${runId}_${targetTag}_dump.xml")
            if (shell.dumpWindowHierarchy(dump.absolutePath) && dump.exists()) {
                artifactUploader.upload(
                    attemptId = task.attemptId,
                    artifact = ArtifactDescriptor(
                        attemptId = task.attemptId,
                        taskId = task.taskId,
                        runId = runId,
                        artifactType = "ui_dump",
                        localPath = dump.absolutePath,
                        mimeType = "application/xml"
                    )
                )
            }
        }
    }

    private fun currentIdentity(forceRefresh: Boolean = false): ExecutorIdentity {
        val capabilities = runtimeDependencies.collectCapabilities(this, forceRefresh)
        val health = runtimeDependencies.collectHealth(
            context = this,
            backendReachable = backendReachable,
            lastRegisterOk = lastRegisterOk,
            lastHeartbeatOk = lastHeartbeatOk,
            degradedReason = degradedReason,
            forceRefresh = forceRefresh
        ).copy(
            authConfigured = client.hasDeviceToken(),
            bufferedDeliveryCount = deliveryStore.count()
        )
        snapshotStore.updateHealth(health)
        return ExecutorIdentity.fromContext(
            context = this,
            capabilities = capabilities,
            executorVersion = BuildConfig.VERSION_NAME,
            installedProfiles = ExecutorProfileRegistry.entries(this).map { it.profile.packageName },
            tags = buildList {
                add("android-executor")
                add(BuildConfig.BUILD_TYPE)
                if (capabilities.rootAvailable) add("root")
                if (capabilities.networkIsolationAvailable) add("net-isolation")
            },
            hostGroup = "default",
            healthSnapshot = health.toPayload()
        )
    }

    private fun refreshHealth(forceRefresh: Boolean = false) {
        snapshotStore.updateHealth(
            runtimeDependencies.collectHealth(
                context = this,
                backendReachable = backendReachable,
                lastRegisterOk = lastRegisterOk,
                lastHeartbeatOk = lastHeartbeatOk,
                degradedReason = degradedReason,
                forceRefresh = forceRefresh
            ).copy(
                authConfigured = client.hasDeviceToken(),
                bufferedDeliveryCount = deliveryStore.count()
            )
        )
    }

    private fun refreshIdentityMetadata(forceRefresh: Boolean = false) {
        refreshIdentityMetadata(currentIdentity(forceRefresh))
    }

    private fun refreshIdentityMetadata(identity: ExecutorIdentity) {
        snapshotStore.updateIdentity(identity)
    }

    private fun preflightSummary(
        failureCode: String,
        failureMessage: String,
        targetProfilePackage: String,
        networkIsolationRequired: Boolean
    ): PreflightSummary = PreflightSummary(
        ok = false,
        failureCode = failureCode,
        failureMessage = failureMessage,
        targetProfilePackage = targetProfilePackage,
        networkIsolationRequired = networkIsolationRequired,
        capturedAt = runtimeDependencies.nowMs()
    )

    private fun failureDetail(
        failureCode: String,
        failureStage: String,
        lastError: String
    ): FailureDetail = FailureDetail(
        failureCode = failureCode,
        failureStage = failureStage,
        lastError = lastError,
        capturedAt = runtimeDependencies.nowMs()
    )

    private fun ExecutorHealthSnapshot.toPayload(): HealthSnapshotPayload =
        HealthSnapshotPayload(
            backendReachable = backendReachable,
            accessibilityEnabled = accessibilityEnabled,
            rootAvailable = rootAvailable,
            shellAvailable = shellAvailable,
            networkIsolationAvailable = networkIsolationAvailable,
            foregroundPackage = foregroundPackage,
            batteryLevel = batteryLevel,
            thermalStatus = thermalStatus,
            capturedAt = lastCheckedAt
        )

    private fun handleControlCommand(type: ExecutorControlCommandType, attemptId: String?, now: Long) {
        when (type) {
            ExecutorControlCommandType.STOP_LOOP -> {
                loopSuppressed = true
                snapshotStore.updateState(ExecutorRuntimeState.IDLE, "loop stopped by command")
            }

            ExecutorControlCommandType.CANCEL_ATTEMPT -> {
                cancelAttemptId = attemptId ?: dispatcher.currentAttemptId()
                snapshotStore.updateState(ExecutorRuntimeState.RECOVERING, "cancel requested", error = cancelAttemptId)
            }

            ExecutorControlCommandType.FORCE_HEALTH_CHECK -> refreshHealth(forceRefresh = true)

            ExecutorControlCommandType.REREGISTER -> {
                registered = false
                controlLoopState.forceRegisterNow(now)
                snapshotStore.updateState(ExecutorRuntimeState.REGISTERING, "re-register requested")
            }

            ExecutorControlCommandType.REFRESH_CONFIG -> snapshotStore.updateState(ExecutorRuntimeState.RECOVERING, "config refresh requested")

            ExecutorControlCommandType.QUIESCE -> {
                quiesced = true
                snapshotStore.updateState(ExecutorRuntimeState.IDLE, "quiesced by command")
            }
        }
    }

    private fun isAttemptCancelled(attemptId: String): Boolean = cancelAttemptId == attemptId

    private fun isLeaseExpiredBeforeExecution(task: RemoteTask): Boolean =
        task.leaseExpireAt?.let { runtimeDependencies.nowMs() > it } ?: false

    private fun startForegroundInternal(contentText: String) {
        notificationManager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "AutoA11y Executor", NotificationManager.IMPORTANCE_LOW)
        )
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("AutoA11y Executor")
            .setContentText(contentText)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setOngoing(true)
            .build()
        startForeground(NOTIFICATION_ID, notification)
    }

    internal fun runControlTickForTest(forceHealthRefresh: Boolean = false) {
        controlTick(forceHealthRefresh)
    }

    internal fun snapshotForTest() = snapshotStore.read()
}
