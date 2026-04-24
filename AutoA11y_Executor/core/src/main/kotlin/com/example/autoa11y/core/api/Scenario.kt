package com.example.autoa11y.core.api
data class Step(val require: Condition? = null, val actions: List<Action>)
data class Scenario(val id: String, val steps: List<Step>)
data class PageSignature(
    val pkg: String,
    val must: List<Selector> = emptyList(),
    /** 至少命中其中一个 Selector，才认为处于此页面（可为空，表示不约束）。 */
    val oneOf: List<Selector> = emptyList(),
    /** 这些 Selector 全部不命中，才认为处于此页面（用于排除"看起来相似"的错误页面）。 */
    val mustNot: List<Selector> = emptyList()
)
sealed interface Condition {
    data class OnPage(val sig: PageSignature) : Condition
    data class And(val items: List<Condition>) : Condition
    data class Not(val item: Condition) : Condition
}
