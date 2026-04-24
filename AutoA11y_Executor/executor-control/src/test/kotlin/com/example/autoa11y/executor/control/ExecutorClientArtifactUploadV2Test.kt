package com.example.autoa11y.executor.control

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.nio.file.Files
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicReference

@RunWith(RobolectricTestRunner::class)
class ExecutorClientArtifactUploadV2Test {

    @Test
    fun uploadArtifactDetailedUsesTicketDirectPutAndFinalize() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val calls = CopyOnWriteArrayList<String>()
        val finalizeEtag = AtomicReference<String?>()
        val file = Files.createTempFile("artifact-upload-v2", ".txt").toFile().apply {
            writeText("hello")
            deleteOnExit()
        }
        val client = object : ExecutorClient(context) {
            override fun requestArtifactUploadTicketDetailed(
                attemptId: String,
                artifact: ArtifactDescriptor
            ): ClientCallResult<ArtifactUploadTicket> {
                calls += "ticket"
                assertEquals("artifact-1", artifact.artifactId)
                assertEquals("run_log", artifact.artifactType)
                return ClientCallResult(
                    ok = true,
                    body = ArtifactUploadTicket(
                        artifactId = artifact.artifactId,
                        artifactUploadMode = ArtifactUploadMode.DIRECT_PUT_V2,
                        uploadUrl = "http://127.0.0.1/upload/${artifact.artifactId}",
                        httpMethod = "PUT",
                        requiredHeaders = mapOf("X-Test-Upload" to "ticket-header"),
                        objectKey = "artifacts/task-1/attempt-1/artifact-1/run.txt"
                    ),
                    statusCode = 200,
                    retryable = false
                )
            }

            override fun directUploadArtifactDetailed(
                ticket: ArtifactUploadTicket,
                artifact: ArtifactDescriptor
            ): ClientCallResult<String?> {
                calls += "put"
                assertEquals("ticket-header", ticket.requiredHeaders["X-Test-Upload"])
                assertEquals("DIRECT_PUT_V2", ticket.artifactUploadMode?.name)
                assertEquals(file.absolutePath, artifact.localPath)
                return ClientCallResult(ok = true, body = "\"etag-1\"", statusCode = 200, retryable = false)
            }

            override fun finalizeArtifactUploadDetailed(
                attemptId: String,
                artifact: ArtifactDescriptor,
                etag: String?
            ): ClientCallResult<ArtifactUploadFinalizeResponse> {
                calls += "finalize"
                finalizeEtag.set(etag)
                return ClientCallResult(
                    ok = true,
                    body = ArtifactUploadFinalizeResponse(
                        accepted = true,
                        artifactId = artifact.artifactId,
                        sizeBytes = artifact.sizeBytes
                    ),
                    statusCode = 200,
                    retryable = false
                )
            }
        }
        val artifact = ArtifactDescriptor(
            artifactId = "artifact-1",
            attemptId = "attempt-1",
            taskId = "task-1",
            runId = "run-1",
            artifactType = "run_log",
            localPath = file.absolutePath,
            mimeType = "text/plain"
        )

        val result = client.uploadArtifactDetailed("attempt-1", artifact)

        assertTrue(result.ok)
        assertEquals(listOf("ticket", "put", "finalize"), calls)
        assertEquals("\"etag-1\"", finalizeEtag.get())
    }

    @Test
    fun uploadArtifactDetailedReturnsTicketFailureWithoutFallback() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val file = Files.createTempFile("artifact-upload-fallback", ".txt").toFile().apply {
            writeText("fallback")
            deleteOnExit()
        }
        val client = object : ExecutorClient(context) {
            var ticketCalls = 0
            var directCalls = 0
            var finalizeCalls = 0

            override fun requestArtifactUploadTicketDetailed(
                attemptId: String,
                artifact: ArtifactDescriptor
            ): ClientCallResult<ArtifactUploadTicket> {
                ticketCalls += 1
                return ClientCallResult(
                    ok = false,
                    statusCode = 404,
                    retryable = false,
                    errorMessage = "ARTIFACT_UPLOAD_V1_REMOVED"
                )
            }
        }

        val result = client.uploadArtifactDetailed(
            attemptId = "attempt-1",
            artifact = ArtifactDescriptor(
                artifactId = "artifact-1",
                attemptId = "attempt-1",
                taskId = "task-1",
                runId = "run-1",
                artifactType = "run_log",
                localPath = file.absolutePath,
                mimeType = "text/plain"
            )
        )

        assertFalse(result.ok)
        assertFalse(result.retryable)
        assertEquals(404, result.statusCode)
        assertEquals(1, client.ticketCalls)
        assertEquals(0, client.directCalls)
        assertEquals(0, client.finalizeCalls)
    }

    @Test
    fun repeatedV2RetryReRequestsTicketAndDoesNotFallbackAfterTicketSuccess() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val file = Files.createTempFile("artifact-upload-retry", ".txt").toFile().apply {
            writeText("retry")
            deleteOnExit()
        }
        val client = object : ExecutorClient(context) {
            var ticketCalls = 0
            var directCalls = 0
            var finalizeCalls = 0

            override fun requestArtifactUploadTicketDetailed(
                attemptId: String,
                artifact: ArtifactDescriptor
            ): ClientCallResult<ArtifactUploadTicket> {
                ticketCalls += 1
                return ClientCallResult(
                    ok = true,
                    body = ArtifactUploadTicket(
                        artifactId = artifact.artifactId,
                        artifactUploadMode = ArtifactUploadMode.DIRECT_PUT_V2,
                        uploadUrl = "http://127.0.0.1/upload/${artifact.artifactId}"
                    ),
                    statusCode = 200,
                    retryable = false
                )
            }

            override fun directUploadArtifactDetailed(
                ticket: ArtifactUploadTicket,
                artifact: ArtifactDescriptor
            ): ClientCallResult<String?> {
                directCalls += 1
                return ClientCallResult(ok = false, statusCode = 503, retryable = true, errorMessage = "http_503")
            }

            override fun finalizeArtifactUploadDetailed(
                attemptId: String,
                artifact: ArtifactDescriptor,
                etag: String?
            ): ClientCallResult<ArtifactUploadFinalizeResponse> {
                finalizeCalls += 1
                return ClientCallResult(ok = true, retryable = false)
            }
        }
        val artifact = ArtifactDescriptor(
            artifactId = "artifact-1",
            attemptId = "attempt-1",
            taskId = "task-1",
            runId = "run-1",
            artifactType = "run_log",
            localPath = file.absolutePath,
            mimeType = "text/plain"
        )

        val first = client.uploadArtifactDetailed("attempt-1", artifact)
        val second = client.uploadArtifactDetailed("attempt-1", artifact)

        assertFalse(first.ok)
        assertFalse(second.ok)
        assertTrue(first.retryable)
        assertTrue(second.retryable)
        assertEquals(2, client.ticketCalls)
        assertEquals(2, client.directCalls)
        assertEquals(0, client.finalizeCalls)
    }
}
