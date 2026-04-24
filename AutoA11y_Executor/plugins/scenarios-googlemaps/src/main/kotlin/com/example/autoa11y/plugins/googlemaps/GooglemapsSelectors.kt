package com.example.autoa11y.plugins.googlemaps

import com.example.autoa11y.core.api.Selector

internal object GooglemapsSelectors {

    private const val SEARCH_OMNIBOX_LAYOUT_ID = "com.google.android.apps.maps:id/mod_search_omnibox_layout"
    private const val SEARCH_OMNIBOX_TEXT_BOX_ID = "com.google.android.apps.maps:id/search_omnibox_text_box"
    private const val EXPLORE_TAB_BUTTON_ID = "com.google.android.apps.maps:id/explore_tab_strip_button"

    object Anchors {
        val searchBar: Selector = Selector.AnyOf(
            listOf(
                Selector.ById(SEARCH_OMNIBOX_LAYOUT_ID),
                Selector.ById(SEARCH_OMNIBOX_TEXT_BOX_ID),
                Selector.ByDesc("在此处搜索"),
                Selector.ByText("搜索“", contains = true)
            )
        )
        val exploreTab: Selector = Selector.AnyOf(
            listOf(
                Selector.ByIdSelected(EXPLORE_TAB_BUTTON_ID, selected = true),
                Selector.ById(EXPLORE_TAB_BUTTON_ID),
                Selector.ByDesc("探索")
            )
        )
    }

    object Home {
        val searchBar: Selector = Anchors.searchBar
        val exploreTab: Selector = Anchors.exploreTab
    }

    object Search {
        val backNav: Selector = Selector.ByDesc("向上导航")
        val inputBox: Selector = Selector.ById("com.google.android.apps.maps:id/search_omnibox_edit_text")
    }

    object Results {
        val closeButton: Selector = Selector.ByDesc("关闭")
        val listContainer: Selector = Selector.ById("com.google.android.apps.maps:id/recycler_view")
        val resultCardTitle: Selector = Selector.ById("com.google.android.apps.maps:id/title")
        val resultCard: Selector = Selector.AnyOf(
            listOf(
                Selector.ClickableAncestorOf(resultCardTitle, maxDepth = 6),
                Selector.CoordRatio(0.50f, 0.58f),
                Selector.CoordRatio(0.50f, 0.72f),
                Selector.CoordRatio(0.50f, 0.84f)
            )
        )
    }

    object PlaceDetail {
        val headerCloseButton: Selector =
            Selector.ById("com.google.android.apps.maps:id/terra_navigation_header_close_button")
        val collapseButton: Selector = Selector.ByDesc("折叠", contains = true)
        val anchor: Selector = Selector.AnyOf(
            listOf(
                headerCloseButton,
                collapseButton
            )
        )
        val dismissButton: Selector = anchor
        val routeButton: Selector = Selector.AnyOf(
            listOf(
                Selector.ByText("路线"),
                Selector.ByDesc("路线", contains = true)
            )
        )
        val startNavButton: Selector = Selector.ByDesc("开始")
    }

    object Common {
        val backNav: Selector = Selector.ByDesc("向上导航")
        val closeButton: Selector = Selector.ByDesc("关闭")
    }
}
