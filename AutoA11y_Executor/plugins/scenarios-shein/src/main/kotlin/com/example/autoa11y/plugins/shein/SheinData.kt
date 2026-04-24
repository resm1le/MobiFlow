package com.example.autoa11y.plugins.shein

import com.example.autoa11y.core.common.keywords.CommonKeywords

internal const val TARGET_PKG = "com.zzkko"
internal const val TAG = "SheinProfile"

internal object SheinData {
    val keywordSearches: List<String> = CommonKeywords.fashionShoppingEn

    val homeTabs: List<String> = listOf(
        "Women",
        "Curve",
        "Men",
        "Kids",
        "Local",
        "Shoes",
        "Home"
    )
}
