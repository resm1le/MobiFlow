package com.example.autoa11y.executor.reporting

import androidx.test.core.app.ApplicationProvider
import com.example.autoa11y.executor.control.ExecutorClient
import com.example.autoa11y.executor.control.ClientCallResult
import com.example.autoa11y.executor.control.FinalTaskState
import com.example.autoa11y.executor.control.RemoteTask
import com.example.autoa11y.executor.control.RunEventDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread
import kotlin.io.path.createTempDirectory

@RunWith(RobolectricTestRunner::class)
class EventReporterTest {

    @Test
    fun reportEventReturnsQuicklyEvenWhenClientBlocksAndEventuallyBuffers() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val store = LocalDeliveryStore(createTempDirectory("event-reporter-test").toFile())
        val latch = CountDownLatch(1)
        val client = object : ExecutorClient(context) {
            override fun reportEventsDetailed(attemptId: String, events: List<RunEventDto>): ClientCallResult<org.json.JSONObject> {
                latch.await(250, TimeUnit.MILLISECONDS)
                return ClientCallResult(ok = false, retryable = true)
            }
        }
        val reporter = EventReporter(client, store, Executors.newSingleThreadExecutor())

        val start = System.nanoTime()
        reporter.reportEvent(
            event = RunEventDto(
                attemptId = "attempt-1",
                taskId = "task-1",
                deviceId = "device-1",
                runId = "run-1",
                eventType = "scenario_start",
                message = "started"
            )
        )
        val elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start)

        assertTrue("reportEvent should not block on network send, elapsed=${elapsedMs}ms", elapsedMs < 100)
        latch.countDown()
        reporter.close()
        assertEquals(1, store.peek(10).size)
    }

    @Test
    fun reportTaskFinishReturnsQuicklyEvenWhenClientBlocksAndEventuallyBuffers() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val store = LocalDeliveryStore(createTempDirectory("event-reporter-test").toFile())
        val latch = CountDownLatch(1)
        val client = object : ExecutorClient(context) {
            override fun reportTaskFinishDetailed(
                attemptId: String,
                taskId: String,
                runId: String,
                status: FinalTaskState,
                message: String
            ): ClientCallResult<org.json.JSONObject> {
                latch.await(250, TimeUnit.MILLISECONDS)
                return ClientCallResult(ok = false, retryable = true)
            }
        }
        val reporter = EventReporter(client, store, Executors.newSingleThreadExecutor())

        val start = System.nanoTime()
        reporter.reportTaskFinish("attempt-2", "task-2", "device-1", "run-2", FinalTaskState.FAILED, "boom")
        val elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start)

        assertTrue("reportTaskFinish should not block on network send, elapsed=${elapsedMs}ms", elapsedMs < 100)
        latch.countDown()
        reporter.close()
        val item = store.peek(1).single()
        assertEquals(DeliveryKind.TASK_FINISH, item.kind)
    }

    @Test
    fun reportTaskStartReturnsQuicklyWhenClientBlocks() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val store = LocalDeliveryStore(createTempDirectory("event-reporter-test").toFile())
        val latch = CountDownLatch(1)
        val client = object : ExecutorClient(context) {
            override fun reportTaskStartDetailed(task: RemoteTask, runId: String): ClientCallResult<org.json.JSONObject> {
                latch.await(250, TimeUnit.MILLISECONDS)
                return ClientCallResult(ok = false, retryable = true)
            }
        }
        val reporter = EventReporter(client, store, Executors.newSingleThreadExecutor())

        val task = RemoteTask(
            taskId = "task-1",
            attemptId = "attempt-3",
            profilePackage = "com.google.android.apps.maps"
        )
        val start = System.nanoTime()
        reporter.reportTaskStart(task, "run-3")
        val elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start)

        assertTrue("reportTaskStart should not block on network send, elapsed=${elapsedMs}ms", elapsedMs < 100)
        latch.countDown()
        reporter.close()
    }

    @Test
    fun batchesEventsBySizeBeforeSending() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val store = LocalDeliveryStore(createTempDirectory("event-reporter-batch").toFile())
        val latch = CountDownLatch(1)
        val batchSizes = CopyOnWriteArrayList<Int>()
        val client = object : ExecutorClient(context) {
            override fun reportEventsDetailed(attemptId: String, events: List<RunEventDto>): ClientCallResult<org.json.JSONObject> {
                batchSizes += events.size
                latch.countDown()
                return ClientCallResult(ok = true, body = org.json.JSONObject(), statusCode = 200, retryable = false)
            }
        }
        val reporter = EventReporter(client, store, Executors.newSingleThreadExecutor())

        repeat(10) { index ->
            reporter.reportEvent(event("attempt-batch", index))
        }

        assertTrue(latch.await(2, TimeUnit.SECONDS))
        reporter.close()
        assertEquals(listOf(10), batchSizes)
        assertEquals(0, store.count())
    }

    @Test
    fun reportTaskFinishFlushesPendingEventsFirst() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val store = LocalDeliveryStore(createTempDirectory("event-reporter-finish").toFile())
        val completion = CountDownLatch(2)
        val operations = CopyOnWriteArrayList<String>()
        val client = object : ExecutorClient(context) {
            override fun reportEventsDetailed(attemptId: String, events: List<RunEventDto>): ClientCallResult<org.json.JSONObject> {
                operations += "events:${events.size}"
                completion.countDown()
                return ClientCallResult(ok = true, body = org.json.JSONObject(), statusCode = 200, retryable = false)
            }

            override fun reportTaskFinishDetailed(
                attemptId: String,
                taskId: String,
                runId: String,
                status: FinalTaskState,
                message: String
            ): ClientCallResult<org.json.JSONObject> {
                operations += "finish:$attemptId"
                completion.countDown()
                return ClientCallResult(ok = true, body = org.json.JSONObject(), statusCode = 200, retryable = false)
            }
        }
        val reporter = EventReporter(client, store, Executors.newSingleThreadExecutor())

        reporter.reportEvent(event("attempt-finish", 1))
        reporter.reportTaskFinish("attempt-finish", "task-1", "device-1", "run-1", FinalTaskState.SUCCESS, "ok")

        assertTrue(completion.await(2, TimeUnit.SECONDS))
        reporter.close()
        assertEquals(listOf("events:1", "finish:attempt-finish"), operations)
    }

    @Test
    fun failedBatchBuffersAllEvents() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val store = LocalDeliveryStore(createTempDirectory("event-reporter-buffer").toFile())
        val client = object : ExecutorClient(context) {
            override fun reportEventsDetailed(attemptId: String, events: List<RunEventDto>): ClientCallResult<org.json.JSONObject> {
                return ClientCallResult(ok = false, retryable = true)
            }
        }
        val reporter = EventReporter(client, store, Executors.newSingleThreadExecutor())

        reporter.reportEvent(event("attempt-buffer", 1))
        reporter.reportEvent(event("attempt-buffer", 2))

        reporter.close()
        assertEquals(2, store.count())
    }

    @Test
    fun nonRetryableBatchDropsEventsInsteadOfBuffering() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val store = LocalDeliveryStore(createTempDirectory("event-reporter-drop").toFile())
        val client = object : ExecutorClient(context) {
            override fun reportEventsDetailed(attemptId: String, events: List<RunEventDto>): ClientCallResult<org.json.JSONObject> {
                return ClientCallResult(ok = false, statusCode = 400, retryable = false, errorMessage = "ATTEMPT_STATE_INVALID")
            }
        }
        val reporter = EventReporter(client, store, Executors.newSingleThreadExecutor())

        reporter.reportEvent(event("attempt-drop", 1))
        reporter.reportEvent(event("attempt-drop", 2))

        reporter.close()
        assertEquals(0, store.count())
    }

    @Test
    fun reportTaskFinishAndAwaitWaitsForQueuedEventsBeforeReturning() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val store = LocalDeliveryStore(createTempDirectory("event-reporter-await").toFile())
        val eventsStarted = CountDownLatch(1)
        val releaseEvents = CountDownLatch(1)
        val finished = CountDownLatch(1)
        val operations = CopyOnWriteArrayList<String>()
        val client = object : ExecutorClient(context) {
            override fun reportEventsDetailed(attemptId: String, events: List<RunEventDto>): ClientCallResult<org.json.JSONObject> {
                operations += "events:${events.size}"
                eventsStarted.countDown()
                releaseEvents.await(2, TimeUnit.SECONDS)
                return ClientCallResult(ok = true, body = org.json.JSONObject(), statusCode = 200, retryable = false)
            }

            override fun reportTaskFinishDetailed(
                attemptId: String,
                taskId: String,
                runId: String,
                status: FinalTaskState,
                message: String
            ): ClientCallResult<org.json.JSONObject> {
                operations += "finish:$attemptId"
                return ClientCallResult(ok = true, body = org.json.JSONObject(), statusCode = 200, retryable = false)
            }
        }
        val reporter = EventReporter(client, store, Executors.newSingleThreadExecutor())

        reporter.reportEvent(event("attempt-await", 1))
        thread(start = true) {
            reporter.reportTaskFinishAndAwait(
                attemptId = "attempt-await",
                taskId = "task-1",
                deviceId = "device-1",
                runId = "run-1",
                status = FinalTaskState.SUCCESS,
                message = "ok"
            )
            finished.countDown()
        }

        assertTrue(eventsStarted.await(2, TimeUnit.SECONDS))
        assertFalse(finished.await(150, TimeUnit.MILLISECONDS))
        releaseEvents.countDown()
        assertTrue(finished.await(2, TimeUnit.SECONDS))
        reporter.close()
        assertEquals(listOf("events:1", "finish:attempt-await"), operations)
        assertEquals(0, store.count())
    }

    @Test
    fun nonRetryableFinishIsDroppedInsteadOfBuffered() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val store = LocalDeliveryStore(createTempDirectory("event-reporter-finish-drop").toFile())
        val client = object : ExecutorClient(context) {
            override fun reportTaskFinishDetailed(
                attemptId: String,
                taskId: String,
                runId: String,
                status: FinalTaskState,
                message: String
            ): ClientCallResult<org.json.JSONObject> {
                return ClientCallResult(ok = false, statusCode = 400, retryable = false, errorMessage = "ATTEMPT_STATE_INVALID")
            }
        }
        val reporter = EventReporter(client, store, Executors.newSingleThreadExecutor())

        reporter.reportTaskFinish(
            attemptId = "attempt-finish-drop",
            taskId = "task-1",
            deviceId = "device-1",
            runId = "run-1",
            status = FinalTaskState.FAILED,
            message = "boom"
        )

        reporter.close()
        assertEquals(0, store.count())
    }

    private fun event(attemptId: String, index: Int): RunEventDto =
        RunEventDto(
            attemptId = attemptId,
            taskId = "task-1",
            deviceId = "device-1",
            runId = "run-1",
            eventType = "step_end",
            message = "event-$index"
        )
}
