package com.example.autoa11y.core.dsl

import com.example.autoa11y.core.api.Selector

fun PageScope.safeBack(
    targetPageMarker: Selector,
    backBtn: Selector,
    pauseRange: LongRange = 1_200L..1_800L,
    timeoutMs: Long = 6_000L
) {
    attempt("safeBack") {
        click(backBtn)
        pause(pauseRange)
        verify(targetPageMarker, timeoutMs)
    }.recover("safeBackFallback") {
        backForce()
        pause(pauseRange)
        verify(targetPageMarker, timeoutMs)
    }
}

fun PageScope.safeClick(
    trigger: Selector,
    target: Selector,
    fallbackTrigger: Selector? = null,
    pauseRange: LongRange = 1_200L..2_000L,
    timeoutMs: Long = 6_000L
) {
    val settleDelayMs = pauseRange.first.coerceAtLeast(0L)
    attempt("safeClick") {
        smartClick(
            trigger = trigger,
            expectedMarker = target,
            timeoutMs = timeoutMs,
            settleDelayMs = settleDelayMs
        )
    }.recover("safeClickFallback") {
        smartClick(
            trigger = fallbackTrigger ?: trigger,
            expectedMarker = target,
            timeoutMs = timeoutMs,
            settleDelayMs = settleDelayMs
        )
    }
}

fun PageScope.forceBackTo(
    targetPageMarker: Selector,
    pauseRange: LongRange = 1_200L..1_800L,
    timeoutMs: Long = 6_000L
) {
    attempt("forceBack") {
        backForce()
        pause(pauseRange)
        verify(targetPageMarker, timeoutMs)
    }.recover("forceBackFallback") {
        backForce()
        pause(pauseRange)
        verify(targetPageMarker, timeoutMs)
    }
}

fun PageScope.robustClickTo(
    name: String = "robustClick",
    trigger: Selector,
    targetMarker: Selector,
    maxAttempts: Int = 3,
    pauseRange: LongRange = 1_200L..2_000L,
    timeoutMs: Long = 6_000L,
    fallbackTrigger: Selector? = null,
    restartReason: String? = null
) {
    val attempts = maxAttempts.coerceAtLeast(1)
    val settleDelayMs = pauseRange.first.coerceAtLeast(0L)
    val retryRequire = requireOnPageAndNotTarget(targetMarker)
    val handle = attempt("${name}_try1") {
        smartClick(
            trigger = trigger,
            expectedMarker = targetMarker,
            timeoutMs = timeoutMs,
            settleDelayMs = settleDelayMs
        )
    }
    for (i in 2..attempts) {
        handle.recover(require = retryRequire, name = "${name}_try$i") {
            smartClick(
                trigger = fallbackTrigger ?: trigger,
                expectedMarker = targetMarker,
                timeoutMs = timeoutMs,
                settleDelayMs = settleDelayMs
            )
        }
    }
    val reason = restartReason ?: "robustClickTo recovery name=$name attempts=$attempts target=$targetMarker"
    handle.recover(require = retryRequire, name = "${name}_circuit") {
        requestRestart(reason)
    }
}

fun PageScope.robustBackTo(
    name: String = "robustBack",
    backBtn: Selector,
    targetMarker: Selector,
    maxAttempts: Int = 3,
    pauseRange: LongRange = 1_200L..1_800L,
    timeoutMs: Long = 6_000L,
    forceOnRetry: Boolean = true,
    restartReason: String? = null
) {
    val attempts = maxAttempts.coerceAtLeast(1)
    val retryRequire = requireOnPageAndNotTarget(targetMarker)
    val handle = attempt("${name}_try1") {
        click(backBtn)
        pause(pauseRange)
        verify(targetMarker, timeoutMs)
    }
    for (i in 2..attempts) {
        handle.recover(require = retryRequire, name = "${name}_try$i") {
            if (forceOnRetry) {
                backForce()
            } else {
                click(backBtn)
            }
            pause(pauseRange)
            verify(targetMarker, timeoutMs)
        }
    }
    val reason = restartReason ?: "robustBackTo recovery name=$name attempts=$attempts target=$targetMarker"
    handle.recover(require = retryRequire, name = "${name}_circuit") {
        requestRestart(reason)
    }
}

fun PageScope.robustSystemBackTo(
    name: String = "robustSystemBack",
    targetMarker: Selector,
    maxAttempts: Int = 3,
    pauseRange: LongRange = 1_200L..1_800L,
    timeoutMs: Long = 6_000L,
    restartReason: String? = null
) {
    val attempts = maxAttempts.coerceAtLeast(1)
    val retryRequire = requireOnPageAndNotTarget(targetMarker)
    val handle = attempt("${name}_try1") {
        backForce()
        pause(pauseRange)
        verify(targetMarker, timeoutMs)
    }
    for (i in 2..attempts) {
        handle.recover(require = retryRequire, name = "${name}_try$i") {
            backForce()
            pause(pauseRange)
            verify(targetMarker, timeoutMs)
        }
    }
    val reason = restartReason ?: "robustSystemBackTo recovery name=$name attempts=$attempts target=$targetMarker"
    handle.recover(require = retryRequire, name = "${name}_circuit") {
        requestRestart(reason)
    }
}
