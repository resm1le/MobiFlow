package com.example.autoa11y.plugins.shein

import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.Selector
import com.example.autoa11y.core.dsl.ActionScope
import com.example.autoa11y.core.dsl.PageScope
import com.example.autoa11y.core.dsl.flow
import com.example.autoa11y.core.dsl.robustSystemBackTo
import kotlin.math.abs
import kotlin.random.Random

internal object SheinFlows {

    enum class SuggestionSource {
        RECENT,
        DISCOVERY,
        TRENDING
    }

    fun startup(): Scenario = flow("shein_startup") {
        anyPage { coldStartPause() }
    }

    fun homeDiscovery(): Scenario {
        val random = Random(System.currentTimeMillis())
        val preferredTab = if (random.nextFloat() < 0.55f) {
            SheinData.homeTabs.random(random)
        } else {
            null
        }
        val homeFallbackTap = listOf(
            Selector.CoordRatio(0.72f, 0.69f),
            Selector.CoordRatio(0.50f, 0.80f),
            Selector.CoordRatio(0.31f, 0.69f)
        ).random(random)

        return flow("shein_home_${random.nextInt(10_000)}") {
            on(SheinPages.searchResults) { exitResultsToHome("normalize_results") }
            on(SheinPages.searchHome) { exitSearchToHome("normalize_search") }
            on(SheinPages.detail) { normalizeDetailToHome("normalize_detail") }

            on(SheinPages.home) {
                perform("home_browse") {
                    homeBrowsePattern(preferredTab)
                }

                perform("home_open_product") {
                    navigate(
                        trigger = SheinSelectors.Home.productCard,
                        expectedPageId = SheinPages.DETAIL_ID,
                        sourcePageId = SheinPages.HOME_ID,
                        fallbackTrigger = homeFallbackTap,
                        maxAttempts = 3,
                        timeoutMs = 9_500L,
                        settleDelayMs = 450L,
                        unknownBackMax = 2,
                        restartReason = "home open product failed"
                    )
                    postNavigatePause()
                }
            }

            on(SheinPages.detail) {
                perform("detail_from_home") {
                    detailBrowsePattern()
                    maybeFavorite()
                }

                robustSystemBackTo(
                    name = "detail_back_home",
                    targetMarker = SheinSelectors.Home.visualSearch,
                    maxAttempts = 3,
                    pauseRange = 1_900L..3_600L,
                    timeoutMs = 9_000L,
                    restartReason = "detail back to home failed"
                )
            }
        }
    }

    fun keywordSearch(keyword: String, allowRefine: Boolean): Scenario {
        val random = Random(System.currentTimeMillis())
        val resultFallbackTap = SheinSelectors.Results.fallbackProductCandidates.random(random)
        val productCount = random.nextInt(3, 9)
        val flowId = "shein_keyword_${keyword.replace(' ', '_').take(18)}_${random.nextInt(10_000)}"

        return flow(flowId) {
            on(SheinPages.searchResults) { exitResultsToSearch("normalize_results") }
            on(SheinPages.detail) { detailToSearchHome("normalize_detail") }
            on(SheinPages.home) { openSearchFromHome("from_home") }

            on(SheinPages.searchHome) {
                perform("input_keyword") {
                    pause(1_400L, 2_800L)
                    click(SheinSelectors.SearchHome.input)
                    settleInputFocus()
                    input(SheinSelectors.SearchHome.input, keyword, clear = true)
                    typedInputPause()
                }

                perform("submit_keyword") {
                    preSearchSubmitPause()
                    navigate(
                        trigger = SheinSelectors.SearchHome.searchButton,
                        expectedPageId = SheinPages.RESULTS_ID,
                        sourcePageId = SheinPages.SEARCH_ID,
                        maxAttempts = 3,
                        timeoutMs = 8_500L,
                        settleDelayMs = 350L,
                        unknownBackMax = 2,
                        restartReason = "submit keyword failed keyword=$keyword"
                    )
                    postNavigatePause()
                }
            }

            repeat(productCount) { index ->
                val browseTag = index + 1

                on(SheinPages.searchResults) {
                    perform("results_browse_$browseTag") {
                        resultsBrowsePattern(
                            allowRefine = allowRefine && index == 0,
                            intensity = if (index == 0) BrowseIntensity.DEEP else BrowseIntensity.LIGHT
                        )
                    }

                    perform("open_result_product_$browseTag") {
                        navigate(
                            trigger = SheinSelectors.Results.productCard,
                            expectedPageId = SheinPages.DETAIL_ID,
                            sourcePageId = SheinPages.RESULTS_ID,
                            fallbackTrigger = resultFallbackTap,
                            maxAttempts = 3,
                            timeoutMs = 9_000L,
                            settleDelayMs = 450L,
                            unknownBackMax = 2,
                            restartReason = "open result product failed keyword=$keyword visit=$browseTag"
                        )
                        postNavigatePause()
                    }
                }

                on(SheinPages.detail) {
                    perform("detail_from_results_$browseTag") {
                        detailBrowsePattern()
                        maybeFavorite()
                    }

                    robustSystemBackTo(
                        name = "detail_back_results_$browseTag",
                        targetMarker = SheinSelectors.Results.changeView,
                        maxAttempts = 3,
                        pauseRange = 1_900L..3_600L,
                        timeoutMs = 9_000L,
                        restartReason = "detail back to results failed keyword=$keyword visit=$browseTag"
                    )
                }
            }
        }
    }

    fun suggestionSearch(source: SuggestionSource): Scenario {
        val random = Random(System.currentTimeMillis())
        val sourceTap = pickSuggestionTap(source, random)
        val resultFallbackTap = SheinSelectors.Results.fallbackProductCandidates.random(random)
        val productCount = random.nextInt(3, 9)
        val flowId = "shein_${source.name.lowercase()}_${random.nextInt(10_000)}"

        return flow(flowId) {
            on(SheinPages.searchResults) { exitResultsToSearch("normalize_results") }
            on(SheinPages.detail) { detailToSearchHome("normalize_detail") }
            on(SheinPages.home) { openSearchFromHome("from_home") }

            on(SheinPages.searchHome) {
                perform("tap_${source.name.lowercase()}_entry") {
                    pause(1_000L, 2_000L)
                    navigate(
                        trigger = sourceTap,
                        expectedPageId = SheinPages.RESULTS_ID,
                        sourcePageId = SheinPages.SEARCH_ID,
                        maxAttempts = 2,
                        timeoutMs = 8_000L,
                        settleDelayMs = 350L,
                        unknownBackMax = 2,
                        restartReason = "tap search suggestion failed source=$source"
                    )
                    postNavigatePause()
                }
            }

            repeat(productCount) { index ->
                val browseTag = index + 1

                on(SheinPages.searchResults) {
                    perform("results_browse_${source.name.lowercase()}_$browseTag") {
                        resultsBrowsePattern(
                            allowRefine = index == 0,
                            intensity = if (index == 0) BrowseIntensity.DEEP else BrowseIntensity.LIGHT
                        )
                    }

                    perform("open_result_product_${source.name.lowercase()}_$browseTag") {
                        navigate(
                            trigger = SheinSelectors.Results.productCard,
                            expectedPageId = SheinPages.DETAIL_ID,
                            sourcePageId = SheinPages.RESULTS_ID,
                            fallbackTrigger = resultFallbackTap,
                            maxAttempts = 3,
                            timeoutMs = 9_000L,
                            settleDelayMs = 450L,
                            unknownBackMax = 2,
                            restartReason = "open result product failed source=$source visit=$browseTag"
                        )
                        postNavigatePause()
                    }
                }

                on(SheinPages.detail) {
                    perform("detail_from_${source.name.lowercase()}_$browseTag") {
                        detailBrowsePattern()
                        maybeFavorite()
                    }

                    robustSystemBackTo(
                        name = "detail_back_results_${source.name.lowercase()}_$browseTag",
                        targetMarker = SheinSelectors.Results.changeView,
                        maxAttempts = 3,
                        pauseRange = 1_900L..3_600L,
                        timeoutMs = 9_000L,
                        restartReason = "detail back to results failed source=$source visit=$browseTag"
                    )
                }
            }
        }
    }

    fun recoveryFlow(reason: String): Scenario =
        flow("shein_recovery_${abs(reason.hashCode())}") {
            anyPage {
                backForce()
                pause(2_400L, 4_400L)
                backForce()
                pause(2_400L, 4_400L)
            }
        }

    private fun pickSuggestionTap(source: SuggestionSource, random: Random): Selector =
        when (source) {
            SuggestionSource.RECENT -> listOf(
                SheinSelectors.SearchHome.recentTapPrimary,
                SheinSelectors.SearchHome.recentTapSecondary
            ).random(random)

            SuggestionSource.DISCOVERY -> listOf(
                SheinSelectors.SearchHome.discoveryTapPrimary,
                SheinSelectors.SearchHome.discoveryTapSecondary,
                SheinSelectors.SearchHome.discoveryTapTertiary
            ).random(random)

            SuggestionSource.TRENDING -> listOf(
                SheinSelectors.SearchHome.trendingTapPrimary,
                SheinSelectors.SearchHome.trendingTapSecondary
            ).random(random)
        }
}

private fun PageScope.openSearchFromHome(tag: String) {
    perform("open_search_$tag") {
        pause(800L, 1_500L)
        navigate(
            trigger = SheinSelectors.Home.searchEntry,
            expectedPageId = SheinPages.SEARCH_ID,
            sourcePageId = SheinPages.HOME_ID,
            maxAttempts = 2,
            timeoutMs = 7_500L,
            settleDelayMs = 350L,
            restartReason = "open search failed tag=$tag"
        )
        searchLandingPause()
    }
}

private fun PageScope.exitSearchToHome(tag: String) {
    robustSystemBackTo(
        name = "search_to_home_$tag",
        targetMarker = SheinSelectors.Home.visualSearch,
        maxAttempts = 2,
        pauseRange = 1_700L..3_100L,
        timeoutMs = 8_000L,
        restartReason = "search to home failed tag=$tag"
    )
}

private fun PageScope.exitResultsToHome(tag: String) {
    robustSystemBackTo(
        name = "results_to_search_$tag",
        targetMarker = SheinSelectors.SearchHome.input,
        maxAttempts = 2,
        pauseRange = 1_700L..3_100L,
        timeoutMs = 8_000L,
        restartReason = "results to search failed tag=$tag"
    )
    robustSystemBackTo(
        name = "search_to_home_$tag",
        targetMarker = SheinSelectors.Home.visualSearch,
        maxAttempts = 2,
        pauseRange = 1_700L..3_100L,
        timeoutMs = 8_000L,
        restartReason = "search to home failed tag=$tag"
    )
}

private fun PageScope.normalizeDetailToHome(tag: String) {
    detailToSearchHome(tag)
    exitSearchToHome("${tag}_final")
}

private fun PageScope.exitResultsToSearch(tag: String) {
    robustSystemBackTo(
        name = "results_to_search_$tag",
        targetMarker = SheinSelectors.SearchHome.input,
        maxAttempts = 2,
        pauseRange = 1_700L..3_100L,
        timeoutMs = 8_000L,
        restartReason = "results to search failed tag=$tag"
    )
}

private fun PageScope.detailToSearchHome(tag: String) {
    perform("detail_to_search_$tag") {
        navigate(
            trigger = SheinSelectors.Detail.topSearch,
            expectedPageId = SheinPages.SEARCH_ID,
            sourcePageId = SheinPages.DETAIL_ID,
            maxAttempts = 2,
            timeoutMs = 7_500L,
            settleDelayMs = 350L,
            restartReason = "detail to search failed tag=$tag"
        )
        postNavigatePause()
    }
}

private fun ActionScope.coldStartPause() {
    pause(4_800L, 7_800L)
    if (chance(0.30f)) {
        pause(1_200L, 2_400L)
    }
}

private fun ActionScope.postNavigatePause() {
    pause(2_100L, 4_200L)
    if (chance(0.35f)) {
        pause(900L, 1_900L)
    }
}

private fun ActionScope.searchLandingPause() {
    pause(1_300L, 2_450L)
    if (chance(0.45f)) {
        pause(550L, 1_050L)
    }
}

private fun ActionScope.settleInputFocus() {
    pause(900L, 1_650L)
    if (chance(0.35f)) {
        pause(450L, 800L)
    }
}

private fun ActionScope.typedInputPause() {
    pause(1_700L, 3_050L)
    if (chance(0.55f)) {
        pause(550L, 1_100L)
    }
}

private fun ActionScope.preSearchSubmitPause() {
    pause(750L, 1_600L)
    if (chance(0.35f)) {
        pause(400L, 800L)
    }
}

private fun ActionScope.homeBrowsePattern(preferredTab: String?) {
    pause(3_800L, 6_400L)
    preferredTab?.let {
        click(Selector.ByText(it))
        pause(1_400L, 2_900L)
    }
    repeatRandom(2..4) {
        scroll(1, Action.Direction.UP)
        pause(2_100L, 4_600L)
        if (chance(0.15f)) {
            scroll(1, Action.Direction.DOWN)
            pause(1_500L, 3_100L)
        } else if (chance(0.35f)) {
            scroll(1, Action.Direction.UP)
            pause(1_400L, 2_800L)
        }
    }
    if (chance(0.30f)) {
        pause(1_600L, 3_200L)
    }
}

private fun ActionScope.resultsBrowsePattern(allowRefine: Boolean) {
    resultsBrowsePattern(allowRefine = allowRefine, intensity = BrowseIntensity.DEEP)
}

private enum class BrowseIntensity {
    LIGHT,
    DEEP
}

private fun ActionScope.resultsBrowsePattern(allowRefine: Boolean, intensity: BrowseIntensity) {
    pause(2_800L, 5_000L)
    if (allowRefine && chance(0.35f)) {
        click(SheinSelectors.Results.relatedTapCandidates.random())
        pause(2_100L, 4_300L)
    }
    val upRange = when (intensity) {
        BrowseIntensity.LIGHT -> 1..2
        BrowseIntensity.DEEP -> 2..4
    }
    repeatRandom(upRange) {
        scroll(1, Action.Direction.UP)
        pause(2_200L, 4_800L)
        if (chance(0.16f)) {
            scroll(1, Action.Direction.DOWN)
            pause(1_500L, 3_100L)
        } else if (chance(0.32f)) {
            scroll(1, Action.Direction.UP)
            pause(1_400L, 2_900L)
        }
    }
    if (chance(0.30f)) {
        pause(1_200L, 2_600L)
    }
}

private fun ActionScope.detailBrowsePattern() {
    pause(4_800L, 8_600L)
    repeatRandom(3..8) { index ->
        swipe(fromX = 0.5f, fromY = 0.80f, toX = 0.5f, toY = 0.48f, durationMs = 420)
        pause(2_300L, 4_600L)
        if (chance(0.30f)) {
            swipe(fromX = 0.5f, fromY = 0.78f, toX = 0.5f, toY = 0.44f, durationMs = 430)
            pause(1_500L, 3_100L)
        }
        if (index > 0 && chance(0.18f)) {
            swipe(fromX = 0.5f, fromY = 0.48f, toX = 0.5f, toY = 0.72f, durationMs = 360)
            pause(1_600L, 3_300L)
        }
    }
    if (chance(0.45f)) {
        pause(1_600L, 3_100L)
    }
}

private fun ActionScope.maybeFavorite() {
    if (!chance(0.20f)) return
    pause(1_200L, 2_200L)
    click(SheinSelectors.Detail.save)
    pause(1_800L, 3_400L)
}
