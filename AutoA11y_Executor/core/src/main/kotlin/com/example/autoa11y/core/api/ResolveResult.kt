package com.example.autoa11y.core.api

/**
 * 节点解析结果码。
 * 供 Driver 实现在执行 click/input/waitVisible 时返回结构化失败原因。
 */
enum class ResolveCode {
    /** 节点命中且操作成功。 */
    SUCCESS,

    /** 在视图树中找不到任何匹配节点。 */
    NOT_FOUND,

    /** 找到多个匹配节点，当前严格模式下不自动切候选。 */
    AMBIGUOUS,

    /** 节点找到了但不可点击（既无 isClickable 也无 ACTION_CLICK）。 */
    NOT_CLICKABLE,

    /** 节点可点击，但 ACTION_CLICK 执行失败（可能是瞬时状态问题）。 */
    ACTION_FAILED,

    /** 当前 Driver 不支持该 Selector 类型（如 A11yDriver 不支持坐标类）。 */
    UNSUPPORTED,
}

/**
 * 轻量节点摘要，仅存文本信息，避免持有 AccessibilityNodeInfo 引用（生命周期不安全）。
 */
data class NodeSummary(
    val text: String,
    val desc: String,
    val bounds: String,
    val clickable: Boolean
) {
    override fun toString(): String =
        "Node(text=$text desc=$desc bounds=$bounds clickable=$clickable)"
}

/**
 * Selector 解析结果。
 *
 * @param code      结果码
 * @param chosen    被选中的节点摘要（仅 SUCCESS 时非空）
 * @param candidates 所有候选节点摘要（用于调试 AMBIGUOUS 场景）
 * @param reason    人可读的失败说明
 */
data class ResolveResult(
    val code: ResolveCode,
    val chosen: NodeSummary? = null,
    val candidates: List<NodeSummary> = emptyList(),
    val reason: String = ""
) {
    val ok: Boolean get() = code == ResolveCode.SUCCESS

    companion object {
        fun success(node: NodeSummary) = ResolveResult(ResolveCode.SUCCESS, chosen = node)
        fun notFound(sel: Selector) = ResolveResult(ResolveCode.NOT_FOUND, reason = "no node matched: $sel")
        fun ambiguous(candidates: List<NodeSummary>, sel: Selector) =
            ResolveResult(ResolveCode.AMBIGUOUS, candidates = candidates, reason = "${candidates.size} candidates for $sel")
        fun notClickable(node: NodeSummary) =
            ResolveResult(ResolveCode.NOT_CLICKABLE, chosen = node, reason = "node found but not clickable: $node")
        fun actionFailed(node: NodeSummary, reason: String = "performAction(ACTION_CLICK) returned false") =
            ResolveResult(ResolveCode.ACTION_FAILED, chosen = node, reason = "$reason: $node")
        fun unsupported(sel: Selector) =
            ResolveResult(ResolveCode.UNSUPPORTED, reason = "selector type not supported by this driver: $sel")
    }
}

/**
 * 动作执行结果，包含 resolve 信息。
 */
data class ActionResult(
    val ok: Boolean,
    val resolve: ResolveResult? = null,
    val detail: String = ""
) {
    companion object {
        fun success(resolve: ResolveResult? = null) = ActionResult(ok = true, resolve = resolve)
        fun failure(resolve: ResolveResult, detail: String = "") =
            ActionResult(ok = false, resolve = resolve, detail = detail)
    }
}
