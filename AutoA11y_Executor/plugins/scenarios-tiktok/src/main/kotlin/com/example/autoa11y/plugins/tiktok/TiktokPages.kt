package com.example.autoa11y.plugins.tiktok

import com.example.autoa11y.core.api.PageSignature

/**
 * TikTok 页面定义。
 *
 * 本插件只在首页推荐 Feed 操作，因此只定义一个 home 页面。
 */
internal object TiktokPages {
    val home: PageSignature = PageSignature(TARGET_PKG, must = listOf(TiktokSelectors.Anchors.home))
}
