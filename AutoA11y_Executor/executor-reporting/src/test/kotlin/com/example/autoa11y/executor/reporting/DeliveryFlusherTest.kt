package com.example.autoa11y.executor.reporting

import androidx.test.core.app.ApplicationProvider
import com.example.autoa11y.executor.control.ExecutorClient
import com.example.autoa11y.executor.control.ArtifactDescriptor
import com.example.autoa11y.executor.control.ClientCallResult
import com.example.autoa11y.executor.control.RunEventDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.io.path.createTempDirectory

@RunWith(RobolectricTestRunner::class)
class DeliveryFlusherTest {

    @Test
    fun flushGroupsConsecutiveEventsForSameAttempt() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val store = LocalDeliveryStore(createTempDirectory("delivery-flusher-group").toFile())
        store.enqueueEvent(event("attempt-1", "first"))
        store.enqueueEvent(event("attempt-1", "second"))
        store.enqueueEvent(event("attempt-2", "third"))
        val calls = CopyOnWriteArrayList<Pair<String, Int>>()
        val client = object : ExecutorClient(context) {
            override fun reportEventsDetailed(attemptId: String, events: List<RunEventDto>): ClientCallResult<org.json.JSONObject> {
                calls += attemptId to events.size
                return ClientCallResult(ok = true, body = org.json.JSONObject(), statusCode = 200, retryable = false)
            }
        }

        DeliveryFlusher(client, store).flush(limit = 10)

        assertEquals(listOf("attempt-1" to 2, "attempt-2" to 1), calls)
        assertEquals(0, store.count())
    }

    @Test
    fun flushStopsWhenGroupedEventsFailRetryably() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val store = LocalDeliveryStore(createTempDirectory("delivery-flusher-stop").toFile())
        store.enqueueEvent(event("attempt-1", "first"))
        store.enqueueEvent(event("attempt-1", "second"))
        store.enqueueEvent(event("attempt-2", "third"))
        val attempts = CopyOnWriteArrayList<String>()
        val client = object : ExecutorClient(context) {
            override fun reportEventsDetailed(attemptId: String, events: List<RunEventDto>): ClientCallResult<org.json.JSONObject> {
                attempts += attemptId
                return ClientCallResult(ok = false, retryable = true)
            }
        }

        DeliveryFlusher(client, store).flush(limit = 10)

        assertEquals(listOf("attempt-1"), attempts)
        assertEquals(3, store.count())
        assertTrue(store.peek(10).all { it.kind == DeliveryKind.EVENT })
    }

    @Test
    fun flushReplaysBufferedArtifactWithoutUploadModeState() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val tempDir = createTempDirectory("delivery-flusher-artifact").toFile()
        val artifactFile = kotlin.io.path.createTempFile("artifact", ".txt").toFile().apply {
            writeText("artifact-body")
            deleteOnExit()
        }
        val store = LocalDeliveryStore(tempDir)
        store.enqueueArtifact(
            "device-1",
            "attempt-1",
            ArtifactDescriptor(
                attemptId = "attempt-1",
                taskId = "task-1",
                runId = "run-1",
                artifactType = "run_log",
                localPath = artifactFile.absolutePath,
                mimeType = "text/plain"
            )
        )
        val artifactTypes = CopyOnWriteArrayList<String>()
        val client = object : ExecutorClient(context) {
            override fun uploadArtifactDetailed(attemptId: String, artifact: ArtifactDescriptor): ClientCallResult<Unit> {
                artifactTypes += artifact.artifactType
                return ClientCallResult(ok = true, body = Unit, statusCode = 200, retryable = false)
            }
        }

        DeliveryFlusher(client, store).flush(limit = 10)

        assertEquals(listOf("run_log"), artifactTypes)
        assertEquals(0, store.count())
    }

    private fun event(attemptId: String, message: String): RunEventDto =
        RunEventDto(
            attemptId = attemptId,
            taskId = "task-1",
            deviceId = "device-1",
            runId = "run-1",
            eventType = "step_end",
            message = message
        )
}
