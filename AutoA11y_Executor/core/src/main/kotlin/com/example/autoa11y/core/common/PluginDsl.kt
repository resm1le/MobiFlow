package com.example.autoa11y.core.common

import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.Condition
import com.example.autoa11y.core.api.Interceptor
import com.example.autoa11y.core.api.PageSignature
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.Selector
import com.example.autoa11y.core.api.Step
import kotlin.random.Random

/**
 * 轻量插件 DSL：封装常用的随机停顿、坐标点选、滚动组合等，减少重复样板。
 * 在插件侧复用同一个 [random]，可以得到更稳定的随机序列。
 */
class PluginDsl(private val random: Random = Random(System.currentTimeMillis())) {

    /** 构建器模式创建 Scenario，减少显式 mutableList 操作 */
    fun scenario(id: String, block: ScenarioBuilder.() -> Unit): Scenario =
        ScenarioBuilder(id).apply(block).build()

    /** 固定时长睡眠 */
    fun sleep(ms: Long): Action.Sleep = Action.Sleep(ms)

    /** 区间随机睡眠 */
    fun sleep(minMs: Long, maxMs: Long): Action.Sleep = Action.Sleep(randomBetween(minMs, maxMs))

    /** 生成固定坐标点击（坐标比值 0~1） */
    fun tap(xRatio: Float, yRatio: Float): Action.Click = Action.Click(Selector.CoordRatio(xRatio, yRatio))

    /** 在矩形区域内随机点击一次（坐标比值 0~1） */
    fun tapArea(
        xRange: ClosedFloatingPointRange<Float>,
        yRange: ClosedFloatingPointRange<Float>
    ): Action.Click {
        val x = random.nextDouble(xRange.start.toDouble(), xRange.endInclusive.toDouble()).toFloat()
        val y = random.nextDouble(yRange.start.toDouble(), yRange.endInclusive.toDouble()).toFloat()
        return tap(x, y)
    }

    /**
     * 组合滚动动作，可附带滚动间的随机停顿。
     * @param timesRange 滚动次数区间（含端点）
     * @param dir 滚动方向
     * @param pauseRange 每次滚动后的停顿区间；null 表示不插入停顿
     */
    fun scrollBlock(
        timesRange: IntRange,
        dir: Action.Direction,
        pauseRange: LongRange? = null
    ): List<Action> {
        val times = randomBetween(timesRange.first, timesRange.last)
        val actions = mutableListOf<Action>()
        repeat(times) {
            actions += Action.Scroll(1, dir)
            pauseRange?.let { actions += sleep(it.first, it.last) }
        }
        return actions
    }

    /**
     * 等待控件出现再点击，可选点击后停顿。
     */
    fun waitThenClick(sel: Selector, timeoutMs: Long, pauseRange: LongRange? = null): List<Action> =
        buildList {
            add(Action.Wait(sel, timeoutMs))
            add(Action.Click(sel))
            pauseRange?.let { add(sleep(it.first, it.last)) }
        }

    /**
     * 点击某控件后等待另一个控件出现，用于“跳转 -> 等待目标页”。
     */
    fun clickThenWait(
        clickSel: Selector,
        waitSel: Selector,
        timeoutMs: Long,
        pauseRange: LongRange? = null
    ): List<Action> = buildList {
        add(Action.Click(clickSel))
        pauseRange?.let { add(sleep(it.first, it.last)) }
        add(Action.Wait(waitSel, timeoutMs))
    }

    /** Strict smart click: click once, then verify target marker once. */
    fun smartClick(
        trigger: Selector,
        expectedMarker: Selector,
        timeoutMs: Long = 6_000L,
        settleDelayMs: Long = 250L
    ): Action.SmartClick = Action.SmartClick(
        trigger = trigger,
        expectedMarker = expectedMarker,
        timeoutMs = timeoutMs,
        settleDelayMs = settleDelayMs
    )

    /**
     * 输入并可选提交：先聚焦并清空（可配置），输入文本，最后点击提交控件。
     */
    fun inputAndSubmit(
        editSel: Selector,
        text: String,
        submitSel: Selector? = null,
        clearFirst: Boolean = true,
        pauseAfterFocus: LongRange? = 700L..1_200L,
        pauseAfterInput: LongRange? = 1_000L..2_000L
    ): List<Action> = buildList {
        add(Action.Click(editSel))
        if (clearFirst) add(Action.Input(editSel, ""))
        pauseAfterFocus?.let { add(sleep(it.first, it.last)) }
        add(Action.Input(editSel, text, clearFirst = false))
        pauseAfterInput?.let { add(sleep(it.first, it.last)) }
        submitSel?.let { add(Action.Click(it)) }
    }

    /**
     * 连续 Back，常用于回到上一级/首页。
     */
    fun backOff(times: Int = 1, pauseRange: LongRange = 1_000L..2_000L): List<Action> =
        buildList {
            repeat(times) {
                add(Action.BackForce)
                add(sleep(pauseRange.first, pauseRange.last))
            }
        }

    /**
     * 标准“搜索-提交-等待结果”片段。
     */
    fun searchFlow(
        entrySel: Selector,
        editSel: Selector,
        keyword: String,
        submitSel: Selector,
        resultSel: Selector,
        waitEntryMs: Long = 5_000,
        waitResultMs: Long = 8_000,
        pauses: SearchPauses = SearchPauses()
    ): List<Action> = buildList {
        add(Action.Wait(entrySel, waitEntryMs))
        add(Action.Click(entrySel))
        pauses.beforeFocus?.let { add(sleep(it.first, it.last)) }
        add(Action.Wait(editSel, waitEntryMs))
        add(Action.Click(editSel))
        pauses.beforeInput?.let { add(sleep(it.first, it.last)) }
        add(Action.Input(editSel, "", clearFirst = true))
        pauses.afterClear?.let { add(sleep(it.first, it.last)) }
        add(Action.Input(editSel, keyword, clearFirst = false))
        pauses.afterInput?.let { add(sleep(it.first, it.last)) }
        add(Action.Click(submitSel))
        pauses.afterSubmit?.let { add(sleep(it.first, it.last)) }
        add(Action.Wait(resultSel, waitResultMs))
    }

    /**
     * 标准“列表浏览 + 结果点击”片段。
     */
    fun browseListAndOpen(
        scrollTimes: IntRange,
        scrollDir: Action.Direction = Action.Direction.UP,
        scrollPause: LongRange = 1_500L..3_000L,
        entryTap: Action.Click,
        preOpenPause: LongRange = 1_000L..2_000L,
        postOpenPause: LongRange = 2_000L..4_000L
    ): List<Action> = buildList {
        addAll(scrollBlock(scrollTimes, scrollDir, pauseRange = scrollPause))
        addAll(
            listOf(
                sleep(preOpenPause.first, preOpenPause.last),
                entryTap,
                sleep(postOpenPause.first, postOpenPause.last)
            )
        )
    }

    /** 随机长时间观看，用于视频播放等场景 */
    fun longWatch(lowMs: Long, highMs: Long, biasHigh: Float = 0.5f): Long {
        val useHigh = random.nextFloat() < biasHigh
        return if (useHigh) randomBetween(highMs / 3, highMs) else randomBetween(lowMs, highMs / 2)
    }

    fun randomBetween(min: Int, max: Int): Int =
        if (min >= max) min else random.nextInt(from = min, until = max + 1)

    fun randomBetween(min: Long, max: Long): Long =
        if (min >= max) min else random.nextLong(from = min, until = max + 1)
}

/** 标准化首页签名构造，避免各插件手写 PageSignature */
fun homeSignature(pkg: String, must: List<Selector> = emptyList()): PageSignature =
    PageSignature(pkg, must)

/**
 * 统一的关键词弹窗拦截器工厂，可叠加额外词汇与调节次数/间隔
 *
 * @param enabled 是否启用拦截器，默认 false（不生效）。如需启用请显式传入 true
 */
fun keywordPopupInterceptor(
    extra: List<String> = emptyList(),
    rounds: Int = 2,
    pauseMs: Long = 200,
    enabled: Boolean = false
): Interceptor = PopupDismissInterceptor(
    keywords = PopupDismissInterceptor.DEFAULT_KEYWORDS + extra,
    rounds = rounds,
    pauseMs = pauseMs,
    enabled = enabled
)

/**
 * 场景构建器：更接近声明式写法，避免直接维护 Step/Action 列表。
 */
class ScenarioBuilder(private val id: String) {
    private val steps = mutableListOf<Step>()

    fun step(require: Condition? = null, block: MutableList<Action>.() -> Unit) {
        val actions = mutableListOf<Action>()
        block.invoke(actions)
        steps += Step(require = require, actions = actions.toList())
    }

    fun build(): Scenario = Scenario(id = id, steps = steps.toList())
}

data class SearchPauses(
    val beforeFocus: LongRange? = 500L..900L,
    val beforeInput: LongRange? = 500L..900L,
    val afterClear: LongRange? = 500L..900L,
    val afterInput: LongRange? = 1_000L..2_000L,
    val afterSubmit: LongRange? = 1_000L..2_000L
)
