package com.example.autoa11y.core.dsl

import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.Selector
import com.example.autoa11y.core.common.PluginDefaults
import com.example.autoa11y.core.common.SearchPauses

/**
 * 复用度高的“短序列”片段：把常见的 click/input/scroll/back 组合封装成一行可读语句。
 *
 * 注意：为了不修改 engine，这些片段仍然只是在 DSL 层生成标准 Step/Action；
 * recover 的语义是“仍在同一页面时的补救步骤”，而不是感知 Action 返回值的失败回调。
 */

fun PageScope.safeInputAndSubmit(
    editSel: Selector,
    text: String,
    submitSel: Selector,
    resultMarker: Selector,
    clearFirst: Boolean = true,
    waitResultMs: Long = 6_000L,
    pauseAfterFocus: LongRange? = 500L..900L,
    pauseAfterInput: LongRange? = 1_000L..2_000L,
    pauseAfterSubmit: LongRange? = 1_000L..2_000L,
    fallbackSubmitSel: Selector? = null
) {
    attempt("safeInputAndSubmit") {
        inputAndSubmit(
            editSel = editSel,
            text = text,
            submitSel = submitSel,
            clearFirst = clearFirst,
            pauseAfterFocus = pauseAfterFocus,
            pauseAfterInput = pauseAfterInput
        )
        pauseAfterSubmit?.let { pause(it) }
        verify(resultMarker, waitResultMs)
    }.recover("safeInputAndSubmitFallback") {
        click(fallbackSubmitSel ?: submitSel)
        pauseAfterSubmit?.let { pause(it) }
        verify(resultMarker, waitResultMs)
    }
}

fun PageScope.browseAndReturn(
    marker: Selector,
    scrollRange: IntRange,
    dir: Action.Direction = Action.Direction.UP,
    scrollPause: LongRange = 1_500L..3_000L,
    extraPauseChance: Float = 0.35f,
    extraPause: LongRange = 4_500L..8_500L,
    backTargetMarker: Selector,
    backBtn: Selector
) {
    perform("browse") {
        verify(marker, 3_000L)
        scrollBlock(scrollRange, dir, pauseRange = scrollPause)
        if (chance(extraPauseChance)) {
            pause(extraPause)
        }
    }
    safeBack(
        targetPageMarker = backTargetMarker,
        backBtn = backBtn,
        pauseRange = 1_200L..1_800L,
        timeoutMs = 6_000L
    )
}

fun PageScope.searchFlow(
    name: String = "searchFlow",
    entrySel: Selector,
    editSel: Selector,
    keyword: String,
    submitSel: Selector,
    resultMarker: Selector,
    clearFirst: Boolean = true,
    waitEntryMs: Long = 5_000L,
    waitResultMs: Long = 6_000L,
    pauses: SearchPauses = PluginDefaults.SEARCH_PAUSES,
    fallbackSubmitSel: Selector? = null
) {
    attempt(name) {
        wait(entrySel, waitEntryMs)
        click(entrySel)
        pauses.beforeFocus?.let { pause(it) }
        wait(editSel, waitEntryMs)
        click(editSel)
        pauses.beforeInput?.let { pause(it) }
        if (clearFirst) {
            input(editSel, "", clear = true)
            pauses.afterClear?.let { pause(it) }
        }
        input(editSel, keyword, clear = false)
        pauses.afterInput?.let { pause(it) }
        click(submitSel)
        pauses.afterSubmit?.let { pause(it) }
        verify(resultMarker, waitResultMs)
    }.recover("${name}Fallback") {
        click(fallbackSubmitSel ?: submitSel)
        pauses.afterSubmit?.let { pause(it) }
        verify(resultMarker, waitResultMs)
    }
}

fun PageScope.openFromList(
    name: String = "openFromList",
    cardMarker: Selector,
    targetMarker: Selector,
    fallbackTap: Selector? = null,
    preScrollRange: IntRange = 0..0,
    preScrollDir: Action.Direction = Action.Direction.UP,
    preScrollPause: LongRange = 2_000L..3_500L,
    waitCardMs: Long = 4_000L,
    waitTargetMs: Long = 6_000L,
    postClickPause: LongRange = 2_000L..3_500L
) {
    attempt(name) {
        if (preScrollRange.first != 0 || preScrollRange.last != 0) {
            scrollBlock(preScrollRange, preScrollDir, pauseRange = preScrollPause)
        }
        verify(cardMarker, waitCardMs)
        click(cardMarker)
        pause(postClickPause)
        verify(targetMarker, waitTargetMs)
    }.recover("${name}Fallback") {
        click(fallbackTap ?: cardMarker)
        pause(postClickPause)
        verify(targetMarker, waitTargetMs)
    }
}

fun PageScope.browseWithScroll(
    name: String = "browseWithScroll",
    marker: Selector,
    scrollRange: IntRange,
    dir: Action.Direction = Action.Direction.UP,
    scrollPause: LongRange = 3_000L..6_000L,
    verifyMs: Long = 3_000L,
    introPause: LongRange? = null,
    firstExtraPause: LongRange? = null,
    perScrollExtraPauseChance: Float = 0f,
    perScrollExtraPause: LongRange = 4_000L..8_000L,
    downScrollChance: Float = 0f,
    downScrollDir: Action.Direction = Action.Direction.DOWN,
    downScrollPause: LongRange = 2_500L..3_800L,
    tailPause: LongRange? = null,
    tailPauseChance: Float = 0f,
    tailPauseElse: LongRange? = null
) {
    perform(name) {
        verify(marker, verifyMs)
        introPause?.let { pause(it) }
        repeatRandom(scrollRange) { index ->
            scroll(1, dir)
            pause(scrollPause)
            if (index == 0 && firstExtraPause != null) {
                pause(firstExtraPause)
            } else if (perScrollExtraPauseChance > 0f && chance(perScrollExtraPauseChance)) {
                pause(perScrollExtraPause)
            }
        }
        if (downScrollChance > 0f && chance(downScrollChance)) {
            scroll(1, downScrollDir)
            pause(downScrollPause)
        }
        val tail = when {
            tailPause != null && tailPauseChance > 0f ->
                if (chance(tailPauseChance)) tailPause else tailPauseElse
            else -> tailPause
        }
        tail?.let { pause(it) }
    }
}
