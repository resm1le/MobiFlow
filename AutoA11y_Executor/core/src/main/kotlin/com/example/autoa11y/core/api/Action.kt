package com.example.autoa11y.core.api

sealed class Action {
    data class Log(val message: String) : Action()
    data class Click(val sel: Selector) : Action()
    data class Input(val sel: Selector, val text: String, val clearFirst: Boolean = true) : Action()
    data class Wait(val sel: Selector, val timeoutMs: Long) : Action()
    data class CleanupDownloadArtifacts(
        val baseNames: List<String> = emptyList(),
        val downloadDir: String = "/sdcard/Download",
        val deleteAll: Boolean = false
    ) : Action()
    data class WaitForDownloadArtifact(
        val baseName: String,
        val downloadDir: String = "/sdcard/Download",
        val timeoutMs: Long = 90_000L,
        val pollIntervalMs: Long = 1_500L,
        val progressMonitor: DownloadProgressMonitor? = null,
        val restartReason: String? = null
    ) : Action()
    data class WaitForDownloadStart(
        val baseName: String,
        val downloadDir: String = "/sdcard/Download",
        val interfaceName: String = "wlan0",
        val timeoutMs: Long = 8_000L,
        val sampleIntervalMs: Long = 1_000L,
        val strongRxBytes: Long = 128L * 1024L,
        val sustainedRxBytes: Long = 64L * 1024L,
        val sustainedWindows: Int = 2,
        val cumulativeRxBytes: Long = 256L * 1024L,
        val restartReason: String? = null
    ) : Action()
    data class DownloadProgressMonitor(
        val interfaceName: String = "wlan0",
        val checkIntervalMs: Long = 30_000L,
        val minRxBytesPerCheck: Long = 256L * 1024L,
        val idleTimeoutMs: Long = 45_000L
    )
    /**
     * Strict smart click:
     * - click once
     * - optionally wait a short settle delay
     * - verify target page marker once
     *
     * No candidate switching, no retry policy here (Phase 3 STRICT only).
     */
    data class SmartClick(
        val trigger: Selector,
        val expectedMarker: Selector,
        val timeoutMs: Long = 6_000L,
        val settleDelayMs: Long = 250L
    ) : Action()
    /**
     * Navigation with page re-sync:
     * - click trigger
     * - wait for expected known page
     * - if expected page is not reached, resolve current known page
     * - if unknown, back out a few times to recover before requesting restart
     */
    data class Navigate(
        val trigger: Selector,
        val expectedPageId: String,
        val sourcePageId: String? = null,
        val fallbackTrigger: Selector? = null,
        val maxAttempts: Int = 3,
        val timeoutMs: Long = 6_000L,
        val settleDelayMs: Long = 250L,
        val unknownBackMax: Int = 2,
        val restartReason: String? = null
    ) : Action()
    data class Scroll(val times: Int, val direction: Direction) : Action()
    /**
     * 新增：通用滑动手势（坐标比值），用于水平或自定义滑动。
     */
    data class Swipe(
        val fromX: Float,
        val fromY: Float,
        val toX: Float,
        val toY: Float,
        val durationMs: Int = 300
    ) : Action()
    data class Sleep(val ms: Long) : Action()

    /** 新增：通用返回 */
    object Back : Action()
    /** 强制返回：无视“已在首页”检查，始终发送 Back */
    object BackForce : Action()
    /** Request a full scenario restart (circuit break). */
    data class RequestRestart(val reason: String) : Action()

    enum class Direction { UP, DOWN }
}
