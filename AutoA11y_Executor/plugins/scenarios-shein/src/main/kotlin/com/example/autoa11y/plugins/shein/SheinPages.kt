package com.example.autoa11y.plugins.shein

import com.example.autoa11y.core.api.KnownPage
import com.example.autoa11y.core.api.PageSignature

internal object SheinPages {
    const val HOME_ID = "home_shop"
    const val SEARCH_ID = "search_home"
    const val RESULTS_ID = "search_results"
    const val DETAIL_ID = "product_detail"

    val home: PageSignature = PageSignature(
        pkg = TARGET_PKG,
        must = listOf(
            SheinSelectors.Home.visualSearch,
            SheinSelectors.Home.wishlist,
            SheinSelectors.Home.shopTab
        ),
        oneOf = listOf(
            SheinSelectors.Home.categoryTab,
            SheinSelectors.Home.feed
        ),
        mustNot = listOf(
            SheinSelectors.SearchHome.back,
            SheinSelectors.Results.changeView,
            SheinSelectors.Detail.shoppingCart
        )
    )

    val searchHome: PageSignature = PageSignature(
        pkg = TARGET_PKG,
        must = listOf(
            SheinSelectors.SearchHome.back,
            SheinSelectors.SearchHome.input,
            SheinSelectors.SearchHome.searchButton
        ),
        oneOf = listOf(
            SheinSelectors.SearchHome.recentHeader,
            SheinSelectors.SearchHome.discoveryHeader,
            SheinSelectors.SearchHome.trendingHeader
        ),
        mustNot = listOf(
            SheinSelectors.Results.changeView,
            SheinSelectors.Detail.shoppingCart
        )
    )

    val searchResults: PageSignature = PageSignature(
        pkg = TARGET_PKG,
        must = listOf(
            SheinSelectors.Results.back,
            SheinSelectors.Results.changeView,
            SheinSelectors.Results.wishlist
        ),
        oneOf = listOf(
            SheinSelectors.Results.priceLayout,
            SheinSelectors.Results.title,
            SheinSelectors.Results.goToCart
        ),
        mustNot = listOf(
            SheinSelectors.SearchHome.input,
            SheinSelectors.Detail.shoppingCart
        )
    )

    val detail: PageSignature = PageSignature(
        pkg = TARGET_PKG,
        must = listOf(
            SheinSelectors.Detail.topSearch,
            SheinSelectors.Detail.shoppingCart
        ),
        oneOf = listOf(
            SheinSelectors.Detail.share,
            SheinSelectors.Detail.more
        ),
        mustNot = listOf(
            SheinSelectors.Results.changeView,
            SheinSelectors.SearchHome.input
        )
    )

    val allKnownPages: List<KnownPage> = listOf(
        KnownPage(HOME_ID, home),
        KnownPage(SEARCH_ID, searchHome),
        KnownPage(RESULTS_ID, searchResults),
        KnownPage(DETAIL_ID, detail)
    )
}
