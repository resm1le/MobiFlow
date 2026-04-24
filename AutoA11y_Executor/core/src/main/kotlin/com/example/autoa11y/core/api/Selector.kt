package com.example.autoa11y.core.api

sealed interface Selector {
    data class ById(val id: String) : Selector

    // Match by viewIdResourceName AND node.isSelected == selected.
    data class ByIdSelected(val id: String, val selected: Boolean = true) : Selector

    data class ByText(val text: String, val contains: Boolean = false, val regex: Boolean = false) : Selector
    data class ByDesc(val desc: String, val contains: Boolean = false) : Selector

    // Match by AccessibilityNodeInfo.className (e.g. "android.widget.TextView").
    data class ByClass(val name: String, val contains: Boolean = false) : Selector

    data class AnyOf(val items: List<Selector>) : Selector

    /**
     * 坐标比例点击（0..1）。
     * - 通常由 ShellDriver 执行（A11yDriver 不支持坐标点击）。
     */
    data class CoordRatio(val x: Float, val y: Float) : Selector

    /**
     * 固定像素坐标点击（px）。
     * - 仅建议在控件无稳定 ID/Desc 且布局相对稳定时使用。
     * - 通常由 ShellDriver 执行（A11yDriver 不支持坐标点击）。
     */
    data class CoordPx(val x: Int, val y: Int) : Selector

    /**
     * 选择任意可编辑输入框（通常为 EditText）。
     * - preferBottom=true 时选择屏幕上更靠下的输入框，便于匹配聊天输入栏。
     */
    data class Editable(val preferBottom: Boolean = true) : Selector

    // ──────────────────────────────────────────────────────────────────────────
    // 关系型选择器（Phase 1 新增）
    // ──────────────────────────────────────────────────────────────────────────

    /**
     * 先用 [child] 定位叶节点，然后向上遍历父链，找第一个 isClickable=true 的祖先节点并点击。
     *
     * 解决"父容器可点击但无 ID/Desc，子节点有文字但不可点击"的常见问题。
     * [maxDepth] 防止无限向上爬误命中屏幕根容器（建议 3~5）。
     */
    data class ClickableAncestorOf(
        val child: Selector,
        val maxDepth: Int = 4
    ) : Selector

    /**
     * 在匹配 [parent] 的视图的**子树**中查找匹配 [child] 的节点并返回。
     * 适用于需要在特定容器范围内定位子节点（如 RecyclerView 中的某一行）。
     */
    data class HasDescendant(
        val parent: Selector,
        val child: Selector
    ) : Selector

    /**
     * 在匹配 [scope] 的容器内，进一步用 [target] 定位目标节点（两阶段定位）。
     * 与 HasDescendant 类似，但语义上强调「scope 是视界约束」而非「parent 是具有语义的父」。
     */
    data class Within(
        val scope: Selector,
        val target: Selector
    ) : Selector
}
