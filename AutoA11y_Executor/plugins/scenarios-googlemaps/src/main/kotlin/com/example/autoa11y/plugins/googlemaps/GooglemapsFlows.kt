package com.example.autoa11y.plugins.googlemaps

import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.common.DeviceKeyboard
import com.example.autoa11y.core.dsl.flow
import com.example.autoa11y.core.dsl.robustSystemBackTo
import kotlin.random.Random

internal object GooglemapsFlows {

    fun startup(): Scenario = flow("maps_startup") {
        anyPage { pause(4_000L, 6_000L) }
    }

    fun searchAndRoute(destination: String, isUnique: Boolean): Scenario {
        val flowId = "maps_search_${destination.take(10).replace(' ', '_')}_${Random.nextInt(10_000)}"
        return flow(flowId) {
            on(GooglemapsPages.home) {
                perform("open_search") {
                    navigate(
                        trigger = GooglemapsSelectors.Home.searchBar,
                        expectedPageId = GooglemapsPages.SEARCH_ID,
                        sourcePageId = GooglemapsPages.HOME_ID,
                        timeoutMs = 8_000L,
                        settleDelayMs = 900L,
                        maxAttempts = 3,
                        restartReason = "maps home->search failed"
                    )
                    pause(1_000L, 1_600L)
                }
            }
            on(GooglemapsPages.search) {
                perform("search_input_text") {
                    input(GooglemapsSelectors.Search.inputBox, destination, clear = true)
                    pause(1_200L, 2_000L)
                }
                perform("search_submit") {
                    navigate(
                        trigger = DeviceKeyboard.enterKey,
                        expectedPageId = if (isUnique) GooglemapsPages.DETAIL_ID else GooglemapsPages.RESULTS_ID,
                        sourcePageId = GooglemapsPages.SEARCH_ID,
                        timeoutMs = 8_000L,
                        settleDelayMs = 1_000L,
                        maxAttempts = 3,
                        restartReason = "maps submit search failed dest=$destination"
                    )
                }
            }
            if (isUnique) {
                on(GooglemapsPages.detail) {
                    perform("detail_interact") {
                        pause(4_000L, 7_000L)
                        swipe(fromX = 0.5f, fromY = 0.75f, toX = 0.5f, toY = 0.45f, durationMs = 400)
                        pause(3_000L, 5_000L)
                    }
                    perform("close_detail_to_home") {
                        navigate(
                            trigger = GooglemapsSelectors.PlaceDetail.dismissButton,
                            expectedPageId = GooglemapsPages.HOME_ID,
                            sourcePageId = GooglemapsPages.DETAIL_ID,
                            timeoutMs = 8_000L,
                            settleDelayMs = 900L,
                            maxAttempts = 3,
                            restartReason = "close detail to home failed"
                        )
                    }
                }
            } else {
                on(GooglemapsPages.results) {
                    perform("results_interact") {
                        pause(3_000L, 5_000L)
                        swipe(fromX = 0.5f, fromY = 0.75f, toX = 0.5f, toY = 0.50f, durationMs = 400)
                        pause(2_000L, 4_000L)
                    }
                    perform("open_detail") {
                        navigate(
                            trigger = GooglemapsSelectors.Results.resultCard,
                            expectedPageId = GooglemapsPages.DETAIL_ID,
                            sourcePageId = GooglemapsPages.RESULTS_ID,
                            timeoutMs = 8_000L,
                            settleDelayMs = 1_000L,
                            maxAttempts = 3,
                            restartReason = "open search result detail failed"
                        )
                    }
                }
                on(GooglemapsPages.detail) {
                    perform("detail_interact") {
                        pause(4_000L, 7_000L)
                        swipe(fromX = 0.5f, fromY = 0.75f, toX = 0.5f, toY = 0.45f, durationMs = 400)
                        pause(3_000L, 5_000L)
                    }
                    perform("close_detail") {
                        navigate(
                            trigger = GooglemapsSelectors.PlaceDetail.dismissButton,
                            expectedPageId = GooglemapsPages.RESULTS_ID,
                            sourcePageId = GooglemapsPages.DETAIL_ID,
                            timeoutMs = 8_000L,
                            settleDelayMs = 900L,
                            maxAttempts = 3,
                            restartReason = "close detail failed"
                        )
                    }
                }
                on(GooglemapsPages.results) {
                    perform("close_results") {
                        navigate(
                            trigger = GooglemapsSelectors.Results.closeButton,
                            expectedPageId = GooglemapsPages.HOME_ID,
                            sourcePageId = GooglemapsPages.RESULTS_ID,
                            timeoutMs = 8_000L,
                            settleDelayMs = 900L,
                            maxAttempts = 3,
                            restartReason = "close results failed"
                        )
                    }
                }
            }
        }
    }

    fun browseNearby(category: String): Scenario {
        val flowId = "maps_browse_${category.take(5)}_${Random.nextInt(10_000)}"
        return flow(flowId) {
            on(GooglemapsPages.home) {
                perform("browse_drag_map") {
                    swipe(
                        fromX = 0.3f + Random.nextFloat() * 0.4f,
                        fromY = 0.4f + Random.nextFloat() * 0.2f,
                        toX = 0.2f + Random.nextFloat() * 0.6f,
                        toY = 0.3f + Random.nextFloat() * 0.3f,
                        durationMs = 600
                    )
                    pause(2_000L, 4_000L)

                    if (chance(0.5f)) {
                        swipe(
                            fromX = 0.3f + Random.nextFloat() * 0.4f,
                            fromY = 0.5f + Random.nextFloat() * 0.2f,
                            toX = 0.2f + Random.nextFloat() * 0.6f,
                            toY = 0.3f + Random.nextFloat() * 0.3f,
                            durationMs = 500
                        )
                        pause(2_000L, 3_000L)
                    }
                }
                perform("browse_search_category") {
                    navigate(
                        trigger = GooglemapsSelectors.Home.searchBar,
                        expectedPageId = GooglemapsPages.SEARCH_ID,
                        sourcePageId = GooglemapsPages.HOME_ID,
                        timeoutMs = 8_000L,
                        settleDelayMs = 900L,
                        maxAttempts = 3,
                        restartReason = "maps browse home->search failed"
                    )
                    pause(1_000L, 1_600L)
                }
            }
            on(GooglemapsPages.search) {
                perform("browse_input_category") {
                    input(GooglemapsSelectors.Search.inputBox, category, clear = true)
                    pause(1_200L, 2_000L)
                }
                perform("browse_submit_category") {
                    navigate(
                        trigger = DeviceKeyboard.enterKey,
                        expectedPageId = GooglemapsPages.RESULTS_ID,
                        sourcePageId = GooglemapsPages.SEARCH_ID,
                        timeoutMs = 8_000L,
                        settleDelayMs = 1_000L,
                        maxAttempts = 3,
                        restartReason = "submit category search failed"
                    )
                }
            }
            on(GooglemapsPages.results) {
                perform("browse_results_interact") {
                    pause(3_000L, 5_000L)
                    swipe(fromX = 0.5f, fromY = 0.80f, toX = 0.5f, toY = 0.50f, durationMs = 400)
                    pause(2_000L, 4_000L)
                    swipe(fromX = 0.5f, fromY = 0.80f, toX = 0.5f, toY = 0.55f, durationMs = 400)
                    pause(2_000L, 3_000L)
                }
                perform("open_category_detail") {
                    navigate(
                        trigger = GooglemapsSelectors.Results.resultCard,
                        expectedPageId = GooglemapsPages.DETAIL_ID,
                        sourcePageId = GooglemapsPages.RESULTS_ID,
                        timeoutMs = 8_000L,
                        settleDelayMs = 1_000L,
                        maxAttempts = 3,
                        restartReason = "open explore result detail failed"
                    )
                }
            }
            on(GooglemapsPages.detail) {
                perform("category_detail_interact") {
                    pause(5_000L, 8_000L)
                    swipe(fromX = 0.5f, fromY = 0.8f, toX = 0.5f, toY = 0.3f, durationMs = 500)
                    pause(3_000L, 5_000L)
                }
                perform("close_category_detail") {
                    navigate(
                        trigger = GooglemapsSelectors.PlaceDetail.dismissButton,
                        expectedPageId = GooglemapsPages.RESULTS_ID,
                        sourcePageId = GooglemapsPages.DETAIL_ID,
                        timeoutMs = 8_000L,
                        settleDelayMs = 900L,
                        maxAttempts = 3,
                        restartReason = "close explore detail failed"
                    )
                }
            }
            on(GooglemapsPages.results) {
                perform("close_category_results") {
                    navigate(
                        trigger = GooglemapsSelectors.Results.closeButton,
                        expectedPageId = GooglemapsPages.HOME_ID,
                        sourcePageId = GooglemapsPages.RESULTS_ID,
                        timeoutMs = 8_000L,
                        settleDelayMs = 900L,
                        maxAttempts = 3,
                        restartReason = "close explore results failed"
                    )
                }
            }
        }
    }

    fun recoveryFlow(reason: String): Scenario =
        flow("maps_recovery_${kotlin.math.abs(reason.hashCode())}") {
            anyPage {
                backForce()
                pause(1_500L, 2_500L)
                backForce()
                pause(1_500L, 2_500L)
            }
        }
}
