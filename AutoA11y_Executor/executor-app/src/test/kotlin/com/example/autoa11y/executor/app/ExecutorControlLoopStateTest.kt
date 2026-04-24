package com.example.autoa11y.executor.app

import com.example.autoa11y.executor.control.RunConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ExecutorControlLoopStateTest {
    @Test
    fun applyRunConfigUpdatesIntervals() {
        val state = ExecutorControlLoopState()

        state.apply(
            RunConfig(
                pollIntervalMs = 7_000L,
                heartbeatIntervalMs = 12_000L
            )
        )

        assertEquals(7_000L, state.config.pollIntervalMs)
        assertEquals(12_000L, state.config.heartbeatIntervalMs)
    }

    @Test
    fun registerFailureBacksOffAndSuccessResetsSchedule() {
        val state = ExecutorControlLoopState()
        val now = 1_000L

        assertTrue(state.shouldAttemptRegister(now))
        state.onRegisterFailure(now)
        assertFalse(state.shouldAttemptRegister(now + 1_000L))
        assertTrue(state.shouldAttemptRegister(now + 5_000L))

        state.onRegisterSuccess(now + 5_000L)
        assertTrue(state.shouldSendHeartbeat(now + 5_000L))
        assertTrue(state.shouldPoll(now + 5_000L))
    }

    @Test
    fun heartbeatFailureUsesExponentialBackoff() {
        val state = ExecutorControlLoopState()
        val now = 10_000L

        state.onHeartbeatFailure(now)
        assertFalse(state.shouldSendHeartbeat(now + 4_000L))
        assertTrue(state.shouldSendHeartbeat(now + 5_000L))

        state.onHeartbeatFailure(now + 5_000L)
        assertFalse(state.shouldSendHeartbeat(now + 12_000L))
        assertTrue(state.shouldSendHeartbeat(now + 15_000L))
    }
}
