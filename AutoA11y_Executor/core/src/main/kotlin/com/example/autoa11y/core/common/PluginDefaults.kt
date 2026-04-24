package com.example.autoa11y.core.common

/**
 * 统一的时序/随机约定，便于各插件复用而不必硬编码常量。
 */
object PluginDefaults {
    // 常用等待/停顿
    const val WAIT_SHORT_MS: Long = 2_000L
    const val WAIT_MEDIUM_MS: Long = 5_000L
    const val WAIT_LONG_MS: Long = 8_000L

    // 滚动/返回的默认停顿区间
    val SCROLL_PAUSE_MS: LongRange = 1_500L..3_000L
    val BACKOFF_PAUSE_MS: LongRange = 1_000L..2_000L

    // 搜索流程的标准时间片
    val SEARCH_PAUSES: SearchPauses = SearchPauses(
        beforeFocus = 500L..900L,
        beforeInput = 500L..900L,
        afterClear = 500L..900L,
        afterInput = 1_000L..2_000L,
        afterSubmit = 1_000L..2_000L
    )
}
