package com.example.autoa11y.plugins.googlemaps

import com.example.autoa11y.core.api.KnownPage
import com.example.autoa11y.core.api.PageSignature

internal object GooglemapsPages {
    const val HOME_ID = "home"
    const val SEARCH_ID = "search"
    const val RESULTS_ID = "results"
    const val DETAIL_ID = "detail"

    val home: PageSignature = PageSignature(
        TARGET_PKG,
        must = listOf(
            GooglemapsSelectors.Anchors.searchBar,
            GooglemapsSelectors.Anchors.exploreTab
        ),
        mustNot = listOf(
            GooglemapsSelectors.Search.inputBox,
            GooglemapsSelectors.Results.closeButton,
            GooglemapsSelectors.PlaceDetail.anchor
        )
    )

    val search: PageSignature = PageSignature(
        TARGET_PKG,
        must = listOf(
            GooglemapsSelectors.Search.inputBox,
            GooglemapsSelectors.Search.backNav
        ),
        mustNot = listOf(
            GooglemapsSelectors.PlaceDetail.anchor
        )
    )

    val results: PageSignature = PageSignature(
        TARGET_PKG,
        must = listOf(
            GooglemapsSelectors.Results.closeButton,
            GooglemapsSelectors.Results.listContainer
        ),
        oneOf = listOf(
            GooglemapsSelectors.Results.resultCardTitle
        ),
        mustNot = emptyList()
    )

    val detail: PageSignature = PageSignature(
        TARGET_PKG,
        must = listOf(
            GooglemapsSelectors.PlaceDetail.anchor
        ),
        oneOf = listOf(
            GooglemapsSelectors.PlaceDetail.routeButton,
            GooglemapsSelectors.PlaceDetail.startNavButton
        ),
        mustNot = listOf(
            GooglemapsSelectors.Search.inputBox
        )
    )

    val knownPages: List<KnownPage> = listOf(
        KnownPage(HOME_ID, home),
        KnownPage(SEARCH_ID, search),
        KnownPage(RESULTS_ID, results),
        KnownPage(DETAIL_ID, detail)
    )
}
