package com.example.autoa11y.executor.reporting

import android.util.Log
import com.example.autoa11y.executor.control.ExecutorClient
import com.example.autoa11y.executor.control.FinalTaskState
import java.io.File

private const val TAG = "DeliveryFlusher"

class DeliveryFlusher(
    private val client: ExecutorClient,
    private val store: LocalDeliveryStore
) {
    fun flush(limit: Int = 20) {
        val batch = store.peek(limit)
        if (batch.isEmpty()) return

        val deliveredIds = mutableListOf<String>()
        var index = 0
        while (index < batch.size) {
            val delivery = batch[index]
            if (delivery.kind == DeliveryKind.EVENT) {
                val grouped = groupBufferedEvents(batch, index)
                index += grouped.size
                val validEvents = grouped.mapNotNull { groupedDelivery ->
                    if (groupedDelivery.event == null) {
                        Log.w(TAG, "drop malformed event delivery id=${groupedDelivery.id}")
                        deliveredIds += groupedDelivery.id
                        null
                    } else {
                        groupedDelivery.event
                    }
                }
                if (validEvents.isEmpty()) {
                    continue
                }
                val result = client.reportEventsDetailed(grouped.first().attemptId, validEvents)
                if (result.ok) {
                    deliveredIds += grouped.map { it.id }
                    continue
                }
                if (!result.retryable) {
                    Log.w(
                        TAG,
                        "drop non-retryable delivery id=${grouped.first().id} kind=EVENT statusCode=${result.statusCode} err=${result.errorMessage}"
                    )
                    deliveredIds += grouped.map { it.id }
                    continue
                }
                break
            }
            val result = when (delivery.kind) {
                DeliveryKind.TASK_FINISH -> {
                    val finalState = runCatching {
                        FinalTaskState.valueOf(delivery.status.orEmpty())
                    }.getOrDefault(FinalTaskState.FAILED)
                    if (delivery.preflightSummary == null && delivery.failureDetail == null) {
                        client.reportTaskFinishDetailed(
                            attemptId = delivery.attemptId,
                            taskId = delivery.taskId,
                            runId = delivery.runId.orEmpty(),
                            status = finalState,
                            message = delivery.message.orEmpty()
                        )
                    } else {
                        client.reportTaskFinishDetailed(
                            attemptId = delivery.attemptId,
                            taskId = delivery.taskId,
                            runId = delivery.runId.orEmpty(),
                            status = finalState,
                            message = delivery.message.orEmpty(),
                            preflightSummary = delivery.preflightSummary,
                            failureDetail = delivery.failureDetail
                        )
                    }
                }

                DeliveryKind.ARTIFACT -> {
                    val artifact = delivery.artifact
                    if (artifact == null) {
                        Log.w(TAG, "drop malformed artifact delivery id=${delivery.id}")
                        null
                    } else if (!File(artifact.localPath).exists()) {
                        Log.w(TAG, "drop missing artifact path=${artifact.localPath}")
                        null
                    } else {
                        client.uploadArtifactDetailed(delivery.attemptId, artifact)
                    }
                }
                DeliveryKind.EVENT -> null
            }
            if (result == null) {
                deliveredIds += delivery.id
            } else if (result.ok) {
                deliveredIds += delivery.id
            } else if (!result.retryable) {
                Log.w(
                    TAG,
                    "drop non-retryable delivery id=${delivery.id} kind=${delivery.kind} statusCode=${result.statusCode} err=${result.errorMessage}"
                )
                deliveredIds += delivery.id
            } else {
                break
            }
            index += 1
        }

        if (deliveredIds.isNotEmpty()) {
            store.drop(deliveredIds)
        }
    }

    private fun groupBufferedEvents(batch: List<BufferedDelivery>, startIndex: Int): List<BufferedDelivery> {
        val grouped = mutableListOf<BufferedDelivery>()
        val first = batch[startIndex]
        var cursor = startIndex
        while (cursor < batch.size) {
            val candidate = batch[cursor]
            if (candidate.kind != DeliveryKind.EVENT || candidate.attemptId != first.attemptId) {
                break
            }
            grouped += candidate
            cursor += 1
        }
        return grouped
    }
}
