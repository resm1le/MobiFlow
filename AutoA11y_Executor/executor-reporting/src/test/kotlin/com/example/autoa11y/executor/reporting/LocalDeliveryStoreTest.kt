package com.example.autoa11y.executor.reporting

import com.example.autoa11y.executor.control.ArtifactDescriptor
import com.example.autoa11y.executor.control.RunEventDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

class LocalDeliveryStoreTest {
    @Test
    fun enqueuePeekAndDropAcrossKinds() {
        val dir = tempDir()
        try {
            val store = LocalDeliveryStore(dir)
            store.enqueueEvent(
                RunEventDto(
                    attemptId = "attempt-1",
                    taskId = "task-1",
                    deviceId = "device-1",
                    runId = "run-1",
                    eventType = "event",
                    message = "ok"
                )
            )
            store.enqueueTaskFinish("device-1", "task-1", "attempt-1", "run-1", "SUCCESS", "done")
            store.enqueueArtifact(
                "device-1",
                "attempt-1",
                ArtifactDescriptor(
                    attemptId = "attempt-1",
                    taskId = "task-1",
                    runId = "run-1",
                    artifactType = "run_log",
                    localPath = File(dir, "run.txt").absolutePath,
                    mimeType = "text/plain"
                )
            )

            val batch = store.peek(10)
            assertEquals(3, batch.size)
            assertEquals(DeliveryKind.EVENT, batch[0].kind)
            assertEquals(DeliveryKind.TASK_FINISH, batch[1].kind)
            assertEquals(DeliveryKind.ARTIFACT, batch[2].kind)

            store.drop(batch.take(2).map { it.id })
            val remaining = store.peek(10)
            assertEquals(1, remaining.size)
            assertEquals(DeliveryKind.ARTIFACT, remaining.first().kind)
            assertEquals("run_log", remaining.first().artifact?.artifactType)
        } finally {
            dir.deleteRecursively()
        }
    }

    @Test
    fun malformedEntriesAreDroppedDuringPeek() {
        val dir = tempDir()
        try {
            val store = LocalDeliveryStore(dir)
            File(dir, "00000000000000000001.json").writeText("{broken")

            val batch = store.peek(10)
            assertTrue(batch.isEmpty())
            assertTrue(dir.listFiles()?.none { it.name.endsWith(".json") } == true)
        } finally {
            dir.deleteRecursively()
        }
    }

    @Test
    fun queueIsTrimmedToBoundedSize() {
        val dir = tempDir()
        try {
            val store = LocalDeliveryStore(dir)
            repeat(505) { index ->
                store.enqueueEvent(
                    RunEventDto(
                        attemptId = "attempt-$index",
                        taskId = "task-$index",
                        deviceId = "device-1",
                        runId = "run-$index",
                        eventType = "event",
                        message = "msg-$index"
                    )
                )
            }

            val dataFiles = dir.listFiles()?.filter { it.name.endsWith(".json") }.orEmpty()
            assertEquals(500, dataFiles.size)
        } finally {
            dir.deleteRecursively()
        }
    }

    private fun tempDir(): File = Files.createTempDirectory("local-delivery-store-test").toFile()
}
