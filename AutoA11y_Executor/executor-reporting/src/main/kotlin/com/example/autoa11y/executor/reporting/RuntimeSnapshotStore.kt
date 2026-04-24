package com.example.autoa11y.executor.reporting

import android.content.Context
import com.example.autoa11y.executor.control.EXECUTOR_PROTOCOL_VERSION
import com.example.autoa11y.executor.control.ExecutorIdentity
import com.example.autoa11y.executor.control.RemoteTask

enum class ExecutorRuntimeState {
    IDLE,
    REGISTERING,
    POLLING,
    RUNNING,
    RECOVERING,
    DEGRADED
}

data class ExecutorHealthSnapshot(
    val accessibilityEnabled: Boolean,
    val rootAvailable: Boolean,
    val shellAvailable: Boolean,
    val networkIsolationAvailable: Boolean,
    val backendReachable: Boolean,
    val lastRegisterOk: Boolean,
    val lastHeartbeatOk: Boolean,
    val authConfigured: Boolean,
    val bufferedDeliveryCount: Int,
    val degradedReason: String?,
    val lastCheckedAt: Long,
    val foregroundPackage: String? = null,
    val batteryLevel: Int? = null,
    val thermalStatus: String? = null
)

data class ExecutorStatusSnapshot(
    val backendUrl: String,
    val deviceId: String,
    val registered: Boolean,
    val state: ExecutorRuntimeState,
    val protocolVersion: String,
    val configVersion: String?,
    val currentAttemptId: String?,
    val currentTaskId: String?,
    val currentTaskType: String?,
    val currentProfilePackage: String?,
    val lastRunId: String?,
    val lastHeartbeatAt: Long,
    val leaseExpireAt: Long?,
    val lastCommand: String?,
    val tags: List<String>,
    val lastMessage: String,
    val lastError: String?,
    val pollIntervalMs: Long,
    val heartbeatIntervalMs: Long,
    val health: ExecutorHealthSnapshot,
    val lastUpdatedAt: Long
) {
    val accessibilityEnabled: Boolean get() = health.accessibilityEnabled
    val rootAvailable: Boolean get() = health.rootAvailable
    val busy: Boolean get() = !currentAttemptId.isNullOrBlank()
}

class RuntimeSnapshotStore(context: Context) {
    private val prefs = context.applicationContext
        .getSharedPreferences("executor_runtime_snapshot", Context.MODE_PRIVATE)

    fun updateBackend(url: String, deviceId: String) {
        prefs.edit()
            .putString("backendUrl", url)
            .putString("deviceId", deviceId)
            .putLong("lastUpdatedAt", System.currentTimeMillis())
            .apply()
    }

    fun updateIdentity(identity: ExecutorIdentity) {
        prefs.edit()
            .putString("deviceId", identity.deviceId)
            .putString("protocolVersion", identity.protocolVersion)
            .putString("tags", identity.tags.joinToString(","))
            .putLong("lastUpdatedAt", System.currentTimeMillis())
            .apply()
    }

    fun updateHealth(health: ExecutorHealthSnapshot) {
        prefs.edit()
            .putBoolean("accessibilityEnabled", health.accessibilityEnabled)
            .putBoolean("rootAvailable", health.rootAvailable)
            .putBoolean("shellAvailable", health.shellAvailable)
            .putBoolean("networkIsolationAvailable", health.networkIsolationAvailable)
            .putBoolean("backendReachable", health.backendReachable)
            .putBoolean("lastRegisterOk", health.lastRegisterOk)
            .putBoolean("lastHeartbeatOk", health.lastHeartbeatOk)
            .putBoolean("authConfigured", health.authConfigured)
            .putInt("bufferedDeliveryCount", health.bufferedDeliveryCount)
            .putString("degradedReason", health.degradedReason)
            .putLong("healthCheckedAt", health.lastCheckedAt)
            .putString("foregroundPackage", health.foregroundPackage)
            .putInt("batteryLevel", health.batteryLevel ?: -1)
            .putString("thermalStatus", health.thermalStatus)
            .putLong("lastUpdatedAt", System.currentTimeMillis())
            .apply()
    }

    fun updateLoopConfig(pollIntervalMs: Long, heartbeatIntervalMs: Long) {
        prefs.edit()
            .putLong("pollIntervalMs", pollIntervalMs)
            .putLong("heartbeatIntervalMs", heartbeatIntervalMs)
            .putLong("lastUpdatedAt", System.currentTimeMillis())
            .apply()
    }

    fun updateControlMetadata(
        configVersion: String?,
        lastHeartbeatAt: Long,
        lastCommand: String?,
        leaseExpireAt: Long?
    ) {
        prefs.edit()
            .putString("configVersion", configVersion)
            .putLong("lastHeartbeatAt", lastHeartbeatAt)
            .putString("lastCommand", lastCommand)
            .putLong("leaseExpireAt", leaseExpireAt ?: -1L)
            .putLong("lastUpdatedAt", System.currentTimeMillis())
            .apply()
    }

    fun updateRegistration(registered: Boolean, message: String, error: String? = null) {
        prefs.edit()
            .putBoolean("registered", registered)
            .putString("lastMessage", message)
            .putString("lastError", error)
            .putLong("lastUpdatedAt", System.currentTimeMillis())
            .apply()
    }

    fun updateState(state: ExecutorRuntimeState, message: String, error: String? = null, degradedReason: String? = null) {
        prefs.edit()
            .putString("state", state.name)
            .putString("lastMessage", message)
            .putString("lastError", error)
            .putString("degradedReason", degradedReason)
            .putLong("lastUpdatedAt", System.currentTimeMillis())
            .apply()
    }

    fun markTaskRunning(task: RemoteTask, runId: String, message: String, error: String? = null) {
        prefs.edit()
            .putString("state", ExecutorRuntimeState.RUNNING.name)
            .putString("currentTaskId", task.taskId)
            .putString("currentAttemptId", task.attemptId)
            .putString("currentTaskType", task.taskType)
            .putString("currentProfilePackage", task.profilePackage)
            .putString("lastRunId", runId)
            .putString("lastMessage", message)
            .putString("lastError", error)
            .putString("degradedReason", null)
            .putLong("leaseExpireAt", task.leaseExpireAt ?: -1L)
            .putLong("lastUpdatedAt", System.currentTimeMillis())
            .apply()
    }

    fun markIdle(message: String, error: String? = null) {
        prefs.edit()
            .putString("state", ExecutorRuntimeState.IDLE.name)
            .remove("currentTaskId")
            .remove("currentAttemptId")
            .remove("currentTaskType")
            .remove("currentProfilePackage")
            .putString("lastMessage", message)
            .putString("lastError", error)
            .putString("degradedReason", null)
            .putLong("leaseExpireAt", -1L)
            .putLong("lastUpdatedAt", System.currentTimeMillis())
            .apply()
    }

    fun markDegraded(message: String, reason: String) {
        prefs.edit()
            .putString("state", ExecutorRuntimeState.DEGRADED.name)
            .putString("lastMessage", message)
            .putString("lastError", reason)
            .putString("degradedReason", reason)
            .putLong("lastUpdatedAt", System.currentTimeMillis())
            .apply()
    }

    fun read(): ExecutorStatusSnapshot = ExecutorStatusSnapshot(
        backendUrl = prefs.getString("backendUrl", "") ?: "",
        deviceId = prefs.getString("deviceId", "") ?: "",
        registered = prefs.getBoolean("registered", false),
        state = prefs.getString("state", ExecutorRuntimeState.IDLE.name)
            ?.let { runCatching { ExecutorRuntimeState.valueOf(it) }.getOrNull() }
            ?: ExecutorRuntimeState.IDLE,
        protocolVersion = prefs.getString("protocolVersion", EXECUTOR_PROTOCOL_VERSION) ?: EXECUTOR_PROTOCOL_VERSION,
        configVersion = prefs.getString("configVersion", null),
        currentAttemptId = prefs.getString("currentAttemptId", null),
        currentTaskId = prefs.getString("currentTaskId", null),
        currentTaskType = prefs.getString("currentTaskType", null),
        currentProfilePackage = prefs.getString("currentProfilePackage", null),
        lastRunId = prefs.getString("lastRunId", null),
        lastHeartbeatAt = prefs.getLong("lastHeartbeatAt", 0L),
        leaseExpireAt = prefs.getLong("leaseExpireAt", -1L).takeIf { it > 0L },
        lastCommand = prefs.getString("lastCommand", null),
        tags = prefs.getString("tags", "")
            ?.split(",")
            ?.map { it.trim() }
            ?.filter { it.isNotBlank() }
            ?: emptyList(),
        lastMessage = prefs.getString("lastMessage", "idle") ?: "idle",
        lastError = prefs.getString("lastError", null),
        pollIntervalMs = prefs.getLong("pollIntervalMs", 15_000L),
        heartbeatIntervalMs = prefs.getLong("heartbeatIntervalMs", 30_000L),
        health = ExecutorHealthSnapshot(
            accessibilityEnabled = prefs.getBoolean("accessibilityEnabled", false),
            rootAvailable = prefs.getBoolean("rootAvailable", false),
            shellAvailable = prefs.getBoolean("shellAvailable", false),
            networkIsolationAvailable = prefs.getBoolean("networkIsolationAvailable", false),
            backendReachable = prefs.getBoolean("backendReachable", false),
            lastRegisterOk = prefs.getBoolean("lastRegisterOk", false),
            lastHeartbeatOk = prefs.getBoolean("lastHeartbeatOk", false),
            authConfigured = prefs.getBoolean("authConfigured", false),
            bufferedDeliveryCount = prefs.getInt("bufferedDeliveryCount", 0),
            degradedReason = prefs.getString("degradedReason", null),
            lastCheckedAt = prefs.getLong("healthCheckedAt", 0L),
            foregroundPackage = prefs.getString("foregroundPackage", null),
            batteryLevel = prefs.getInt("batteryLevel", -1).takeIf { it >= 0 },
            thermalStatus = prefs.getString("thermalStatus", null)
        ),
        lastUpdatedAt = prefs.getLong("lastUpdatedAt", 0L)
    )
}
