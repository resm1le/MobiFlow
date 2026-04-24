package com.example.autoa11y.executor.reporting

import android.util.Log
import com.example.autoa11y.executor.control.ExecutorClient
import com.example.autoa11y.executor.control.FailureDetail
import com.example.autoa11y.executor.control.FinalTaskState
import com.example.autoa11y.executor.control.PreflightSummary
import com.example.autoa11y.executor.control.RemoteTask
import com.example.autoa11y.executor.control.RunEventDto
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

private const val TAG = "EventReporter"
private const val MAX_BATCH_SIZE = 10
private const val MAX_BATCH_DELAY_MS = 1000L

class EventReporter(
    private val client: ExecutorClient,
    private val buffer: LocalDeliveryStore,
    private val executor: ExecutorService = Executors.newSingleThreadExecutor(),
    private val scheduler: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()
) : AutoCloseable {

    private val pendingEventsByAttempt = linkedMapOf<String, MutableList<RunEventDto>>()
    private val scheduledFlushes = mutableMapOf<String, ScheduledFuture<*>>()

    fun reportTaskStart(task: RemoteTask, runId: String): Boolean {
        executor.execute {
            val result = client.reportTaskStartDetailed(task, runId)
            if (!result.ok) {
                Log.w(TAG, "reportTaskStart failed, dropping immediate delivery attempt=${task.attemptId}")
            }
        }
        return true
    }

    fun reportEvent(event: RunEventDto) {
        executor.execute {
            val batch = pendingEventsByAttempt.getOrPut(event.attemptId) { mutableListOf() }
            batch += event
            if (batch.size >= MAX_BATCH_SIZE) {
                flushAttemptBatchInternal(event.attemptId)
            } else {
                ensureDelayedFlush(event.attemptId)
            }
        }
    }

    fun reportTaskFinish(
        attemptId: String,
        taskId: String,
        deviceId: String,
        runId: String,
        status: FinalTaskState,
        message: String,
        preflightSummary: PreflightSummary? = null,
        failureDetail: FailureDetail? = null
    ): Boolean {
        executor.execute {
            reportTaskFinishInternal(
                attemptId = attemptId,
                taskId = taskId,
                deviceId = deviceId,
                runId = runId,
                status = status,
                message = message,
                preflightSummary = preflightSummary,
                failureDetail = failureDetail
            )
        }
        return true
    }

    fun reportTaskFinishAndAwait(
        attemptId: String,
        taskId: String,
        deviceId: String,
        runId: String,
        status: FinalTaskState,
        message: String,
        preflightSummary: PreflightSummary? = null,
        failureDetail: FailureDetail? = null,
        timeoutMs: Long = 60_000L
    ): Boolean {
        return runCatching {
            executor.submit<Boolean> {
                reportTaskFinishInternal(
                    attemptId = attemptId,
                    taskId = taskId,
                    deviceId = deviceId,
                    runId = runId,
                    status = status,
                    message = message,
                    preflightSummary = preflightSummary,
                    failureDetail = failureDetail
                )
            }.get(timeoutMs, TimeUnit.MILLISECONDS)
        }.getOrElse {
            Log.w(TAG, "reportTaskFinishAndAwait failed attempt=$attemptId err=${it.message}")
            buffer.enqueueTaskFinish(
                deviceId = deviceId,
                taskId = taskId,
                attemptId = attemptId,
                runId = runId,
                status = status.name,
                message = message,
                preflightSummary = preflightSummary,
                failureDetail = failureDetail
            )
            false
        }
    }

    override fun close() {
        runCatching {
            executor.submit {
                flushAllPendingInternal()
            }.get(5, TimeUnit.SECONDS)
        }.onFailure {
            Log.w(TAG, "close flush failed err=${it.message}")
        }
        scheduler.shutdownNow()
        executor.shutdown()
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            executor.shutdownNow()
        }
    }

    private fun ensureDelayedFlush(attemptId: String) {
        val scheduled = scheduledFlushes[attemptId]
        if (scheduled != null && !scheduled.isDone) {
            return
        }
        scheduledFlushes[attemptId] = scheduler.schedule(
            { executor.execute { flushAttemptBatchInternal(attemptId) } },
            MAX_BATCH_DELAY_MS,
            TimeUnit.MILLISECONDS
        )
    }

    private fun flushAllPendingInternal() {
        pendingEventsByAttempt.keys.toList().forEach(::flushAttemptBatchInternal)
    }

    private fun flushAttemptBatchInternal(attemptId: String) {
        scheduledFlushes.remove(attemptId)?.cancel(false)
        val events = pendingEventsByAttempt.remove(attemptId)?.toList().orEmpty()
        if (events.isEmpty()) {
            return
        }
        val result = client.reportEventsDetailed(attemptId, events)
        if (!result.ok) {
            if (result.retryable) {
                Log.w(TAG, "reportEvent batch failed, buffering attempt=$attemptId size=${events.size}")
                events.forEach { buffer.enqueueEvent(it) }
            } else {
                Log.w(
                    TAG,
                    "reportEvent batch failed non-retryable, dropping attempt=$attemptId size=${events.size} statusCode=${result.statusCode} err=${result.errorMessage}"
                )
            }
        }
    }

    private fun reportTaskFinishInternal(
        attemptId: String,
        taskId: String,
        deviceId: String,
        runId: String,
        status: FinalTaskState,
        message: String,
        preflightSummary: PreflightSummary? = null,
        failureDetail: FailureDetail? = null
    ): Boolean {
        flushAttemptBatchInternal(attemptId)
        val result = if (preflightSummary == null && failureDetail == null) {
            client.reportTaskFinishDetailed(attemptId, taskId, runId, status, message)
        } else {
            client.reportTaskFinishDetailed(
                attemptId = attemptId,
                taskId = taskId,
                runId = runId,
                status = status,
                message = message,
                preflightSummary = preflightSummary,
                failureDetail = failureDetail
            )
        }
        if (!result.ok) {
            if (result.retryable) {
                Log.w(TAG, "reportTaskFinish failed, buffering attempt=$attemptId status=${status.name}")
                buffer.enqueueTaskFinish(
                    deviceId = deviceId,
                    taskId = taskId,
                    attemptId = attemptId,
                    runId = runId,
                    status = status.name,
                    message = message,
                    preflightSummary = preflightSummary,
                    failureDetail = failureDetail
                )
            } else {
                Log.w(
                    TAG,
                    "reportTaskFinish failed non-retryable, dropping attempt=$attemptId status=${status.name} statusCode=${result.statusCode} err=${result.errorMessage}"
                )
            }
        }
        return result.ok
    }
}
