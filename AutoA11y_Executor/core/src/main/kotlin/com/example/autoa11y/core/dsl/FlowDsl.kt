package com.example.autoa11y.core.dsl

import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.Condition
import com.example.autoa11y.core.api.PageSignature
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.Selector
import com.example.autoa11y.core.api.Step
import com.example.autoa11y.core.common.DeviceKeyboard
import kotlin.random.Random

fun flow(
    id: String,
    random: Random = Random(System.currentTimeMillis()),
    block: FlowBuilder.() -> Unit
): Scenario {
    val builder = FlowBuilder(id, random)
    builder.block()
    return builder.build()
}

class FlowBuilder internal constructor(
    private val id: String,
    private val random: Random
) {
    private val steps = mutableListOf<Step>()

    fun on(page: PageSignature, block: PageScope.() -> Unit) {
        PageScope(page, random, steps).block()
    }

    fun anyPage(block: ActionScope.() -> Unit) {
        val actions = ActionScope(random).apply(block).build()
        steps.add(Step(require = null, actions = actions))
    }

    fun build(): Scenario = Scenario(id, steps.toList())
}

@Suppress("UNUSED_PARAMETER")
class PageScope internal constructor(
    private val page: PageSignature,
    private val random: Random,
    private val steps: MutableList<Step>
) {
    fun perform(name: String = "", block: ActionScope.() -> Unit) {
        val actions = ActionScope(random).apply(block).build()
        steps.add(Step(require = Condition.OnPage(page), actions = actions))
    }

    fun attempt(name: String = "", block: ActionScope.() -> Unit): AttemptHandle {
        perform(name, block)
        return AttemptHandle(page, random, steps)
    }

    fun recover(name: String = "", block: ActionScope.() -> Unit) {
        perform(name, block)
    }

    internal fun requireOnPageAndNotTarget(targetMarker: Selector): Condition {
        val targetSig = PageSignature(page.pkg, must = listOf(targetMarker))
        return Condition.And(
            listOf(
                Condition.OnPage(page),
                Condition.Not(Condition.OnPage(targetSig))
            )
        )
    }

    @Suppress("UNUSED_PARAMETER")
    class AttemptHandle internal constructor(
        private val page: PageSignature,
        private val random: Random,
        private val steps: MutableList<Step>
    ) {
        fun recover(name: String = "", require: Condition? = null, block: ActionScope.() -> Unit) {
            val actions = ActionScope(random).apply(block).build()
            steps.add(Step(require = require ?: Condition.OnPage(page), actions = actions))
        }
    }
}

class ActionScope internal constructor(private val random: Random) {
    private val list = mutableListOf<Action>()

    fun log(message: String) {
        list.add(Action.Log(message))
    }

    fun click(sel: Selector) {
        list.add(Action.Click(sel))
    }

    fun input(sel: Selector, text: String, clear: Boolean = true) {
        list.add(Action.Input(sel, text, clear))
    }

    fun wait(sel: Selector, ms: Long) {
        list.add(Action.Wait(sel, ms))
    }

    fun cleanupDownloadArtifacts(
        baseNames: List<String> = emptyList(),
        downloadDir: String = "/sdcard/Download",
        deleteAll: Boolean = false
    ) {
        list.add(
            Action.CleanupDownloadArtifacts(
                baseNames = baseNames,
                downloadDir = downloadDir,
                deleteAll = deleteAll
            )
        )
    }

    fun waitForDownloadArtifact(
        baseName: String,
        downloadDir: String = "/sdcard/Download",
        timeoutMs: Long = 90_000L,
        pollIntervalMs: Long = 1_500L,
        progressMonitor: Action.DownloadProgressMonitor? = null,
        restartReason: String? = null
    ) {
        list.add(
            Action.WaitForDownloadArtifact(
                baseName = baseName,
                downloadDir = downloadDir,
                timeoutMs = timeoutMs,
                pollIntervalMs = pollIntervalMs,
                progressMonitor = progressMonitor,
                restartReason = restartReason
            )
        )
    }

    fun waitForDownloadStart(
        baseName: String,
        downloadDir: String = "/sdcard/Download",
        interfaceName: String = "wlan0",
        timeoutMs: Long = 8_000L,
        sampleIntervalMs: Long = 1_000L,
        strongRxBytes: Long = 128L * 1024L,
        sustainedRxBytes: Long = 64L * 1024L,
        sustainedWindows: Int = 2,
        cumulativeRxBytes: Long = 256L * 1024L,
        restartReason: String? = null
    ) {
        list.add(
            Action.WaitForDownloadStart(
                baseName = baseName,
                downloadDir = downloadDir,
                interfaceName = interfaceName,
                timeoutMs = timeoutMs,
                sampleIntervalMs = sampleIntervalMs,
                strongRxBytes = strongRxBytes,
                sustainedRxBytes = sustainedRxBytes,
                sustainedWindows = sustainedWindows,
                cumulativeRxBytes = cumulativeRxBytes,
                restartReason = restartReason
            )
        )
    }

    fun smartClick(
        trigger: Selector,
        expectedMarker: Selector,
        timeoutMs: Long = 6_000L,
        settleDelayMs: Long = 250L
    ) {
        list.add(
            Action.SmartClick(
                trigger = trigger,
                expectedMarker = expectedMarker,
                timeoutMs = timeoutMs,
                settleDelayMs = settleDelayMs
            )
        )
    }

    fun navigate(
        trigger: Selector,
        expectedPageId: String,
        sourcePageId: String? = null,
        fallbackTrigger: Selector? = null,
        maxAttempts: Int = 3,
        timeoutMs: Long = 6_000L,
        settleDelayMs: Long = 250L,
        unknownBackMax: Int = 2,
        restartReason: String? = null
    ) {
        list.add(
            Action.Navigate(
                trigger = trigger,
                expectedPageId = expectedPageId,
                sourcePageId = sourcePageId,
                fallbackTrigger = fallbackTrigger,
                maxAttempts = maxAttempts,
                timeoutMs = timeoutMs,
                settleDelayMs = settleDelayMs,
                unknownBackMax = unknownBackMax,
                restartReason = restartReason
            )
        )
    }

    fun verify(sel: Selector, timeout: Long = 5_000L) {
        wait(sel, timeout)
    }

    fun sleep(ms: Long) {
        list.add(Action.Sleep(ms))
    }

    fun pause(minMs: Long, maxMs: Long) {
        list.add(Action.Sleep(randomBetween(minMs, maxMs)))
    }

    fun pause(range: LongRange) {
        pause(range.first, range.last)
    }

    fun repeatRandom(range: IntRange, block: (index: Int) -> Unit) {
        val times = randomBetween(range.first, range.last)
        repeat(times) { index -> block(index) }
    }

    fun chance(probability: Float): Boolean = random.nextFloat() < probability

    fun scroll(times: Int, dir: Action.Direction = Action.Direction.UP) {
        list.add(Action.Scroll(times, dir))
    }

    fun swipe(
        fromX: Float,
        fromY: Float,
        toX: Float,
        toY: Float,
        durationMs: Int = 300
    ) {
        list.add(Action.Swipe(fromX, fromY, toX, toY, durationMs))
    }

    fun back() {
        list.add(Action.Back)
    }

    fun backForce() {
        list.add(Action.BackForce)
    }

    /** 点击键盘“回车/搜索/完成”键（设备固定坐标，通常由 ShellDriver 执行）。 */
    fun enterKey() {
        click(DeviceKeyboard.enterKey)
    }

    fun requestRestart(reason: String) {
        list.add(Action.RequestRestart(reason))
    }

    fun add(action: Action) {
        list.add(action)
    }

    fun addAll(actions: Iterable<Action>) {
        list.addAll(actions)
    }

    fun waitThenClick(sel: Selector, timeoutMs: Long, pauseRange: LongRange? = null) {
        wait(sel, timeoutMs)
        click(sel)
        pauseRange?.let { pause(it) }
    }

    fun clickThenWait(
        clickSel: Selector,
        waitSel: Selector,
        timeoutMs: Long,
        pauseRange: LongRange? = null
    ) {
        click(clickSel)
        pauseRange?.let { pause(it) }
        wait(waitSel, timeoutMs)
    }

    fun inputAndSubmit(
        editSel: Selector,
        text: String,
        submitSel: Selector? = null,
        clearFirst: Boolean = true,
        pauseAfterFocus: LongRange? = 700L..1_200L,
        pauseAfterInput: LongRange? = 1_000L..2_000L
    ) {
        click(editSel)
        if (clearFirst) {
            input(editSel, "", clear = true)
        }
        pauseAfterFocus?.let { pause(it) }
        input(editSel, text, clear = false)
        pauseAfterInput?.let { pause(it) }
        submitSel?.let { click(it) }
    }

    fun scrollBlock(
        timesRange: IntRange,
        dir: Action.Direction,
        pauseRange: LongRange? = null
    ) {
        repeatRandom(timesRange) {
            scroll(1, dir)
            pauseRange?.let { pause(it) }
        }
    }

    fun longPause(lowMs: Long, highMs: Long, biasHigh: Float = 0.5f) {
        sleep(longWatch(lowMs, highMs, biasHigh))
    }

    fun build(): List<Action> = list.toList()

    private fun randomBetween(min: Long, max: Long): Long =
        if (min >= max) min else random.nextLong(from = min, until = max + 1)

    private fun randomBetween(min: Int, max: Int): Int =
        if (min >= max) min else random.nextInt(from = min, until = max + 1)

    private fun longWatch(lowMs: Long, highMs: Long, biasHigh: Float): Long {
        val useHigh = random.nextFloat() < biasHigh
        return if (useHigh) {
            randomBetween(highMs / 3, highMs)
        } else {
            randomBetween(lowMs, highMs / 2)
        }
    }
}
