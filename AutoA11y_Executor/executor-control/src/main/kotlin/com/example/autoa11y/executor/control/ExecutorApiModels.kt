package com.example.autoa11y.executor.control

import android.content.Context
import android.os.Build
import android.provider.Settings
import com.example.autoa11y.shared.AppConfig
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

const val EXECUTOR_PROTOCOL_VERSION = "v1"

object TaskTypes {
    const val PLUGIN_RUN = "PLUGIN_RUN"
    const val PLUGIN_SMOKE = "PLUGIN_SMOKE"
    const val LOCAL_DEBUG = "LOCAL_DEBUG"
}

enum class FinalTaskState {
    SUCCESS,
    FAILED,
    CANCELLED,
    PRECHECK_FAILED,
    SYSTEM_ABORTED,
    LEASE_EXPIRED
}

enum class ExecutorControlCommandType {
    STOP_LOOP,
    CANCEL_ATTEMPT,
    FORCE_HEALTH_CHECK,
    REREGISTER,
    REFRESH_CONFIG,
    QUIESCE
}

data class ExecutorControlCommand(
    val type: ExecutorControlCommandType,
    val attemptId: String? = null
) {
    fun toJson(): JSONObject = JSONObject()
        .put("type", type.name)
        .put("attemptId", attemptId)

    companion object {
        fun fromJson(json: JSONObject): ExecutorControlCommand? {
            val type = runCatching {
                ExecutorControlCommandType.valueOf(json.optString("type"))
            }.getOrNull() ?: return null
            return ExecutorControlCommand(
                type = type,
                attemptId = json.optString("attemptId").ifBlank { null }
            )
        }

        fun fromJsonArray(json: JSONArray?): List<ExecutorControlCommand> {
            if (json == null) return emptyList()
            val commands = mutableListOf<ExecutorControlCommand>()
            for (index in 0 until json.length()) {
                when (val item = json.opt(index)) {
                    is JSONObject -> fromJson(item)?.let(commands::add)
                    is String -> runCatching {
                        ExecutorControlCommandType.valueOf(item)
                    }.getOrNull()?.let { commands += ExecutorControlCommand(it) }
                }
            }
            return commands
        }
    }
}

data class HeartbeatResponse(
    val registered: Boolean = true,
    val serverTimeMs: Long? = null,
    val configVersion: String? = null,
    val commands: List<ExecutorControlCommand> = emptyList(),
    val runConfig: RunConfig? = null
) {
    companion object {
        fun fromJson(json: JSONObject?): HeartbeatResponse {
            if (json == null) return HeartbeatResponse()
            return HeartbeatResponse(
                registered = json.optBoolean("registered", true),
                serverTimeMs = json.optLong("serverTimeMs").takeIf { json.has("serverTimeMs") },
                configVersion = json.optString("configVersion").ifBlank { null },
                commands = ExecutorControlCommand.fromJsonArray(json.optJSONArray("commands")),
                runConfig = json.optJSONObject("runConfig")
                    ?.let { RunConfig.fromJson(it) }
                    ?: json.optJSONObject("configSnapshot")?.let { RunConfig.fromJson(it) }
            )
        }
    }
}

data class DeviceAuthConfig(
    val backendUrl: String = BuildConfig.DEFAULT_EXECUTOR_BASE_URL,
    val deviceToken: String = ""
)

data class ExecutorCapabilities(
    val accessibilityEnabled: Boolean,
    val rootAvailable: Boolean,
    val shellAvailable: Boolean = true,
    val networkIsolationAvailable: Boolean,
    val screenshotCapable: Boolean = shellAvailable,
    val uiDumpCapable: Boolean = shellAvailable
) {
    fun toJson(): JSONObject = JSONObject()
        .put("accessibilityEnabled", accessibilityEnabled)
        .put("rootAvailable", rootAvailable)
        .put("shellAvailable", shellAvailable)
        .put("networkIsolationAvailable", networkIsolationAvailable)
        .put("screenshotCapable", screenshotCapable)
        .put("uiDumpCapable", uiDumpCapable)
}

data class HealthSnapshotPayload(
    val backendReachable: Boolean,
    val accessibilityEnabled: Boolean,
    val rootAvailable: Boolean,
    val shellAvailable: Boolean,
    val networkIsolationAvailable: Boolean,
    val foregroundPackage: String? = null,
    val batteryLevel: Int? = null,
    val thermalStatus: String? = null,
    val capturedAt: Long
) {
    fun toJson(): JSONObject = JSONObject()
        .put("backendReachable", backendReachable)
        .put("accessibilityEnabled", accessibilityEnabled)
        .put("rootAvailable", rootAvailable)
        .put("shellAvailable", shellAvailable)
        .put("networkIsolationAvailable", networkIsolationAvailable)
        .put("foregroundPackage", foregroundPackage)
        .put("batteryLevel", batteryLevel)
        .put("thermalStatus", thermalStatus)
        .put("capturedAt", capturedAt)
}

data class PreflightSummary(
    val ok: Boolean,
    val failureCode: String,
    val failureMessage: String,
    val targetProfilePackage: String,
    val networkIsolationRequired: Boolean,
    val capturedAt: Long
) {
    fun toJson(): JSONObject = JSONObject()
        .put("ok", ok)
        .put("failureCode", failureCode)
        .put("failureMessage", failureMessage)
        .put("targetProfilePackage", targetProfilePackage)
        .put("networkIsolationRequired", networkIsolationRequired)
        .put("capturedAt", capturedAt)

    fun toJsonText(): String = toJson().toString()

    companion object {
        fun fromJsonText(text: String?): PreflightSummary? {
            if (text.isNullOrBlank()) return null
            val json = runCatching { JSONObject(text) }.getOrNull() ?: return null
            return PreflightSummary(
                ok = json.optBoolean("ok", false),
                failureCode = json.optString("failureCode"),
                failureMessage = json.optString("failureMessage"),
                targetProfilePackage = json.optString("targetProfilePackage"),
                networkIsolationRequired = json.optBoolean("networkIsolationRequired", false),
                capturedAt = json.optLong("capturedAt", 0L)
            )
        }
    }
}

data class FailureDetail(
    val failureCode: String,
    val failureStage: String,
    val lastError: String,
    val capturedAt: Long
) {
    fun toJson(): JSONObject = JSONObject()
        .put("failureCode", failureCode)
        .put("failureStage", failureStage)
        .put("lastError", lastError)
        .put("capturedAt", capturedAt)

    fun toJsonText(): String = toJson().toString()

    companion object {
        fun fromJsonText(text: String?): FailureDetail? {
            if (text.isNullOrBlank()) return null
            val json = runCatching { JSONObject(text) }.getOrNull() ?: return null
            return FailureDetail(
                failureCode = json.optString("failureCode"),
                failureStage = json.optString("failureStage"),
                lastError = json.optString("lastError"),
                capturedAt = json.optLong("capturedAt", 0L)
            )
        }
    }
}

data class ExecutorIdentity(
    val deviceId: String,
    val protocolVersion: String = EXECUTOR_PROTOCOL_VERSION,
    val executorVersion: String,
    val brand: String,
    val model: String,
    val androidVersion: String,
    val screenWidth: Int,
    val screenHeight: Int,
    val capabilities: ExecutorCapabilities,
    val installedProfiles: List<String> = emptyList(),
    val tags: List<String> = emptyList(),
    val hostGroup: String? = null,
    val healthSnapshot: HealthSnapshotPayload? = null
) {
    fun toJson(): JSONObject = JSONObject()
        .put("deviceId", deviceId)
        .put("protocolVersion", protocolVersion)
        .put("executorVersion", executorVersion)
        .put("brand", brand)
        .put("model", model)
        .put("androidVersion", androidVersion)
        .put("screenWidth", screenWidth)
        .put("screenHeight", screenHeight)
        .put("capabilities", capabilities.toJson())
        .put("installedProfiles", JSONArray(installedProfiles))
        .put("tags", JSONArray(tags))
        .put("hostGroup", hostGroup)
        .put("healthSnapshot", healthSnapshot?.toJson())

    companion object {
        fun fromContext(
            context: Context,
            capabilities: ExecutorCapabilities,
            executorVersion: String = "1.0.0",
            protocolVersion: String = EXECUTOR_PROTOCOL_VERSION,
            installedProfiles: List<String> = emptyList(),
            tags: List<String> = emptyList(),
            hostGroup: String? = null,
            healthSnapshot: HealthSnapshotPayload? = null
        ): ExecutorIdentity {
            val androidId = Settings.Secure.getString(
                context.contentResolver,
                Settings.Secure.ANDROID_ID
            ) ?: "unknown_device"
            val metrics = context.resources.displayMetrics
            return ExecutorIdentity(
                deviceId = androidId,
                protocolVersion = protocolVersion,
                executorVersion = executorVersion,
                brand = Build.BRAND ?: "unknown_brand",
                model = Build.MODEL ?: "unknown_model",
                androidVersion = Build.VERSION.RELEASE ?: "unknown_android",
                screenWidth = metrics.widthPixels,
                screenHeight = metrics.heightPixels,
                capabilities = capabilities,
                installedProfiles = installedProfiles,
                tags = tags,
                hostGroup = hostGroup,
                healthSnapshot = healthSnapshot
            )
        }
    }
}

data class RunConfig(
    val loopCount: Int = 1,
    val budgetMs: Long = AppConfig.LOOP_BUDGET_MS,
    val loopIntervalMs: Long = 0L,
    val networkIsolationEnabled: Boolean = false,
    val pollIntervalMs: Long = BuildConfig.DEFAULT_POLL_INTERVAL_MS,
    val heartbeatIntervalMs: Long = BuildConfig.DEFAULT_HEARTBEAT_INTERVAL_MS
) {
    fun toJson(): JSONObject = JSONObject()
        .put("loopCount", loopCount)
        .put("budgetMs", budgetMs)
        .put("loopIntervalMs", loopIntervalMs)
        .put("networkIsolationEnabled", networkIsolationEnabled)
        .put("pollIntervalMs", pollIntervalMs)
        .put("heartbeatIntervalMs", heartbeatIntervalMs)

    companion object {
        fun fromJson(json: JSONObject?): RunConfig {
            if (json == null) return RunConfig()
            return RunConfig(
                loopCount = json.optInt("loopCount", 1).coerceAtLeast(1),
                budgetMs = json.optLong("budgetMs", AppConfig.LOOP_BUDGET_MS),
                loopIntervalMs = json.optLong("loopIntervalMs", 0L).coerceAtLeast(0L),
                networkIsolationEnabled = json.optBoolean("networkIsolationEnabled", false),
                pollIntervalMs = json.optLong("pollIntervalMs", BuildConfig.DEFAULT_POLL_INTERVAL_MS),
                heartbeatIntervalMs = json.optLong("heartbeatIntervalMs", BuildConfig.DEFAULT_HEARTBEAT_INTERVAL_MS)
            )
        }
    }
}

data class ArtifactPolicy(
    val uploadLog: Boolean = true,
    val uploadScreenshot: Boolean = false,
    val uploadDump: Boolean = false
) {
    fun toJson(): JSONObject = JSONObject()
        .put("uploadLog", uploadLog)
        .put("uploadScreenshot", uploadScreenshot)
        .put("uploadDump", uploadDump)

    companion object {
        fun fromJson(json: JSONObject?): ArtifactPolicy {
            if (json == null) return ArtifactPolicy()
            return ArtifactPolicy(
                uploadLog = json.optBoolean("uploadLog", true),
                uploadScreenshot = json.optBoolean("uploadScreenshot", false),
                uploadDump = json.optBoolean("uploadDump", false)
            )
        }
    }
}

enum class ArtifactUploadMode {
    DIRECT_PUT_V2;

    companion object {
        fun fromWire(value: String?): ArtifactUploadMode? {
            val normalized = value?.trim()?.uppercase().orEmpty()
            if (normalized.isBlank()) return null
            return entries.firstOrNull { it.name == normalized }
        }
    }
}

data class RemoteTask(
    val taskId: String,
    val attemptId: String,
    val runId: String? = null,
    val taskType: String = TaskTypes.PLUGIN_RUN,
    val profilePackage: String,
    val taskPayload: JSONObject? = null,
    val runConfig: RunConfig = RunConfig(),
    val artifactPolicy: ArtifactPolicy = ArtifactPolicy(),
    val priority: Int = 0,
    val labels: List<String> = emptyList(),
    val leaseExpireAt: Long? = null,
    val scheduleVersion: String? = null,
    val idempotencyKey: String? = null,
    val source: String = "remote",
    val artifactUploadMode: ArtifactUploadMode? = null
) {
    val configSnapshot: RunConfig get() = runConfig

    fun toJson(): JSONObject = JSONObject()
        .put("taskId", taskId)
        .put("attemptId", attemptId)
        .put("runId", runId)
        .put("taskType", taskType)
        .put("profilePackage", profilePackage)
        .put("taskPayload", taskPayload)
        .put("runConfig", runConfig.toJson())
        .put("artifactPolicy", artifactPolicy.toJson())
        .put("priority", priority)
        .put("labels", JSONArray(labels))
        .put("leaseExpireAt", leaseExpireAt)
        .put("scheduleVersion", scheduleVersion)
        .put("idempotencyKey", idempotencyKey)
        .put("source", source)
        .put("artifactUploadMode", artifactUploadMode?.name)

    companion object {
        fun fromJson(json: JSONObject): RemoteTask = RemoteTask(
            taskId = json.optString("taskId"),
            attemptId = json.optString("attemptId"),
            runId = json.optString("runId").ifBlank { null },
            taskType = json.optString("taskType", TaskTypes.PLUGIN_RUN),
            profilePackage = json.optString("profilePackage"),
            taskPayload = json.optJSONObject("taskPayload"),
            runConfig = json.optJSONObject("runConfig")
                ?.let { RunConfig.fromJson(it) }
                ?: RunConfig.fromJson(json.optJSONObject("configSnapshot")),
            artifactPolicy = ArtifactPolicy.fromJson(json.optJSONObject("artifactPolicy")),
            priority = json.optInt("priority", 0),
            labels = buildList {
                val array = json.optJSONArray("labels") ?: JSONArray()
                for (index in 0 until array.length()) {
                    val item = array.optString(index).trim()
                    if (item.isNotBlank()) add(item)
                }
            },
            leaseExpireAt = json.optLong("leaseExpireAt").takeIf { json.has("leaseExpireAt") },
            scheduleVersion = json.optString("scheduleVersion").ifBlank { null },
            idempotencyKey = json.optString("idempotencyKey").ifBlank { null },
            source = json.optString("source", "remote"),
            artifactUploadMode = ArtifactUploadMode.fromWire(json.optString("artifactUploadMode"))
        )

        fun fake(profilePackage: String): RemoteTask {
            val now = System.currentTimeMillis().toString()
            return RemoteTask(
                taskId = "fake-$now",
                attemptId = "fake-attempt-$now",
                runId = "fake-run-$now",
                taskType = TaskTypes.LOCAL_DEBUG,
                profilePackage = profilePackage,
                runConfig = RunConfig(loopCount = 1, budgetMs = 60_000L),
                artifactPolicy = ArtifactPolicy(uploadLog = true),
                idempotencyKey = "fake-$now",
                source = "fake"
            )
        }
    }
}

data class RunEventDto(
    val attemptId: String,
    val taskId: String,
    val deviceId: String,
    val runId: String,
    val scenarioId: String? = null,
    val stepIndex: Int? = null,
    val actionIndex: Int? = null,
    val eventType: String,
    val state: String? = null,
    val code: String? = null,
    val message: String = "",
    val ts: Long = System.currentTimeMillis()
) {
    fun toJson(): JSONObject = JSONObject()
        .put("attemptId", attemptId)
        .put("taskId", taskId)
        .put("deviceId", deviceId)
        .put("runId", runId)
        .put("scenarioId", scenarioId)
        .put("stepIndex", stepIndex)
        .put("actionIndex", actionIndex)
        .put("eventType", eventType)
        .put("state", state)
        .put("code", code)
        .put("message", message)
        .put("ts", ts)

    companion object {
        fun toJsonArray(items: List<RunEventDto>): JSONArray = JSONArray().apply {
            items.forEach { put(it.toJson()) }
        }

        fun fromJson(json: JSONObject): RunEventDto = RunEventDto(
            attemptId = json.optString("attemptId"),
            taskId = json.optString("taskId"),
            deviceId = json.optString("deviceId"),
            runId = json.optString("runId"),
            scenarioId = json.optString("scenarioId").ifBlank { null },
            stepIndex = json.optInt("stepIndex").takeIf { json.has("stepIndex") },
            actionIndex = json.optInt("actionIndex").takeIf { json.has("actionIndex") },
            eventType = json.optString("eventType"),
            state = json.optString("state").ifBlank { null },
            code = json.optString("code").ifBlank { null },
            message = json.optString("message"),
            ts = json.optLong("ts", System.currentTimeMillis())
        )
    }
}

data class ArtifactDescriptor(
    val artifactId: String = UUID.randomUUID().toString(),
    val attemptId: String,
    val taskId: String,
    val runId: String,
    val artifactType: String,
    val localPath: String,
    val fileName: String = File(localPath).name,
    val mimeType: String = "application/octet-stream",
    val sizeBytes: Long = File(localPath).takeIf { it.exists() }?.length() ?: -1L
)

data class ArtifactUploadTicket(
    val artifactId: String,
    val artifactUploadMode: ArtifactUploadMode? = null,
    val uploadUrl: String,
    val httpMethod: String = "PUT",
    val requiredHeaders: Map<String, String> = emptyMap(),
    val objectKey: String? = null,
    val expiresAt: Long? = null
) {
    companion object {
        fun fromJson(json: JSONObject): ArtifactUploadTicket = ArtifactUploadTicket(
            artifactId = json.optString("artifactId"),
            artifactUploadMode = ArtifactUploadMode.fromWire(json.optString("artifactUploadMode")),
            uploadUrl = json.optString("uploadUrl"),
            httpMethod = json.optString("httpMethod", "PUT"),
            requiredHeaders = json.optJSONObject("requiredHeaders").toStringMap(),
            objectKey = json.optString("objectKey").ifBlank { null },
            expiresAt = json.optLong("expiresAt").takeIf { json.has("expiresAt") }
        )
    }
}

data class ArtifactUploadFinalizeResponse(
    val accepted: Boolean,
    val artifactId: String,
    val sizeBytes: Long? = null
) {
    companion object {
        fun fromJson(json: JSONObject): ArtifactUploadFinalizeResponse = ArtifactUploadFinalizeResponse(
            accepted = json.optBoolean("accepted", false),
            artifactId = json.optString("artifactId"),
            sizeBytes = json.optLong("sizeBytes").takeIf { json.has("sizeBytes") }
        )
    }
}

private fun JSONObject?.toStringMap(): Map<String, String> {
    if (this == null) return emptyMap()
    val values = linkedMapOf<String, String>()
    val iterator = keys()
    while (iterator.hasNext()) {
        val key = iterator.next()
        values[key] = optString(key)
    }
    return values
}
