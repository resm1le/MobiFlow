package com.example.autoa11y.executor.control

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.BufferedOutputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.UUID
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

private const val TAG = "ExecutorClient"

internal object ExecutorRequestSigner {
    fun buildSignature(
        token: String,
        method: String,
        path: String,
        timestamp: String,
        nonce: String,
        bodyBytes: ByteArray
    ): String {
        if (token.isBlank()) return ""
        val bodySha = sha256Hex(bodyBytes)
        val canonical = method.uppercase() + path + timestamp + nonce + bodySha
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(token.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        return mac.doFinal(canonical.toByteArray(Charsets.UTF_8)).toHex()
    }

    fun sha256Hex(bodyBytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bodyBytes).toHex()

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }
}

data class ClientCallResult<T>(
    val ok: Boolean,
    val body: T? = null,
    val statusCode: Int? = null,
    val retryable: Boolean = !ok,
    val errorMessage: String? = null
)

open class ExecutorClient(context: Context) {
    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences("executor_client_prefs", Context.MODE_PRIVATE)
    private val protocolVersion: String
        get() = prefs.getString("protocol_version", EXECUTOR_PROTOCOL_VERSION) ?: EXECUTOR_PROTOCOL_VERSION
    private val knownDeviceId: String
        get() = prefs.getString("device_id", "unknown-device") ?: "unknown-device"

    open var baseUrl: String
        get() = prefs.getString("base_url", BuildConfig.DEFAULT_EXECUTOR_BASE_URL)
            ?: BuildConfig.DEFAULT_EXECUTOR_BASE_URL
        set(value) {
            prefs.edit().putString("base_url", value.trim().trimEnd('/')).apply()
        }

    open var deviceToken: String
        get() = prefs.getString("device_token", "") ?: ""
        set(value) {
            prefs.edit().putString("device_token", value.trim()).apply()
        }

    open fun authConfig(): DeviceAuthConfig = DeviceAuthConfig(
        backendUrl = baseUrl,
        deviceToken = deviceToken
    )

    open fun updateAuthConfig(config: DeviceAuthConfig) {
        baseUrl = config.backendUrl
        deviceToken = config.deviceToken
    }

    open fun hasDeviceToken(): Boolean = deviceToken.isNotBlank()

    open fun register(identity: ExecutorIdentity): Boolean =
        registerDetailed(identity).ok

    open fun registerDetailed(identity: ExecutorIdentity): ClientCallResult<JSONObject> {
        rememberIdentity(identity)
        return postJsonDetailed("/executor/register", identity.toJson(), identity.deviceId, identity.protocolVersion)
    }

    open fun heartbeat(identity: ExecutorIdentity, currentAttemptId: String?): Boolean {
        return heartbeatDetailed(identity, currentAttemptId).ok
    }

    open fun heartbeatDetailed(identity: ExecutorIdentity, currentAttemptId: String?): ClientCallResult<HeartbeatResponse> {
        rememberIdentity(identity)
        val body = identity.toJson().put("currentAttemptId", currentAttemptId)
        val response = postJsonDetailed("/executor/heartbeat", body, identity.deviceId, identity.protocolVersion)
        return ClientCallResult(
            ok = response.ok,
            body = HeartbeatResponse.fromJson(response.body),
            statusCode = response.statusCode,
            retryable = response.retryable,
            errorMessage = response.errorMessage
        )
    }

    open fun claimTask(identity: ExecutorIdentity): RemoteTask? {
        return claimTaskDetailed(identity).body
    }

    open fun claimTaskDetailed(identity: ExecutorIdentity): ClientCallResult<RemoteTask?> {
        rememberIdentity(identity)
        val body = identity.toJson()
        val response = postJsonDetailed("/executor/tasks/claim", body, identity.deviceId, identity.protocolVersion)
        val task = if (response.ok && response.body?.optBoolean("hasTask", true) == true && response.body.has("task")) {
            RemoteTask.fromJson(response.body.getJSONObject("task"))
        } else {
            null
        }
        return ClientCallResult(
            ok = response.ok,
            body = task,
            statusCode = response.statusCode,
            retryable = response.retryable,
            errorMessage = response.errorMessage
        )
    }

    open fun reportTaskStart(task: RemoteTask, runId: String): Boolean {
        return reportTaskStartDetailed(task, runId).ok
    }

    open fun reportTaskStartDetailed(task: RemoteTask, runId: String): ClientCallResult<JSONObject> {
        val body = JSONObject()
            .put("taskId", task.taskId)
            .put("attemptId", task.attemptId)
            .put("runId", runId)
            .put("profilePackage", task.profilePackage)
            .put("taskType", task.taskType)
            .put("source", task.source)
        return postJsonDetailed("/executor/tasks/${task.attemptId}/start", body, knownDeviceId, protocolVersion)
    }

    open fun reportEvents(attemptId: String, events: List<RunEventDto>): Boolean {
        return reportEventsDetailed(attemptId, events).ok
    }

    open fun reportEventsDetailed(attemptId: String, events: List<RunEventDto>): ClientCallResult<JSONObject> {
        if (events.isEmpty()) return ClientCallResult(ok = true, body = JSONObject(), statusCode = 200, retryable = false)
        val body = JSONObject().put("events", RunEventDto.toJsonArray(events))
        return postJsonDetailed("/executor/tasks/$attemptId/events", body, knownDeviceId, protocolVersion)
    }

    open fun reportTaskFinish(attemptId: String, taskId: String, runId: String, status: FinalTaskState, message: String): Boolean {
        return reportTaskFinishDetailed(attemptId, taskId, runId, status, message).ok
    }

    open fun reportTaskFinishDetailed(
        attemptId: String,
        taskId: String,
        runId: String,
        status: FinalTaskState,
        message: String
    ): ClientCallResult<JSONObject> =
        reportTaskFinishDetailed(
            attemptId = attemptId,
            taskId = taskId,
            runId = runId,
            status = status,
            message = message,
            preflightSummary = null,
            failureDetail = null
        )

    open fun reportTaskFinishDetailed(
        attemptId: String,
        taskId: String,
        runId: String,
        status: FinalTaskState,
        message: String,
        preflightSummary: PreflightSummary? = null,
        failureDetail: FailureDetail? = null
    ): ClientCallResult<JSONObject> {
        val body = JSONObject()
            .put("taskId", taskId)
            .put("attemptId", attemptId)
            .put("runId", runId)
            .put("status", status.name)
            .put("message", message)
            .put("preflightSummary", preflightSummary?.toJson())
            .put("failureDetail", failureDetail?.toJson())
        return postJsonDetailed("/executor/tasks/$attemptId/finish", body, knownDeviceId, protocolVersion)
    }

    open fun uploadArtifact(attemptId: String, artifact: ArtifactDescriptor): Boolean {
        return uploadArtifactDetailed(attemptId, artifact).ok
    }

    open fun uploadArtifactDetailed(attemptId: String, artifact: ArtifactDescriptor): ClientCallResult<Unit> {
        return uploadArtifactDirectPutV2Detailed(attemptId, artifact)
    }

    open fun requestArtifactUploadTicketDetailed(
        attemptId: String,
        artifact: ArtifactDescriptor
    ): ClientCallResult<ArtifactUploadTicket> {
        val body = JSONObject()
            .put("taskId", artifact.taskId)
            .put("runId", artifact.runId)
            .put("artifactId", artifact.artifactId)
            .put("artifactType", artifact.artifactType)
            .put("fileName", artifact.fileName)
            .put("mimeType", artifact.mimeType)
            .put("sizeBytes", artifact.sizeBytes)
        val response = postJsonDetailed(
            path = "/executor/tasks/$attemptId/artifacts/uploads",
            body = body,
            deviceId = knownDeviceId,
            requestProtocolVersion = protocolVersion
        )
        return ClientCallResult(
            ok = response.ok,
            body = response.body?.let(ArtifactUploadTicket.Companion::fromJson),
            statusCode = response.statusCode,
            retryable = response.retryable,
            errorMessage = response.errorMessage
        )
    }

    open fun directUploadArtifactDetailed(
        ticket: ArtifactUploadTicket,
        artifact: ArtifactDescriptor
    ): ClientCallResult<String?> {
        val file = File(artifact.localPath)
        if (!file.exists() || !file.isFile) {
            Log.w(TAG, "artifact file missing path=${artifact.localPath}")
            return ClientCallResult(ok = false, statusCode = 404, retryable = false, errorMessage = "artifact_missing")
        }
        val conn = (URL(ticket.uploadUrl).openConnection() as HttpURLConnection).apply {
            requestMethod = ticket.httpMethod.ifBlank { "PUT" }.uppercase()
            connectTimeout = 5_000
            readTimeout = 15_000
            doOutput = true
            setFixedLengthStreamingMode(file.length())
        }
        val headerNames = mutableSetOf<String>()
        ticket.requiredHeaders.forEach { (name, value) ->
            headerNames += name.lowercase()
            conn.setRequestProperty(name, value)
        }
        if ("content-type" !in headerNames) {
            conn.setRequestProperty("Content-Type", artifact.mimeType)
        }
        val result: ClientCallResult<String?> = runCatching {
            BufferedOutputStream(conn.outputStream).use { output ->
                file.inputStream().use { input -> input.copyTo(output) }
            }
            val rc = conn.responseCode
            val errorText = if (rc in 200..299) null else readResponseText(conn)
            if (rc !in 200..299) {
                Log.w(TAG, "directUploadArtifact rc=$rc artifactId=${artifact.artifactId} objectKey=${ticket.objectKey}")
            }
            ClientCallResult<String?>(
                ok = rc in 200..299,
                body = conn.getHeaderField("ETag"),
                statusCode = rc,
                retryable = rc !in 200..299,
                errorMessage = errorText?.ifBlank { "http_$rc" }
            )
        }.getOrElse {
            Log.w(TAG, "directUploadArtifact failed artifactId=${artifact.artifactId} err=${it.message}")
            ClientCallResult<String?>(ok = false, statusCode = null, retryable = true, errorMessage = it.message)
        }
        return result.also {
            conn.disconnect()
        }
    }

    open fun finalizeArtifactUploadDetailed(
        attemptId: String,
        artifact: ArtifactDescriptor,
        etag: String?
    ): ClientCallResult<ArtifactUploadFinalizeResponse> {
        val body = JSONObject()
            .put("taskId", artifact.taskId)
            .put("runId", artifact.runId)
            .put("artifactId", artifact.artifactId)
            .put("etag", etag)
        val response = postJsonDetailed(
            path = "/executor/tasks/$attemptId/artifacts/uploads/${artifact.artifactId}/finalize",
            body = body,
            deviceId = knownDeviceId,
            requestProtocolVersion = protocolVersion
        )
        val retryable = if (response.ok) false else true
        return ClientCallResult(
            ok = response.ok,
            body = response.body?.let(ArtifactUploadFinalizeResponse.Companion::fromJson),
            statusCode = response.statusCode,
            retryable = retryable,
            errorMessage = response.errorMessage
        )
    }

    private fun uploadArtifactDirectPutV2Detailed(
        attemptId: String,
        artifact: ArtifactDescriptor
    ): ClientCallResult<Unit> {
        val ticket = requestArtifactUploadTicketDetailed(attemptId, artifact)
        if (!ticket.ok || ticket.body == null) {
            return ClientCallResult(
                ok = false,
                statusCode = ticket.statusCode,
                retryable = ticket.retryable,
                errorMessage = ticket.errorMessage
            )
        }
        val upload = directUploadArtifactDetailed(ticket.body, artifact)
        if (!upload.ok) {
            return ClientCallResult(
                ok = false,
                statusCode = upload.statusCode,
                retryable = upload.retryable,
                errorMessage = upload.errorMessage
            )
        }
        val finalize = finalizeArtifactUploadDetailed(attemptId, artifact, upload.body)
        if (!finalize.ok) {
            return ClientCallResult(
                ok = false,
                statusCode = finalize.statusCode,
                retryable = finalize.retryable,
                errorMessage = finalize.errorMessage
            )
        }
        return ClientCallResult(ok = true, body = Unit, statusCode = finalize.statusCode ?: 200, retryable = false)
    }

    private fun postJsonDetailed(
        path: String,
        body: JSONObject,
        deviceId: String,
        requestProtocolVersion: String
    ): ClientCallResult<JSONObject> {
        val url = URL("${baseUrl.trimEnd('/')}$path")
        val bodyBytes = body.toString().toByteArray(Charsets.UTF_8)
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 5_000
            readTimeout = 10_000
            doInput = true
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Accept", "application/json")
        }
        attachExecutorHeaders(
            conn = conn,
            method = "POST",
            path = path,
            bodyBytes = bodyBytes,
            deviceId = deviceId,
            requestProtocolVersion = requestProtocolVersion
        )
        val result: ClientCallResult<JSONObject> = runCatching {
            conn.outputStream.use { it.write(bodyBytes) }
            val rc = conn.responseCode
            val stream = if (rc in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (rc !in 200..299) {
                Log.w(
                    TAG,
                    "postJson failed path=$path rc=$rc hasToken=${deviceToken.isNotBlank()} deviceId=$deviceId protocolVersion=$requestProtocolVersion body=$text"
                )
                ClientCallResult<JSONObject>(
                    ok = false,
                    body = null,
                    statusCode = rc,
                    retryable = rc >= 500,
                    errorMessage = text.ifBlank { "http_$rc" }
                )
            } else if (text.isBlank()) {
                Log.d(
                    TAG,
                    "postJson ok path=$path rc=$rc hasToken=${deviceToken.isNotBlank()} deviceId=$deviceId protocolVersion=$requestProtocolVersion"
                )
                ClientCallResult<JSONObject>(ok = true, body = JSONObject(), statusCode = rc, retryable = false)
            } else {
                Log.d(
                    TAG,
                    "postJson ok path=$path rc=$rc hasToken=${deviceToken.isNotBlank()} deviceId=$deviceId protocolVersion=$requestProtocolVersion"
                )
                ClientCallResult<JSONObject>(ok = true, body = JSONObject(text), statusCode = rc, retryable = false)
            }
        }.getOrElse {
            Log.w(
                TAG,
                "postJson failed path=$path rc=-1 hasToken=${deviceToken.isNotBlank()} deviceId=$deviceId protocolVersion=$requestProtocolVersion body=${it.message}"
            )
            ClientCallResult<JSONObject>(ok = false, statusCode = null, retryable = true, errorMessage = it.message)
        }
        return result.also {
            conn.disconnect()
        }
    }

    private fun rememberIdentity(identity: ExecutorIdentity) {
        prefs.edit()
            .putString("device_id", identity.deviceId)
            .putString("protocol_version", identity.protocolVersion)
            .apply()
    }

    private fun attachExecutorHeaders(
        conn: HttpURLConnection,
        method: String,
        path: String,
        bodyBytes: ByteArray,
        deviceId: String,
        requestProtocolVersion: String
    ) {
        val timestamp = System.currentTimeMillis().toString()
        val nonce = UUID.randomUUID().toString()
        val signature = buildSignature(method, path, timestamp, nonce, bodyBytes)
        conn.setRequestProperty("X-Executor-DeviceId", deviceId)
        conn.setRequestProperty("X-Executor-Protocol-Version", requestProtocolVersion)
        conn.setRequestProperty("X-Executor-Timestamp", timestamp)
        conn.setRequestProperty("X-Executor-Nonce", nonce)
        conn.setRequestProperty("X-Executor-Signature", signature)
    }

    private fun buildSignature(
        method: String,
        path: String,
        timestamp: String,
        nonce: String,
        bodyBytes: ByteArray
    ): String {
        return ExecutorRequestSigner.buildSignature(deviceToken, method, path, timestamp, nonce, bodyBytes)
    }

    private fun readResponseText(conn: HttpURLConnection): String {
        val stream = conn.errorStream ?: conn.inputStream ?: return ""
        return runCatching {
            stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        }.getOrDefault("")
    }
}
