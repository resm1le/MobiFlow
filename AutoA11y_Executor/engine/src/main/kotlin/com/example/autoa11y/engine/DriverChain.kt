package com.example.autoa11y.engine

import android.util.Log
import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.ActionResult
import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.core.api.ResolveCode
import com.example.autoa11y.core.api.Selector

private const val TAG_DC = "DriverChain"

/**
 * 统一驱动优先级：先 A11y，再 Shell。
 *
 * **fallback 触发规则（基于 ResolveCode）：**
 * - UNSUPPORTED  → A11y 不支持该选择器类型（如坐标），直接走 Shell，不走 A11y
 * - NOT_FOUND    → A11y 找不到节点，让 Shell 尝试
 * - NOT_CLICKABLE/ACTION_FAILED → 默认不 fallback；仅当 selector 自带坐标兜底时尝试 Shell
 * - SUCCESS      → A11y 成功，Shell 不介入
 */
class DriverChain(
    private val primary: Driver,
    private val fallback: Driver
) : Driver {

    override fun waitVisible(sel: Selector, timeoutMs: Long): Boolean =
        waitVisibleResolved(sel, timeoutMs).ok

    /** click() 桥接到 clickResolved()，返回布尔以保持旧接口兼容。 */
    override fun click(sel: Selector): Boolean = clickResolved(sel).ok

    override fun clickResolved(sel: Selector): ActionResult {
        // 坐标类直接旁路 primary，避免无意义调用和日志噪音。
        if (shouldBypassPrimary(sel)) {
            return fallback.clickResolved(sel)
        }

        val primaryResult = primary.clickResolved(sel)
        return when (primaryResult.resolve?.code) {
            // A11y 不支持该类型 → 直接走 Shell
            ResolveCode.UNSUPPORTED -> {
                Log.d(TAG_DC, "clickResolved UNSUPPORTED by primary, routing to fallback sel=$sel")
                fallback.clickResolved(sel)
            }
            // A11y 找不到节点 → Shell 尝试兜底
            ResolveCode.NOT_FOUND -> {
                Log.d(TAG_DC, "clickResolved NOT_FOUND by primary, trying fallback sel=$sel")
                val fbResult = fallback.clickResolved(sel)
                if (!fbResult.ok) Log.w(TAG_DC, "clickResolved fallback also failed sel=$sel")
                fbResult
            }
            ResolveCode.AMBIGUOUS -> {
                if (hasCoordinateFallback(sel)) {
                    Log.w(TAG_DC, "clickResolved AMBIGUOUS but selector has coordinate fallback, trying fallback sel=$sel")
                    fallback.clickResolved(sel)
                } else {
                    Log.w(TAG_DC, "clickResolved AMBIGUOUS, skip fallback sel=$sel reason=${primaryResult.resolve?.reason}")
                    primaryResult
                }
            }
            // A11y 找到但不可点击 → Shell 也无能为力，直接报告失败
            ResolveCode.NOT_CLICKABLE -> {
                if (hasCoordinateFallback(sel)) {
                    Log.w(TAG_DC, "clickResolved NOT_CLICKABLE but selector has coordinate fallback, trying fallback sel=$sel")
                    fallback.clickResolved(sel)
                } else {
                    Log.w(TAG_DC, "clickResolved NOT_CLICKABLE, skip fallback sel=$sel reason=${primaryResult.resolve?.reason}")
                    primaryResult
                }
            }
            ResolveCode.ACTION_FAILED -> {
                if (hasCoordinateFallback(sel)) {
                    Log.w(TAG_DC, "clickResolved ACTION_FAILED but selector has coordinate fallback, trying fallback sel=$sel")
                    fallback.clickResolved(sel)
                } else {
                    Log.w(TAG_DC, "clickResolved ACTION_FAILED, skip fallback sel=$sel reason=${primaryResult.resolve?.reason}")
                    primaryResult
                }
            }
            // 成功 or null（旧版 Driver 无 resolve 信息）
            ResolveCode.SUCCESS, null -> primaryResult
            // 其他兜底：尝试 fallback
            else -> {
                val fbResult = fallback.clickResolved(sel)
                fbResult
            }
        }
    }

    override fun input(sel: Selector, text: String, clearFirst: Boolean): Boolean =
        inputResolved(sel, text, clearFirst).ok

    override fun inputResolved(sel: Selector, text: String, clearFirst: Boolean): ActionResult {
        if (shouldBypassPrimary(sel)) {
            return fallback.inputResolved(sel, text, clearFirst)
        }

        val primaryResult = primary.inputResolved(sel, text, clearFirst)
        return when (primaryResult.resolve?.code) {
            ResolveCode.SUCCESS, null -> primaryResult
            ResolveCode.UNSUPPORTED, ResolveCode.NOT_FOUND -> {
                val fbResult = fallback.inputResolved(sel, text, clearFirst)
                if (!fbResult.ok) Log.w(TAG_DC, "inputResolved fallback also failed sel=$sel")
                fbResult
            }
            ResolveCode.AMBIGUOUS -> {
                if (hasCoordinateFallback(sel)) fallback.inputResolved(sel, text, clearFirst) else primaryResult
            }
            ResolveCode.NOT_CLICKABLE, ResolveCode.ACTION_FAILED -> {
                if (hasCoordinateFallback(sel)) {
                    fallback.inputResolved(sel, text, clearFirst)
                } else {
                    primaryResult
                }
            }
            else -> fallback.inputResolved(sel, text, clearFirst)
        }
    }

    override fun waitVisibleResolved(sel: Selector, timeoutMs: Long): ActionResult {
        if (shouldBypassPrimary(sel)) {
            return fallback.waitVisibleResolved(sel, timeoutMs)
        }

        val primaryResult = primary.waitVisibleResolved(sel, timeoutMs)
        if (primaryResult.ok) return primaryResult

        return when (primaryResult.resolve?.code) {
            ResolveCode.UNSUPPORTED, ResolveCode.NOT_FOUND -> fallback.waitVisibleResolved(sel, timeoutMs)
            else -> primaryResult
        }
    }

    override fun scroll(steps: Int, dir: Action.Direction): Boolean =
        primary.scroll(steps, dir) || fallback.scroll(steps, dir)

    override fun swipe(
        fromXRatio: Float,
        fromYRatio: Float,
        toXRatio: Float,
        toYRatio: Float,
        durationMs: Int
    ): Boolean = primary.swipe(fromXRatio, fromYRatio, toXRatio, toYRatio, durationMs) ||
        fallback.swipe(fromXRatio, fromYRatio, toXRatio, toYRatio, durationMs)

    override fun back(): Boolean = primary.back() || fallback.back()

    private fun shouldBypassPrimary(sel: Selector): Boolean = when (sel) {
        is Selector.CoordRatio, is Selector.CoordPx -> true
        else -> false
    }

    private fun hasCoordinateFallback(sel: Selector): Boolean = when (sel) {
        is Selector.CoordRatio, is Selector.CoordPx -> true
        is Selector.AnyOf -> sel.items.any { hasCoordinateFallback(it) }
        else -> false
    }
}
