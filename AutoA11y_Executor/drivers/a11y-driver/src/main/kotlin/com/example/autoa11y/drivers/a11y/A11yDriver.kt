package com.example.autoa11y.drivers.a11y

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.os.Bundle
import android.os.SystemClock
import android.util.Log
import android.view.accessibility.AccessibilityNodeInfo
import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.ActionResult
import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.core.api.NodeSummary
import com.example.autoa11y.core.api.ResolveCode
import com.example.autoa11y.core.api.ResolveResult
import com.example.autoa11y.core.api.Selector

private const val TAG_AD = "A11yDriver"

/**
 * 无障碍驱动：负责通过 A11y 执行点击/输入/等待/滚动/返回。
 * 与 Driver 接口保持一致：
 *  - scroll(steps: Int, dir: Action.Direction): Boolean
 *  - back(): Boolean
 */
class A11yDriver(private val svc: AutomationService) : Driver {

    private fun hasClickAction(node: AccessibilityNodeInfo): Boolean =
        node.actionList?.any { it.id == AccessibilityNodeInfo.ACTION_CLICK } == true

    private fun hasSetTextAction(node: AccessibilityNodeInfo): Boolean =
        node.actionList?.any { it.id == AccessibilityNodeInfo.ACTION_SET_TEXT } == true

    private fun root(): AccessibilityNodeInfo? {
        val r = svc.rootInActiveWindow
        if (r == null) Log.w(TAG_AD, "root is null (window not ready / not in foreground?)")
        return r
    }

    private fun editableAncestor(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        var current: AccessibilityNodeInfo? = node
        while (current != null) {
            val isEditClass = current.className?.contains("EditText", ignoreCase = true) == true
            if ((current.isEditable || isEditClass) && current.isEnabled) {
                return current
            }
            current = current.parent
        }
        return null
    }

    private fun compileRegexOrNull(pattern: String): Regex? =
        runCatching { Regex(pattern) }.getOrNull()

    private fun matchesByTextRule(
        actual: String,
        sel: Selector.ByText,
        compiledRegex: Regex? = null
    ): Boolean {
        if (sel.regex) {
            val regex = compiledRegex ?: compileRegexOrNull(sel.text) ?: return false
            return regex.containsMatchIn(actual)
        }
        return if (sel.contains) actual.contains(sel.text) else actual == sel.text
    }

    private fun findNodesByText(sel: Selector.ByText): List<AccessibilityNodeInfo> {
        // regex 模式必须走 DFS，系统 API 不支持正则
        if (sel.regex) {
            val compiled = compileRegexOrNull(sel.text) ?: run {
                Log.w(TAG_AD, "find ByText invalid regex: ${sel.text}")
                return emptyList()
            }
            val acc = mutableListOf<AccessibilityNodeInfo>()
            fun dfs(n: AccessibilityNodeInfo?) {
                if (n == null) return
                val t = n.text?.toString()
                if (n.isVisibleToUser && !t.isNullOrEmpty() && compiled.containsMatchIn(t)) acc.add(n)
                for (i in 0 until n.childCount) dfs(n.getChild(i))
            }
            dfs(root())
            return acc
        }

        // 系统 API 粗筛（语义是 contains）
        val candidates = root()
            ?.findAccessibilityNodeInfosByText(sel.text)
            ?.filter { it.isVisibleToUser }
            ?: return emptyList()

        // contains=true：系统 API 语义与 Selector 完全一致，直接返回
        if (sel.contains) return candidates

        // contains=false（精确匹配）：在系统 API 返回的超集中做精确过滤
        return candidates.filter { it.text?.toString() == sel.text }
    }

    private fun findNodesByDesc(sel: Selector.ByDesc): List<AccessibilityNodeInfo> {
        fun dfs(n: AccessibilityNodeInfo?, acc: MutableList<AccessibilityNodeInfo>) {
            if (n == null) return
            val d = n.contentDescription?.toString() ?: ""
            if (n.isVisibleToUser && ((sel.contains && d.contains(sel.desc)) || (!sel.contains && d == sel.desc))) {
                acc.add(n)
            }
            for (i in 0 until n.childCount) dfs(n.getChild(i), acc)
        }
        val acc = mutableListOf<AccessibilityNodeInfo>()
        dfs(root(), acc)
        return acc
    }

    private fun findNodesByClass(sel: Selector.ByClass): List<AccessibilityNodeInfo> {
        fun dfs(n: AccessibilityNodeInfo?, acc: MutableList<AccessibilityNodeInfo>) {
            if (n == null) return
            val cls = n.className?.toString() ?: ""
            val match = if (sel.contains) cls.contains(sel.name) else cls == sel.name
            if (n.isVisibleToUser && match) {
                acc.add(n)
            }
            for (i in 0 until n.childCount) dfs(n.getChild(i), acc)
        }
        val acc = mutableListOf<AccessibilityNodeInfo>()
        dfs(root(), acc)
        return acc
    }

    /**
     * 检查单个节点是否匹配简单选择器（不递归）。
     * 供 HasDescendant / Within 在 DFS 子树遍历时使用。
     */
    private fun matchesSimple(n: AccessibilityNodeInfo, sel: Selector): Boolean = when (sel) {
        is Selector.ById -> n.viewIdResourceName == sel.id
        is Selector.ByIdSelected -> n.viewIdResourceName == sel.id && n.isSelected == sel.selected
        is Selector.ByText -> {
            val t = n.text?.toString() ?: ""
            matchesByTextRule(t, sel)
        }
        is Selector.ByDesc -> {
            val d = n.contentDescription?.toString() ?: ""
            if (sel.contains) d.contains(sel.desc) else d == sel.desc
        }
        is Selector.ByClass -> {
            val cls = n.className?.toString() ?: ""
            if (sel.contains) cls.contains(sel.name) else cls == sel.name
        }
        is Selector.AnyOf -> sel.items.any { matchesSimple(n, it) }
        // 关系型/坐标型不支持简单匹配
        else -> false
    }

    private fun findEditable(preferBottom: Boolean): AccessibilityNodeInfo? {
        fun isEditableNode(n: AccessibilityNodeInfo): Boolean =
            (n.isEditable || n.className?.contains("EditText", ignoreCase = true) == true) &&
                n.isEnabled && n.isVisibleToUser

        fun dfs(n: AccessibilityNodeInfo?, acc: MutableList<AccessibilityNodeInfo>) {
            if (n == null) return
            if (isEditableNode(n)) acc.add(n)
            for (i in 0 until n.childCount) dfs(n.getChild(i), acc)
        }

        val acc = mutableListOf<AccessibilityNodeInfo>()
        dfs(root(), acc)
        if (acc.isEmpty()) {
            Log.d(TAG_AD, "find Editable miss")
            return null
        }
        if (!preferBottom) {
            return acc.firstOrNull { hasSetTextAction(it) }
                ?: acc.firstOrNull { it.isFocused }
                ?: acc.firstOrNull()
        }

        var best: AccessibilityNodeInfo? = null
        var bestBottom = Int.MIN_VALUE
        val r = Rect()
        val pool = acc.filter { hasSetTextAction(it) }.ifEmpty { acc }
        for (n in pool) {
            n.getBoundsInScreen(r)
            if (r.bottom > bestBottom) {
                bestBottom = r.bottom
                best = n
            }
        }
        return best
    }

    private class AnyOfCandidate {
        var editable: AccessibilityNodeInfo? = null
        var clickable: AccessibilityNodeInfo? = null
        var any: AccessibilityNodeInfo? = null

        fun best(): AccessibilityNodeInfo? = editable ?: clickable ?: any
    }

    private fun findAnyTextOrDesc(items: List<Selector>): AccessibilityNodeInfo? {
        if (items.isEmpty()) return null

        data class TextSel(
            val index: Int,
            val rule: Selector.ByText,
            val regex: Regex? = null
        )
        data class DescSel(val index: Int, val desc: String, val contains: Boolean)

        val textSels = mutableListOf<TextSel>()
        val descSels = mutableListOf<DescSel>()
        items.forEachIndexed { index, sel ->
            when (sel) {
                is Selector.ByText -> {
                    if (sel.regex) {
                        val regex = compileRegexOrNull(sel.text)
                        if (regex == null) {
                            Log.w(TAG_AD, "find AnyOf invalid regex: ${sel.text}")
                        } else {
                            textSels.add(TextSel(index = index, rule = sel, regex = regex))
                        }
                    } else {
                        textSels.add(TextSel(index = index, rule = sel))
                    }
                }
                is Selector.ByDesc -> descSels.add(DescSel(index, sel.desc, sel.contains))
                else -> Unit
            }
        }
        if (textSels.isEmpty() && descSels.isEmpty()) return null

        val candidates = Array(items.size) { AnyOfCandidate() }

        fun considerText(index: Int, node: AccessibilityNodeInfo) {
            val candidate = candidates[index]
            if (candidate.editable != null) return
            val editable = editableAncestor(node)
            if (editable != null) {
                candidate.editable = editable
                return
            }
            if (candidate.clickable == null && (node.isFocusable || node.isClickable)) {
                candidate.clickable = node
                return
            }
            if (candidate.any == null) {
                candidate.any = node
            }
        }

        fun considerDesc(index: Int, node: AccessibilityNodeInfo) {
            val candidate = candidates[index]
            if (candidate.editable != null) return
            if (node.isEditable || node.className?.contains("EditText", ignoreCase = true) == true) {
                candidate.editable = node
                return
            }
            if (candidate.clickable == null && (node.isFocusable || node.isClickable)) {
                candidate.clickable = node
                return
            }
            if (candidate.any == null) {
                candidate.any = node
            }
        }

        fun dfs(n: AccessibilityNodeInfo?) {
            if (n == null) return
            if (n.isVisibleToUser) {
                val text = n.text?.toString()
                if (!text.isNullOrEmpty()) {
                    for (sel in textSels) {
                        if (matchesByTextRule(text, sel.rule, sel.regex)) {
                            considerText(sel.index, n)
                        }
                    }
                }
                val desc = n.contentDescription?.toString()
                if (!desc.isNullOrEmpty()) {
                    for (sel in descSels) {
                        if ((sel.contains && desc.contains(sel.desc)) || (!sel.contains && desc == sel.desc)) {
                            considerDesc(sel.index, n)
                        }
                    }
                }
            }
            for (i in 0 until n.childCount) dfs(n.getChild(i))
        }

        dfs(root())
        for (i in items.indices) {
            val node = candidates[i].best()
            if (node != null) return node
        }
        return null
    }

    private fun findAll(sel: Selector): List<AccessibilityNodeInfo>? {
        return when (sel) {
            is Selector.ById ->
                root()?.findAccessibilityNodeInfosByViewId(sel.id)?.filter { it.isVisibleToUser } ?: emptyList()
            is Selector.ByIdSelected ->
                root()?.findAccessibilityNodeInfosByViewId(sel.id)
                    ?.filter { it.isVisibleToUser && it.isSelected == sel.selected }
                    ?: emptyList()
            is Selector.ByText -> findNodesByText(sel)
            is Selector.ByDesc -> findNodesByDesc(sel)
            is Selector.ByClass -> findNodesByClass(sel)
            is Selector.AnyOf ->
                sel.items.asSequence()
                    .mapNotNull { findAll(it) }
                    .firstOrNull { it.isNotEmpty() }
                    ?: emptyList()
            is Selector.Editable -> listOfNotNull(findEditable(sel.preferBottom))
            is Selector.ClickableAncestorOf,
            is Selector.HasDescendant,
            is Selector.Within -> listOfNotNull(find(sel))
            is Selector.CoordRatio,
            is Selector.CoordPx -> null
        }
    }

    private fun find(sel: Selector): AccessibilityNodeInfo? = when (sel) {
        is Selector.ById -> {
            val nodes = root()?.findAccessibilityNodeInfosByViewId(sel.id)
            val node = nodes
                ?.firstOrNull { it.isEditable || it.className?.contains("EditText", ignoreCase = true) == true }
                ?: nodes?.firstOrNull { it.isFocusable || it.isClickable }
                ?: nodes?.firstOrNull()
            if (node == null) Log.d(TAG_AD, "find ById miss: ${sel.id}")
            node
        }
        is Selector.ByIdSelected -> {
            val nodes = root()?.findAccessibilityNodeInfosByViewId(sel.id)
            val filtered = nodes?.filter { it.isSelected == sel.selected }
            val node = filtered
                ?.firstOrNull { it.isEditable || it.className?.contains("EditText", ignoreCase = true) == true }
                ?: filtered?.firstOrNull { it.isFocusable || it.isClickable }
                ?: filtered?.firstOrNull()
            if (node == null) Log.d(TAG_AD, "find ByIdSelected miss: ${sel.id} selected=${sel.selected}")
            node
        }
        is Selector.ByText -> {
            val nodes = findNodesByText(sel)
            if (nodes.isNullOrEmpty()) {
                Log.d(TAG_AD, "find ByText miss: ${sel.text}")
                null
            } else {
                var node: AccessibilityNodeInfo? = null
                for (cand in nodes) {
                    node = editableAncestor(cand)
                    if (node != null) break
                }
                if (node == null) {
                    node = nodes.firstOrNull { it.isFocusable || it.isClickable } ?: nodes.firstOrNull()
                }
                node
            }
        }
        is Selector.ByDesc -> {
            fun dfs(n: AccessibilityNodeInfo?, acc: MutableList<AccessibilityNodeInfo>) {
                if (n == null) return
                val d = n.contentDescription?.toString() ?: ""
                if ((sel.contains && d.contains(sel.desc)) || (!sel.contains && d == sel.desc)) {
                    acc.add(n)
                }
                for (i in 0 until n.childCount) dfs(n.getChild(i), acc)
            }
            val acc = mutableListOf<AccessibilityNodeInfo>()
            dfs(root(), acc)
            val node = acc.firstOrNull { it.isEditable || it.className?.contains("EditText", ignoreCase = true) == true }
                ?: acc.firstOrNull { it.isFocusable || it.isClickable }
                ?: acc.firstOrNull()
            if (node == null) Log.d(TAG_AD, "find ByDesc miss: ${sel.desc} (contains=${sel.contains})")
            node
        }
        is Selector.ByClass -> {
            fun dfs(n: AccessibilityNodeInfo?, acc: MutableList<AccessibilityNodeInfo>) {
                if (n == null) return
                val cls = n.className?.toString() ?: ""
                val match = if (sel.contains) cls.contains(sel.name) else cls == sel.name
                if (match) {
                    acc.add(n)
                }
                for (i in 0 until n.childCount) dfs(n.getChild(i), acc)
            }
            val acc = mutableListOf<AccessibilityNodeInfo>()
            dfs(root(), acc)
            val node = acc.firstOrNull { it.isEditable || it.className?.contains("EditText", ignoreCase = true) == true }
                ?: acc.firstOrNull { it.isFocusable || it.isClickable }
                ?: acc.firstOrNull()
            if (node == null) Log.d(TAG_AD, "find ByClass miss: ${sel.name} (contains=${sel.contains})")
            node
        }
        is Selector.AnyOf -> {
            val allTextOrDesc = sel.items.all { it is Selector.ByText || it is Selector.ByDesc }
            val node = if (allTextOrDesc) {
                findAnyTextOrDesc(sel.items)
            } else {
                sel.items.asSequence().mapNotNull { find(it) }.firstOrNull()
            }
            if (node == null) Log.d(TAG_AD, "find AnyOf miss: ${sel.items}")
            node
        }
        is Selector.Editable -> findEditable(sel.preferBottom)

        // ──────────────────────────────────────────────────────────────────────
        // 关系型选择器（Phase 1）
        // ──────────────────────────────────────────────────────────────────────

        is Selector.ClickableAncestorOf -> findClickableAncestorOf(sel)
        is Selector.HasDescendant -> findHasDescendant(sel)
        is Selector.Within -> findWithin(sel)

        is Selector.CoordRatio -> null // 坐标类交给 Shell 兜底
        is Selector.CoordPx -> null // 坐标类交给 Shell 兜底
    }

    private fun findClickableAncestorOf(sel: Selector.ClickableAncestorOf): AccessibilityNodeInfo? {
        val child = find(sel.child)
        if (child == null) {
            Log.d(TAG_AD, "find ClickableAncestorOf: child miss sel=${sel.child}")
            return null
        }
        var current: AccessibilityNodeInfo? = child
        var depth = 0
        while (current != null && depth <= sel.maxDepth) {
            if (current.isClickable || hasClickAction(current)) {
                Log.d(TAG_AD, "find ClickableAncestorOf: found at depth=$depth sel=$sel")
                return current
            }
            current = current.parent
            depth++
        }
        Log.d(TAG_AD, "find ClickableAncestorOf: no clickable ancestor within maxDepth=${sel.maxDepth} sel=$sel")
        return null
    }

    private fun findHasDescendant(sel: Selector.HasDescendant): AccessibilityNodeInfo? {
        val parent = find(sel.parent)
        if (parent == null) {
            Log.d(TAG_AD, "find HasDescendant: parent miss sel=${sel.parent}")
            return null
        }
        fun dfs(n: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
            if (n == null) return null
            if (matchesSimple(n, sel.child)) return n
            for (i in 0 until n.childCount) {
                val found = dfs(n.getChild(i))
                if (found != null) return found
            }
            return null
        }
        val result = dfs(parent)
        if (result == null) Log.d(TAG_AD, "find HasDescendant: child not found in subtree sel=$sel")
        return result
    }

    private fun findWithin(sel: Selector.Within): AccessibilityNodeInfo? {
        val scope = find(sel.scope)
        if (scope == null) {
            Log.d(TAG_AD, "find Within: scope miss sel=${sel.scope}")
            return null
        }
        fun dfs(n: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
            if (n == null) return null
            if (matchesSimple(n, sel.target)) return n
            for (i in 0 until n.childCount) {
                val found = dfs(n.getChild(i))
                if (found != null) return found
            }
            return null
        }
        val result = dfs(scope)
        if (result == null) Log.d(TAG_AD, "find Within: target not found in scope sel=$sel")
        return result
    }

    override fun waitVisible(sel: Selector, timeoutMs: Long): Boolean = waitVisibleResolved(sel, timeoutMs).ok

    override fun waitVisibleResolved(sel: Selector, timeoutMs: Long): ActionResult {
        if (sel is Selector.CoordRatio || sel is Selector.CoordPx) {
            return ActionResult.failure(ResolveResult.unsupported(sel))
        }

        if (timeoutMs <= 0) {
            val node = find(sel)
            return if (node != null) {
                Log.i(TAG_AD, "waitVisibleResolved SUCCESS sel=$sel")
                ActionResult.success(ResolveResult.success(node.toSummary()))
            } else {
                ActionResult.failure(ResolveResult.notFound(sel))
            }
        }

        val end = SystemClock.uptimeMillis() + timeoutMs
        while (SystemClock.uptimeMillis() < end) {
            val node = find(sel)
            if (node != null) {
                Log.i(TAG_AD, "waitVisibleResolved SUCCESS sel=$sel")
                return ActionResult.success(ResolveResult.success(node.toSummary()))
            }
            SystemClock.sleep(200)
        }
        Log.w(TAG_AD, "waitVisibleResolved TIMEOUT sel=$sel after ${timeoutMs}ms")
        return ActionResult.failure(
            ResolveResult(
                code = ResolveCode.NOT_FOUND,
                reason = "wait timeout after ${timeoutMs}ms: $sel"
            )
        )
    }

    /** click() 桥接到 clickResolved()，保持旧接口兼容。 */
    override fun click(sel: Selector): Boolean = clickResolved(sel).ok

    override fun clickResolved(sel: Selector): ActionResult {
        // 坐标类选择器 A11yDriver 不支持，直接返回 UNSUPPORTED
        if (sel is Selector.CoordRatio || sel is Selector.CoordPx) {
            Log.d(TAG_AD, "clickResolved UNSUPPORTED sel=$sel")
            return ActionResult.failure(ResolveResult.unsupported(sel))
        }

        val rawCandidates = findAll(sel)
        if (rawCandidates == null) {
            Log.d(TAG_AD, "clickResolved UNSUPPORTED sel=$sel")
            return ActionResult.failure(ResolveResult.unsupported(sel))
        }
        if (rawCandidates.isEmpty()) {
            Log.w(TAG_AD, "clickResolved NOT_FOUND sel=$sel")
            return ActionResult.failure(ResolveResult.notFound(sel))
        }

        val clickableTargets = mutableListOf<AccessibilityNodeInfo>()
        for (candidate in rawCandidates) {
            val target = findClickableTarget(candidate)
            if (target != null) clickableTargets.add(target)
        }

        val uniqueTargets = mutableListOf<AccessibilityNodeInfo>()
        val seen = mutableSetOf<String>()
        for (target in clickableTargets) {
            val summary = target.toSummary()
            val key = "${summary.bounds}|${summary.text}|${summary.desc}|${summary.clickable}"
            if (seen.add(key)) {
                uniqueTargets.add(target)
            }
        }

        if (uniqueTargets.size > 1) {
            val candidates = uniqueTargets.map { it.toSummary() }
            Log.w(TAG_AD, "clickResolved AMBIGUOUS sel=$sel candidates=${candidates.size}")
            return ActionResult.failure(ResolveResult.ambiguous(candidates, sel))
        }

        if (uniqueTargets.isEmpty()) {
            val summary = rawCandidates.first().toSummary()
            Log.w(TAG_AD, "clickResolved NOT_CLICKABLE sel=$sel node=$summary")
            return ActionResult.failure(ResolveResult.notClickable(summary))
        }

        val target = uniqueTargets.first()
        val ok = target.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        return if (ok) {
            Log.i(TAG_AD, "clickResolved SUCCESS sel=$sel via=resolved")
            ActionResult.success(ResolveResult.success(target.toSummary()))
        } else {
            val summary = target.toSummary()
            Log.w(TAG_AD, "clickResolved ACTION_FAILED sel=$sel node=$summary")
            ActionResult.failure(ResolveResult.actionFailed(summary))
        }
    }

    /** 将 AccessibilityNodeInfo 转换为轻量摘要（不持有节点引用）。 */
    private fun AccessibilityNodeInfo.toSummary(): NodeSummary {
        val rect = Rect().also { getBoundsInScreen(it) }
        return NodeSummary(
            text = text?.toString() ?: "",
            desc = contentDescription?.toString() ?: "",
            bounds = rect.toShortString(),
            clickable = isClickable || hasClickAction(this)
        )
    }

    private fun findClickableTarget(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        var current = node
        while (current != null) {
            if (current.isClickable || current.isFocusable || hasClickAction(current)) {
                return current
            }
            current = current.parent
        }
        return null
    }

    override fun input(sel: Selector, text: String, clearFirst: Boolean): Boolean =
        inputResolved(sel, text, clearFirst).ok

    override fun inputResolved(sel: Selector, text: String, clearFirst: Boolean): ActionResult {
        if (sel is Selector.CoordRatio || sel is Selector.CoordPx) {
            return ActionResult.failure(ResolveResult.unsupported(sel))
        }

        val n = find(sel) ?: run {
            Log.w(TAG_AD, "inputResolved NOT_FOUND sel=$sel")
            return ActionResult.failure(ResolveResult.notFound(sel))
        }
        val target = editableAncestor(n) ?: n

        if (!target.isFocused) {
            val focusOk = target.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
            Log.d(TAG_AD, "inputResolved focus attempt focusOk=$focusOk sel=$sel")
        }
        if (clearFirst) {
            val cleared = target.performAction(
                AccessibilityNodeInfo.ACTION_SET_TEXT,
                Bundle().apply {
                    putCharSequence(
                        AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, ""
                    )
                }
            )
            Log.d(TAG_AD, "inputResolved clearFirst=$clearFirst cleared=$cleared")
        }
        val ok = target.performAction(
            AccessibilityNodeInfo.ACTION_SET_TEXT,
            Bundle().apply {
                putCharSequence(
                    AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text
                )
            }
        )
        return if (ok) {
            Log.i(TAG_AD, "inputResolved SUCCESS sel=$sel")
            ActionResult.success(ResolveResult.success(target.toSummary()))
        } else {
            val summary = target.toSummary()
            Log.w(TAG_AD, "inputResolved ACTION_FAILED sel=$sel node=$summary")
            ActionResult.failure(ResolveResult.actionFailed(summary, "performAction(ACTION_SET_TEXT) returned false"))
        }
    }

    /**
     * 新签名：参数为 (steps, dir)，并返回 Boolean。
     * 这里在根节点尝试滚动；需要更稳时可先定位到可滚动容器再滚。
     */
    override fun scroll(steps: Int, dir: Action.Direction): Boolean {
        var any = false
        repeat(steps) {
            val node = root()
            val nodeAction = when (dir) {
                Action.Direction.UP -> AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
                Action.Direction.DOWN -> AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
            }
            val once = node?.performAction(nodeAction) ?: false
            Log.i(TAG_AD, "scroll once=$once dir=$dir")
            any = any or once
            SystemClock.sleep(300)
        }
        return any
    }

    /**
     * A11y 不提供原生坐标 swipe；返回 false 让 ShellDriver 执行。
     */
    override fun swipe(
        fromXRatio: Float,
        fromYRatio: Float,
        toXRatio: Float,
        toYRatio: Float,
        durationMs: Int
    ): Boolean {
        Log.d(TAG_AD, "swipe not supported by A11yDriver; delegating to fallback")
        return false
    }

    /** 通用全局返回 */
    override fun back(): Boolean {
        return svc.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
    }
}
