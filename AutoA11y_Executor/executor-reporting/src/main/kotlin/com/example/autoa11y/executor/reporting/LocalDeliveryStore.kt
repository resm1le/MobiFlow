package com.example.autoa11y.executor.reporting

import android.content.Context
import com.example.autoa11y.executor.control.ArtifactDescriptor
import com.example.autoa11y.executor.control.FailureDetail
import com.example.autoa11y.executor.control.PreflightSummary
import com.example.autoa11y.executor.control.RunEventDto
import java.io.File
import java.util.Properties

enum class DeliveryKind {
    EVENT,
    TASK_FINISH,
    ARTIFACT
}

data class BufferedDelivery(
    val id: String,
    val kind: DeliveryKind,
    val deviceId: String,
    val taskId: String,
    val attemptId: String,
    val createdAt: Long,
    val event: RunEventDto? = null,
    val runId: String? = null,
    val status: String? = null,
    val message: String? = null,
    val preflightSummary: PreflightSummary? = null,
    val failureDetail: FailureDetail? = null,
    val artifact: ArtifactDescriptor? = null
)

class LocalDeliveryStore(
    private val dir: File
) {
    companion object {
        private const val MAX_FILES = 500

        fun fromContext(context: Context): LocalDeliveryStore =
            LocalDeliveryStore(File(context.applicationContext.filesDir, "executor-buffer-v2"))
    }

    private val seqFile = File(dir, "seq.txt")
    private val lock = Any()

    init {
        dir.mkdirs()
    }

    fun enqueueEvent(event: RunEventDto) = synchronized(lock) {
        write(
            BufferedDelivery(
                id = nextIdLocked(),
                kind = DeliveryKind.EVENT,
                deviceId = event.deviceId,
                taskId = event.taskId,
                attemptId = event.attemptId,
                createdAt = event.ts,
                event = event
            )
        )
        trimLocked()
    }

    fun enqueueTaskFinish(
        deviceId: String,
        taskId: String,
        attemptId: String,
        runId: String,
        status: String,
        message: String,
        preflightSummary: PreflightSummary? = null,
        failureDetail: FailureDetail? = null
    ) = synchronized(lock) {
        write(
            BufferedDelivery(
                id = nextIdLocked(),
                kind = DeliveryKind.TASK_FINISH,
                deviceId = deviceId,
                taskId = taskId,
                attemptId = attemptId,
                createdAt = System.currentTimeMillis(),
                runId = runId,
                status = status,
                message = message,
                preflightSummary = preflightSummary,
                failureDetail = failureDetail
            )
        )
        trimLocked()
    }

    fun enqueueArtifact(deviceId: String, attemptId: String, artifact: ArtifactDescriptor) = synchronized(lock) {
        write(
            BufferedDelivery(
                id = nextIdLocked(),
                kind = DeliveryKind.ARTIFACT,
                deviceId = deviceId,
                taskId = artifact.taskId,
                attemptId = attemptId,
                createdAt = System.currentTimeMillis(),
                artifact = artifact
            )
        )
        trimLocked()
    }

    fun peek(limit: Int = 20): List<BufferedDelivery> = synchronized(lock) {
        val deliveries = mutableListOf<BufferedDelivery>()
        for (file in dataFilesLocked().take(limit)) {
            val parsed = parseLocked(file)
            if (parsed != null) {
                deliveries += parsed
            }
        }
        deliveries
    }

    fun count(): Int = synchronized(lock) { dataFilesLocked().size }

    fun drop(ids: Collection<String>) = synchronized(lock) {
        ids.forEach { id ->
            File(dir, "$id.json").delete()
        }
    }

    private fun parseLocked(file: File): BufferedDelivery? {
        val props = loadProperties(file) ?: run {
            file.delete()
            return null
        }
        val kind = props.getProperty("kind")
            ?.trim()
            ?.takeIf { it.isNotBlank() }
            ?.let { runCatching { DeliveryKind.valueOf(it) }.getOrNull() }
            ?: run {
                file.delete()
                return null
            }
        return when (kind) {
            DeliveryKind.EVENT -> {
                BufferedDelivery(
                    id = file.nameWithoutExtension,
                    kind = kind,
                    deviceId = props.getProperty("deviceId", ""),
                    taskId = props.getProperty("taskId", ""),
                    attemptId = props.getProperty("attemptId", ""),
                    createdAt = props.getProperty("createdAt")?.toLongOrNull() ?: 0L,
                    event = RunEventDto(
                        attemptId = props.getProperty("event.attemptId", props.getProperty("attemptId", "")),
                        taskId = props.getProperty("event.taskId", props.getProperty("taskId", "")),
                        deviceId = props.getProperty("event.deviceId", props.getProperty("deviceId", "")),
                        runId = props.getProperty("event.runId", ""),
                        scenarioId = props.getProperty("event.scenarioId").takeIf { !it.isNullOrBlank() },
                        stepIndex = props.getProperty("event.stepIndex")?.toIntOrNull(),
                        actionIndex = props.getProperty("event.actionIndex")?.toIntOrNull(),
                        eventType = props.getProperty("event.eventType", ""),
                        state = props.getProperty("event.state").takeIf { !it.isNullOrBlank() },
                        code = props.getProperty("event.code").takeIf { !it.isNullOrBlank() },
                        message = props.getProperty("event.message", ""),
                        ts = props.getProperty("event.ts")?.toLongOrNull() ?: 0L
                    )
                )
            }

            DeliveryKind.TASK_FINISH -> BufferedDelivery(
                id = file.nameWithoutExtension,
                kind = kind,
                deviceId = props.getProperty("deviceId", ""),
                taskId = props.getProperty("taskId", ""),
                attemptId = props.getProperty("attemptId", ""),
                createdAt = props.getProperty("createdAt")?.toLongOrNull() ?: 0L,
                runId = props.getProperty("runId", ""),
                status = props.getProperty("status", ""),
                message = props.getProperty("message", ""),
                preflightSummary = PreflightSummary.fromJsonText(props.getProperty("preflightSummary")),
                failureDetail = FailureDetail.fromJsonText(props.getProperty("failureDetail"))
            )

            DeliveryKind.ARTIFACT -> BufferedDelivery(
                id = file.nameWithoutExtension,
                kind = kind,
                deviceId = props.getProperty("deviceId", ""),
                taskId = props.getProperty("taskId", ""),
                attemptId = props.getProperty("attemptId", ""),
                createdAt = props.getProperty("createdAt")?.toLongOrNull() ?: 0L,
                artifact = ArtifactDescriptor(
                    artifactId = props.getProperty("artifact.id", ""),
                    attemptId = props.getProperty("artifact.attemptId", props.getProperty("attemptId", "")),
                    taskId = props.getProperty("artifact.taskId", props.getProperty("taskId", "")),
                    runId = props.getProperty("artifact.runId", props.getProperty("runId", "")),
                    artifactType = props.getProperty("artifact.type", ""),
                    localPath = props.getProperty("artifact.path", ""),
                    fileName = props.getProperty("artifact.fileName", File(props.getProperty("artifact.path", "")).name),
                    mimeType = props.getProperty("artifact.mimeType", "application/octet-stream"),
                    sizeBytes = props.getProperty("artifact.sizeBytes")?.toLongOrNull() ?: -1L
                )
            )
        }
    }

    private fun write(delivery: BufferedDelivery) {
        val file = File(dir, "${delivery.id}.json")
        val props = Properties().apply {
            setProperty("kind", delivery.kind.name)
            setProperty("deviceId", delivery.deviceId)
            setProperty("taskId", delivery.taskId)
            setProperty("attemptId", delivery.attemptId)
            setProperty("createdAt", delivery.createdAt.toString())
            when (delivery.kind) {
                DeliveryKind.EVENT -> {
                    val event = delivery.event
                    if (event != null) {
                        setProperty("event.attemptId", event.attemptId)
                        setProperty("event.taskId", event.taskId)
                        setProperty("event.deviceId", event.deviceId)
                        setProperty("event.runId", event.runId)
                        event.scenarioId?.let { setProperty("event.scenarioId", it) }
                        event.stepIndex?.let { setProperty("event.stepIndex", it.toString()) }
                        event.actionIndex?.let { setProperty("event.actionIndex", it.toString()) }
                        setProperty("event.eventType", event.eventType)
                        event.state?.let { setProperty("event.state", it) }
                        event.code?.let { setProperty("event.code", it) }
                        setProperty("event.message", event.message)
                        setProperty("event.ts", event.ts.toString())
                    }
                }

                DeliveryKind.TASK_FINISH -> {
                    setProperty("runId", delivery.runId.orEmpty())
                    setProperty("status", delivery.status.orEmpty())
                    setProperty("message", delivery.message.orEmpty())
                    delivery.preflightSummary?.let { setProperty("preflightSummary", it.toJsonText()) }
                    delivery.failureDetail?.let { setProperty("failureDetail", it.toJsonText()) }
                }

                DeliveryKind.ARTIFACT -> {
                    val artifact = delivery.artifact
                    if (artifact != null) {
                        setProperty("artifact.id", artifact.artifactId)
                        setProperty("artifact.attemptId", artifact.attemptId)
                        setProperty("artifact.taskId", artifact.taskId)
                        setProperty("artifact.runId", artifact.runId)
                        setProperty("artifact.type", artifact.artifactType)
                        setProperty("artifact.path", artifact.localPath)
                        setProperty("artifact.fileName", artifact.fileName)
                        setProperty("artifact.mimeType", artifact.mimeType)
                        setProperty("artifact.sizeBytes", artifact.sizeBytes.toString())
                    }
                }
            }
        }
        file.outputStream().use { output ->
            props.store(output, null)
        }
    }

    private fun nextIdLocked(): String {
        val current = seqFile.takeIf { it.exists() }
            ?.readText()
            ?.trim()
            ?.toLongOrNull()
            ?: 0L
        val next = current + 1L
        seqFile.writeText(next.toString())
        return "%020d".format(next)
    }

    private fun trimLocked() {
        val files = dataFilesLocked()
        if (files.size <= MAX_FILES) return
        files.take(files.size - MAX_FILES).forEach { it.delete() }
    }

    private fun dataFilesLocked(): List<File> =
        dir.listFiles { file -> file.isFile && file.name.endsWith(".json") }
            ?.sortedBy { it.name }
            ?: emptyList()

    private fun loadProperties(file: File): Properties? =
        runCatching {
            Properties().apply {
                file.inputStream().use { input -> load(input) }
            }
        }.getOrNull()
}
