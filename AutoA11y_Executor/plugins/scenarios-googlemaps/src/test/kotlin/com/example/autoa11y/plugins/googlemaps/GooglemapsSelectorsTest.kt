package com.example.autoa11y.plugins.googlemaps

import com.example.autoa11y.core.api.Selector
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class GooglemapsSelectorsTest {

    @Test
    fun homeSearchBarSupportsCurrentOmniboxIds() {
        val selector = assertIs<Selector.AnyOf>(GooglemapsSelectors.Anchors.searchBar)
        val ids = selector.items.filterIsInstance<Selector.ById>().map { it.id }
        assertTrue("com.google.android.apps.maps:id/mod_search_omnibox_layout" in ids)
        assertTrue("com.google.android.apps.maps:id/search_omnibox_text_box" in ids)
    }

    @Test
    fun homeExploreTabPrefersSelectedTabId() {
        val selector = assertIs<Selector.AnyOf>(GooglemapsSelectors.Anchors.exploreTab)
        val selectedId = assertIs<Selector.ByIdSelected>(selector.items.first())
        assertEquals("com.google.android.apps.maps:id/explore_tab_strip_button", selectedId.id)
        assertTrue(selectedId.selected)
    }
}
