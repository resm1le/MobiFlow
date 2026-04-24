package com.example.autoa11y.drivers.shell

import android.content.Context
import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.ActionResult
import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.core.api.NodeSummary
import com.example.autoa11y.core.api.ResolveResult
import com.example.autoa11y.core.api.Selector

class ShellDriver(private val ctx: Context, private val shell: ShellBridge) : Driver {

    override fun waitVisible(sel: Selector, timeoutMs: Long): Boolean = waitVisibleResolved(sel, timeoutMs).ok

    override fun waitVisibleResolved(sel: Selector, timeoutMs: Long): ActionResult =
        ActionResult.failure(
            ResolveResult.unsupported(sel),
            detail = "waitVisible is not supported by ShellDriver"
        )

    override fun click(sel: Selector): Boolean = clickResolved(sel).ok

    override fun clickResolved(sel: Selector): ActionResult {
        return when (sel) {
            is Selector.AnyOf -> {
                var lastFailure: ActionResult = ActionResult.failure(ResolveResult.notFound(sel))
                for (item in sel.items) {
                    val result = clickResolved(item)
                    if (result.ok) return result
                    lastFailure = result
                }
                lastFailure
            }
            is Selector.CoordRatio -> {
                val (x, y) = ShellCoords.fromRatio(ctx, sel.x, sel.y)
                val ok = shell.inputTap(x, y)
                if (ok) ActionResult.success(ResolveResult.success(sel.toSummary()))
                else ActionResult.failure(ResolveResult.actionFailed(sel.toSummary(), "shell inputTap failed"))
            }
            is Selector.CoordPx -> {
                val ok = shell.inputTap(sel.x, sel.y)
                if (ok) ActionResult.success(ResolveResult.success(sel.toSummary()))
                else ActionResult.failure(ResolveResult.actionFailed(sel.toSummary(), "shell inputTap failed"))
            }
            else -> ActionResult.failure(ResolveResult.unsupported(sel))
        }
    }

    override fun input(sel: Selector, text: String, clearFirst: Boolean): Boolean =
        inputResolved(sel, text, clearFirst).ok

    override fun inputResolved(sel: Selector, text: String, clearFirst: Boolean): ActionResult {
        return when (sel) {
            is Selector.AnyOf -> {
                var lastFailure: ActionResult = ActionResult.failure(ResolveResult.notFound(sel))
                for (item in sel.items) {
                    val result = inputResolved(item, text, clearFirst)
                    if (result.ok) return result
                    lastFailure = result
                }
                lastFailure
            }
            is Selector.CoordRatio -> {
                val (x, y) = ShellCoords.fromRatio(ctx, sel.x, sel.y)
                if (!shell.inputTap(x, y)) {
                    return ActionResult.failure(ResolveResult.actionFailed(sel.toSummary(), "shell inputTap failed"))
                }
                Thread.sleep(200)
                if (clearFirst) clearCurrentText()
                Thread.sleep(80)
                val ok = shell.inputText(text)
                if (ok) ActionResult.success(ResolveResult.success(sel.toSummary()))
                else ActionResult.failure(ResolveResult.actionFailed(sel.toSummary(), "shell inputText failed"))
            }
            is Selector.CoordPx -> {
                if (!shell.inputTap(sel.x, sel.y)) {
                    return ActionResult.failure(ResolveResult.actionFailed(sel.toSummary(), "shell inputTap failed"))
                }
                Thread.sleep(200)
                if (clearFirst) clearCurrentText()
                Thread.sleep(80)
                val ok = shell.inputText(text)
                if (ok) ActionResult.success(ResolveResult.success(sel.toSummary()))
                else ActionResult.failure(ResolveResult.actionFailed(sel.toSummary(), "shell inputText failed"))
            }
            else -> ActionResult.failure(ResolveResult.unsupported(sel))
        }
    }

    override fun scroll(steps: Int, dir: Action.Direction): Boolean {
        val (w, h) = ShellCoords.screenSize(ctx)
        repeat(steps) {
            val (fromY, toY) = when (dir) {
                Action.Direction.UP -> (h * 0.75f).toInt() to (h * 0.25f).toInt()
                Action.Direction.DOWN -> (h * 0.25f).toInt() to (h * 0.75f).toInt()
            }
            shell.inputSwipe(w / 2, fromY, w / 2, toY, 300)
        }
        return true
    }

    override fun swipe(
        fromXRatio: Float,
        fromYRatio: Float,
        toXRatio: Float,
        toYRatio: Float,
        durationMs: Int
    ): Boolean {
        val (x1, y1) = ShellCoords.fromRatio(ctx, fromXRatio, fromYRatio)
        val (x2, y2) = ShellCoords.fromRatio(ctx, toXRatio, toYRatio)
        return shell.inputSwipe(x1, y1, x2, y2, durationMs)
    }

    override fun back(): Boolean = shell.inputKey(4)

    private fun clearCurrentText() {
        shell.inputKey(123)
        Thread.sleep(50)
        repeat(40) {
            shell.inputKey(67)
            Thread.sleep(12)
        }
    }

    private fun Selector.toSummary(): NodeSummary = when (this) {
        is Selector.CoordRatio -> NodeSummary(
            text = "",
            desc = "",
            bounds = "ratio(${x},${y})",
            clickable = true
        )
        is Selector.CoordPx -> NodeSummary(
            text = "",
            desc = "",
            bounds = "px(${x},${y})",
            clickable = true
        )
        else -> NodeSummary(text = "", desc = "", bounds = toString(), clickable = false)
    }
}
