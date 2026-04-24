package com.example.autoa11y.plugins.googlemaps

import com.example.autoa11y.core.common.keywords.CommonKeywords

internal const val TARGET_PKG = "com.google.android.apps.maps"
internal const val TAG = "GoogleMapsProfile"

/**
 * 搜索关键词池 —— 唯一性地名（城市/地址/特定地标）。
 * 搜索这些词汇通常会直接弹出对应的"地点详情页"和路线按钮，而不会出现列表。
 * 来源: CommonKeywords.mapsPlacesUnique (260+ 条)
 */
internal val SEARCH_DESTINATIONS_UNIQUE: List<String> = CommonKeywords.mapsPlacesUnique

/**
 * 搜索关键词池 —— 广泛性词汇（快餐/酒店/连锁品牌等）。
 * 搜索这些词汇通常会弹出"搜索结果"列表，需要用户从中挑选一家进入详情。
 * 来源: CommonKeywords.mapsPlacesGeneric (260+ 条)
 */
internal val SEARCH_DESTINATIONS_GENERIC: List<String> = CommonKeywords.mapsPlacesGeneric

/**
 * 附近搜索分类 —— 用于随机搜索附近商家。
 * 来源: CommonKeywords.mapsNearbyCategories (24 条)
 */
internal val NEARBY_CATEGORIES: List<String> = CommonKeywords.mapsNearbyCategories
