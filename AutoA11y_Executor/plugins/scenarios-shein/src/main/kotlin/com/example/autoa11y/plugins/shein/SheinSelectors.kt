package com.example.autoa11y.plugins.shein

import com.example.autoa11y.core.api.Selector

internal object SheinSelectors {

    object Home {
        val visualSearch: Selector = Selector.ByDesc("VISUAL SEARCH")
        val searchEntry: Selector = Selector.CoordRatio(0.45f, 0.075f)
        val wishlist: Selector = Selector.ByDesc("Wishlist")
        val shopTab: Selector = Selector.ByText("Shop")
        val categoryTab: Selector = Selector.ByText("Category")
        val trendsTab: Selector = Selector.ByText("Trends")
        val feed: Selector = Selector.ById("$TARGET_PKG:id/recyclerView")
        val productPrice: Selector = Selector.ById("$TARGET_PKG:id/tv_price")
        val productCard: Selector = Selector.AnyOf(
            listOf(
                Selector.ClickableAncestorOf(productPrice, maxDepth = 6),
                Selector.CoordRatio(0.31f, 0.69f),
                Selector.CoordRatio(0.72f, 0.69f),
                Selector.CoordRatio(0.50f, 0.80f)
            )
        )
    }

    object SearchHome {
        val back: Selector = Selector.ByDesc("BACK")
        val input: Selector = Selector.AnyOf(
            listOf(
                Selector.ByClass("android.widget.EditText"),
                Selector.Editable(preferBottom = false)
            )
        )
        val searchButton: Selector = Selector.ByDesc("Search")
        val visualSearch: Selector = Selector.ByDesc("VISUAL SEARCH")
        val recentHeader: Selector = Selector.ByText("Recently Searched")
        val discoveryHeader: Selector = Selector.ByText("Search Discovery")
        val trendingHeader: Selector = Selector.ByText("Trending Search")
        val moreButton: Selector = Selector.ByDesc("Show More")

        val recentTapPrimary: Selector = Selector.CoordRatio(0.20f, 0.16f)
        val recentTapSecondary: Selector = Selector.CoordRatio(0.48f, 0.16f)
        val discoveryTapPrimary: Selector = Selector.CoordRatio(0.28f, 0.25f)
        val discoveryTapSecondary: Selector = Selector.CoordRatio(0.67f, 0.25f)
        val discoveryTapTertiary: Selector = Selector.CoordRatio(0.32f, 0.32f)
        val trendingTapPrimary: Selector = Selector.CoordRatio(0.50f, 0.43f)
        val trendingTapSecondary: Selector = Selector.CoordRatio(0.50f, 0.49f)
    }

    object Results {
        val back: Selector = Selector.ByDesc("BACK")
        val clear: Selector = Selector.ByDesc("Clear")
        val visualSearch: Selector = Selector.ByDesc("VISUAL SEARCH")
        val changeView: Selector = Selector.ByDesc("change view")
        val wishlist: Selector = Selector.ByDesc("Wishlist")
        val goToCart: Selector = Selector.ByDesc("Go to cart")
        val relatedLabel: Selector = Selector.ById("$TARGET_PKG:id/tv_label")
        val title: Selector = Selector.ById("$TARGET_PKG:id/tv_title")
        val priceLayout: Selector = Selector.ById("$TARGET_PKG:id/price_layout")

        val relatedTapPrimary: Selector = Selector.CoordRatio(0.18f, 0.13f)
        val relatedTapSecondary: Selector = Selector.CoordRatio(0.37f, 0.13f)
        val relatedTapTertiary: Selector = Selector.CoordRatio(0.58f, 0.13f)
        val relatedTapQuaternary: Selector = Selector.CoordRatio(0.79f, 0.13f)
        val relatedTapCandidates: List<Selector> = listOf(
            relatedTapPrimary,
            relatedTapSecondary,
            relatedTapTertiary,
            relatedTapQuaternary
        )

        val productCard: Selector = Selector.AnyOf(
            listOf(
                Selector.ClickableAncestorOf(title, maxDepth = 6),
                Selector.CoordRatio(0.27f, 0.60f),
                Selector.CoordRatio(0.74f, 0.60f),
                Selector.CoordRatio(0.27f, 0.79f),
                Selector.CoordRatio(0.74f, 0.79f)
            )
        )

        val fallbackProductCandidates: List<Selector> = listOf(
            Selector.CoordRatio(0.74f, 0.60f),
            Selector.CoordRatio(0.27f, 0.79f),
            Selector.CoordRatio(0.74f, 0.79f),
            Selector.CoordRatio(0.27f, 0.60f)
        )
    }

    object Detail {
        val topSearch: Selector = Selector.ByDesc("Search")
        val shoppingCart: Selector = Selector.ByDesc("shopping cart")
        val share: Selector = Selector.ByDesc("Share")
        val more: Selector = Selector.ByDesc("More")
        val photos: Selector = Selector.ByDesc("PHOTOS")
        val save: Selector = Selector.ByDesc("Save")
        val buyNow: Selector = Selector.ByText("Buy Now")
        val addToCart: Selector = Selector.ByText("Add to Cart", contains = true)
        val goodsTab: Selector = Selector.ByText("Goods")
        val reviewsTab: Selector = Selector.ByText("Reviews")
        val recommendTab: Selector = Selector.ByText("Recommend")
        val helpful: Selector = Selector.ByText("Helpful")
    }
}
