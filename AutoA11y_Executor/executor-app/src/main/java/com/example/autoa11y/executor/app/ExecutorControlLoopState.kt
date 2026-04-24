package com.example.autoa11y.executor.app

import com.example.autoa11y.executor.control.BuildConfig
import com.example.autoa11y.executor.control.RunConfig
import kotlin.math.max
import kotlin.math.min

data class ControlLoopConfig(
    val pollIntervalMs: Long = BuildConfig.DEFAULT_POLL_INTERVAL_MS,
    val heartbeatIntervalMs: Long = BuildConfig.DEFAULT_HEARTBEAT_INTERVAL_MS,
    val tickIntervalMs: Long = 2_000L,
    val failureBackoffBaseMs: Long = 5_000L,
    val failureBackoffMaxMs: Long = 60_000L
)

class ExecutorControlLoopState(
    initialConfig: ControlLoopConfig = ControlLoopConfig()
) {
    var config: ControlLoopConfig = initialConfig
        private set

    private var nextRegisterAt: Long = 0L
    private var nextHeartbeatAt: Long = 0L
    private var nextPollAt: Long = 0L
    private var registerFailures: Int = 0
    private var heartbeatFailures: Int = 0

    fun apply(runConfig: RunConfig) {
        config = config.copy(
            pollIntervalMs = runConfig.pollIntervalMs.coerceAtLeast(5_000L),
            heartbeatIntervalMs = runConfig.heartbeatIntervalMs.coerceAtLeast(10_000L)
        )
    }

    fun shouldAttemptRegister(now: Long): Boolean = now >= nextRegisterAt

    fun shouldSendHeartbeat(now: Long): Boolean = now >= nextHeartbeatAt

    fun shouldPoll(now: Long): Boolean = now >= nextPollAt

    fun onRegisterSuccess(now: Long) {
        registerFailures = 0
        nextRegisterAt = now
        nextHeartbeatAt = now
        nextPollAt = now
    }

    fun onRegisterFailure(now: Long) {
        registerFailures++
        nextRegisterAt = now + backoffMs(registerFailures)
    }

    fun onHeartbeatSuccess(now: Long) {
        heartbeatFailures = 0
        nextHeartbeatAt = now + config.heartbeatIntervalMs
    }

    fun onHeartbeatFailure(now: Long) {
        heartbeatFailures++
        nextHeartbeatAt = now + backoffMs(heartbeatFailures)
    }

    fun onPoll(now: Long) {
        nextPollAt = now + config.pollIntervalMs
    }

    fun forceRegisterNow(now: Long) {
        registerFailures = 0
        nextRegisterAt = now
    }

    fun consecutiveFailures(): Int = max(registerFailures, heartbeatFailures)

    private fun backoffMs(failures: Int): Long {
        val multiplier = 1L shl (failures - 1).coerceIn(0, 4)
        return min(config.failureBackoffBaseMs * multiplier, config.failureBackoffMaxMs)
    }
}
