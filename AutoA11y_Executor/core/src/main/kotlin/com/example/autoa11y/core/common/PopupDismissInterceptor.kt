package com.example.autoa11y.core.common

import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.core.api.Interceptor
import com.example.autoa11y.core.api.Selector

/**
 * Generic popup dismiss interceptor: clicks common positive/confirm buttons in multiple rounds.
 * @param enabled whether the interceptor is active; default false.
 */
class PopupDismissInterceptor(
    keywords: List<String> = DEFAULT_KEYWORDS,
    private val rounds: Int = 2,
    private val pauseMs: Long = 200,
    private val enabled: Boolean = false
) : Interceptor {

    private val anyOf = Selector.AnyOf(
        keywords.map { it.trim() }
            .filter { it.isNotEmpty() }
            .distinct()
            .flatMap { k ->
                listOf(Selector.ByText(k, contains = true), Selector.ByDesc(k, contains = true))
            }
    )

    override fun tryIntercept(driver: Driver): Boolean {
        // If not enabled, do nothing.
        if (!enabled) return false

        var acted = false
        repeat(rounds) {
            val ok = driver.click(anyOf)
            if (!ok) return acted
            acted = true
            Thread.sleep(pauseMs)
        }
        return acted
    }

    companion object {
        val DEFAULT_KEYWORDS = listOf(
            // English
            "accept",
            "accept all",
            "agree",
            "i agree",
            "allow",
            "allow all",
            "ok",
            "okay",
            "got it",
            "continue",
            "yes",
            "close",
            "dismiss",
            "later",
            "not now",
            "skip",
            "no thanks",
            // Chinese
            "允许",
            "同意",
            "我知道了",
            "以后再说",
            "好的",
            "确定",
            "继续",
            "接受",
            "关闭",
            "稍后",
            "不再提示"
        )
    }
}
