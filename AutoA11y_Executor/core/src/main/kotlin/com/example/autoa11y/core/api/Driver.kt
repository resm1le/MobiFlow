package com.example.autoa11y.core.api

interface Driver {
    fun waitVisible(sel: Selector, timeoutMs: Long = 0): Boolean
    fun click(sel: Selector): Boolean
    fun input(sel: Selector, text: String, clearFirst: Boolean = true): Boolean
    fun scroll(steps: Int, dir: Action.Direction): Boolean
    /**
     * 新增：坐标比值滑动（用于水平或任意方向的滑动）。
     */
    fun swipe(fromXRatio: Float, fromYRatio: Float, toXRatio: Float, toYRatio: Float, durationMs: Int = 300): Boolean

    /** 新增：通用返回（优先 A11y，失败由实现兜底） */
    fun back(): Boolean

    /**
     * 结构化点击：返回含失败原因码的 [ActionResult]，旧代码可继续用 [click] 的布尔值。
     * 默认实现桥接到旧 [click]，Driver 子类按需覆写以提供精确诊断。
     */
    fun clickResolved(sel: Selector): ActionResult =
        if (click(sel)) ActionResult.success() else ActionResult.failure(ResolveResult.notFound(sel))

    /**
     * 结构化输入：返回含失败原因码的 [ActionResult]，旧代码可继续用 [input] 的布尔值。
     * 默认实现桥接到旧 [input]。
     */
    fun inputResolved(sel: Selector, text: String, clearFirst: Boolean = true): ActionResult =
        if (input(sel, text, clearFirst)) ActionResult.success()
        else ActionResult.failure(ResolveResult.notFound(sel))

    /**
     * 结构化可见性等待：返回含失败原因码的 [ActionResult]，旧代码可继续用 [waitVisible]。
     * 默认实现桥接到旧 [waitVisible]。
     */
    fun waitVisibleResolved(sel: Selector, timeoutMs: Long = 0): ActionResult =
        if (waitVisible(sel, timeoutMs)) ActionResult.success()
        else ActionResult.failure(ResolveResult.notFound(sel))
}
