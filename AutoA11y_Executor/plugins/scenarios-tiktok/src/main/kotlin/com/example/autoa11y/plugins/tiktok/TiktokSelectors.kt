package com.example.autoa11y.plugins.tiktok

import com.example.autoa11y.core.api.Selector

/**
 * TikTok 首页（推荐 Feed）控件选择器。
 *
 * 所有选择器均基于 content-desc 定位（TikTok 的 resource-id 全部混淆，不稳定）。
 * 已在真机 UI dump 中逐一确认可达性。
 */
internal object TiktokSelectors {

    /** 页面锚点 —— 用于判断当前是否在首页推荐 Feed。 */
    object Anchors {
        // 底栏"首页"tab + 顶栏"推荐"tab 同时出现 => 首页推荐 Feed
        val home: Selector = Selector.AnyOf(
            listOf(
                Selector.ByDesc("首页"),
                Selector.ByDesc("推荐")
            )
        )
    }

    /** 首页交互控件。 */
    object Home {
        // 点赞按钮 —— content-desc 格式："点赞视频。xxx 个赞"
        val likeButton: Selector = Selector.ByDesc("点赞视频", contains = true)

        // 评论按钮 —— content-desc 格式："阅读或添加评论。xxx 条评论"
        val commentButton: Selector = Selector.ByDesc("阅读或添加评论", contains = true)

        // 收藏按钮 —— content-desc 格式："将此视频添加到或移出收藏。"
        val bookmarkButton: Selector = Selector.ByDesc("将此视频添加到或移出收藏", contains = true)

        // 底栏"首页"tab（用于 recovery 跳回首页）
        val bottomHomeTab: Selector = Selector.ByDesc("首页")
    }

    /** 通用返回。 */
    object Common {
        val back: Selector = Selector.AnyOf(
            listOf(
                Selector.ByDesc("Navigate up", contains = true),
                Selector.ByDesc("Back", contains = true)
            )
        )
    }
}
