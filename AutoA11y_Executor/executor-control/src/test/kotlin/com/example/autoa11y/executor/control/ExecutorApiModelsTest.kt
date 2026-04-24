package com.example.autoa11y.executor.control

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ExecutorApiModelsTest {
    @Test
    fun heartbeatResponseParsesCommandsAndConfig() {
        val json = JSONObject(
            """
            {
              "registered": true,
              "serverTimeMs": 123456,
              "configVersion": "cfg-7",
              "runConfig": {
                "pollIntervalMs": 21000,
                "heartbeatIntervalMs": 33000
              },
              "commands": [
                {"type":"QUIESCE"},
                {"type":"CANCEL_ATTEMPT","attemptId":"attempt-9"}
              ]
            }
            """.trimIndent()
        )

        val response = HeartbeatResponse.fromJson(json)

        assertTrue(response.registered)
        assertEquals("cfg-7", response.configVersion)
        assertEquals(2, response.commands.size)
        assertEquals(ExecutorControlCommandType.QUIESCE, response.commands[0].type)
        assertEquals("attempt-9", response.commands[1].attemptId)
        assertEquals(21_000L, response.runConfig?.pollIntervalMs)
        assertEquals(33_000L, response.runConfig?.heartbeatIntervalMs)
    }

    @Test
    fun remoteTaskSerializesMultiDeviceFields() {
        val task = RemoteTask(
            taskId = "task-1",
            attemptId = "attempt-1",
            runId = "run-1",
            taskType = TaskTypes.PLUGIN_SMOKE,
            profilePackage = "com.google.android.apps.maps",
            taskPayload = JSONObject().put("query", "IKEA"),
            priority = 7,
            labels = listOf("maps", "smoke"),
            leaseExpireAt = 123456789L,
            scheduleVersion = "v2",
            idempotencyKey = "idem-1",
            artifactUploadMode = ArtifactUploadMode.DIRECT_PUT_V2
        )

        val parsed = RemoteTask.fromJson(task.toJson())

        assertEquals("run-1", parsed.runId)
        assertEquals(TaskTypes.PLUGIN_SMOKE, parsed.taskType)
        assertEquals("IKEA", parsed.taskPayload?.optString("query"))
        assertEquals(7, parsed.priority)
        assertEquals(listOf("maps", "smoke"), parsed.labels)
        assertEquals(123456789L, parsed.leaseExpireAt)
        assertEquals("v2", parsed.scheduleVersion)
        assertEquals("idem-1", parsed.idempotencyKey)
        assertEquals(ArtifactUploadMode.DIRECT_PUT_V2, parsed.artifactUploadMode)
    }

    @Test
    fun eventDtoCarriesRoutingKeys() {
        val event = RunEventDto(
            attemptId = "attempt-2",
            taskId = "task-2",
            deviceId = "device-2",
            runId = "run-2",
            eventType = "action_end",
            state = "RUNNING",
            code = "OK",
            message = "done"
        )

        val parsed = RunEventDto.fromJson(event.toJson())

        assertEquals("attempt-2", parsed.attemptId)
        assertEquals("task-2", parsed.taskId)
        assertEquals("device-2", parsed.deviceId)
        assertEquals("RUNNING", parsed.state)
        assertEquals("OK", parsed.code)
        assertFalse(parsed.ts <= 0L)
    }
}
