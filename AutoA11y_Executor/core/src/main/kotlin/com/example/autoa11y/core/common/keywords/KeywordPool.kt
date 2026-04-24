package com.example.autoa11y.core.common.keywords

import kotlin.random.Random

/**
 * 可复用的“随机不重复队列”：
 * - 每轮将 items 打乱后依次弹出
 * - 消耗完自动重置并再次打乱
 *
 * 用途：插件的搜索词/内容词库轮询，避免每个插件重复写 ArrayDeque(shuffled())。
 */
class KeywordPool(
    private val items: List<String>,
    private val random: Random = Random(System.currentTimeMillis())
) {
    init {
        require(items.isNotEmpty()) { "KeywordPool items must not be empty" }
    }

    private val queue: ArrayDeque<String> = ArrayDeque()

    fun remaining(): Int = queue.size

    fun next(): String {
        if (queue.isEmpty()) {
            refill()
        }
        return queue.removeFirst()
    }

    private fun refill() {
        queue.clear()
        val shuffled = items.shuffled(random)
        shuffled.forEach { queue.addLast(it) }
    }
}

