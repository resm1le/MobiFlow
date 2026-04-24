package com.example.autoa11y.plugins.tiktok

import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.dsl.PageScope
import com.example.autoa11y.core.dsl.flow
import kotlin.random.Random

/**
 * TikTok 首页刷视频流程。
 *
 * 行为摘要：
 *   1. 在推荐 Feed 上反复滑动浏览短视频
 *   2. 随机点赞（~30%）
 *   3. 随机打开评论区浏览后关闭（~20%）
 *   4. 随机收藏（~15%）
 *   5. 全程不离开首页推荐 Feed
 *
 * 稳定性策略：
 *   - 点赞 / 评论 / 收藏均包裹在 attempt 中；若控件不可达则自动跳过，
 *     不影响主循环继续刷视频。
 *   - 最小回退：即使所有交互都失败，也至少保持"滑动浏览"。
 */
internal object TiktokFlows {

    /** 冷启动等待。 */
    fun startup(): Scenario = flow("tiktok_startup") {
        anyPage { pause(4_000L, 6_000L) }
    }

    /**
     * 主业务流：刷视频 + 随机交互。
     * 每次 session 调用产生一个 3~6 条视频的浏览片段。
     */
    fun mainFlow(): Scenario {
        val flowId = "tiktok_main_${Random.nextInt(10_000)}"
        return flow(flowId) {
            on(TiktokPages.home) { browseVideos() }
        }
    }

    /** 恢复流：尝试回到首页。 */
    fun recoveryFlow(reason: String): Scenario =
        flow("tiktok_recovery_${kotlin.math.abs(reason.hashCode())}") {
            // anyPage 只提供 ActionScope，直接调用动作
            anyPage {
                click(TiktokSelectors.Home.bottomHomeTab)
                pause(2_000L, 3_000L)
            }
        }
}

// ===================== 私有扩展函数 =====================

/**
 * 在首页推荐 Feed 上浏览 3~6 个视频，每个视频随机执行交互。
 */
private fun PageScope.browseVideos() {
    perform("browse_loop") {
        verify(TiktokSelectors.Anchors.home, 8_000L)
        repeatRandom(3..6) {
            // === 1. 观看当前视频 ===
            pause(2_000L, 12_000L)

            // === 2. 随机点赞（30%） ===
            if (chance(0.30f)) {
                tryLike()
            }

            // === 3. 随机收藏（15%） ===
            if (chance(0.15f)) {
                tryBookmark()
            }

            // === 4. 随机浏览评论（20%） ===
            if (chance(0.20f)) {
                tryViewComments()
            }

            // === 5. 上滑切换到下一个视频 ===
            swipeNextVideo()
            pause(800L, 1_500L)
        }
    }
}

/**
 * 尝试点赞 —— 找到按钮就点，找不到就跳过。
 */
private fun com.example.autoa11y.core.dsl.ActionScope.tryLike() {
    click(TiktokSelectors.Home.likeButton)
    pause(400L, 800L)
}

/**
 * 尝试收藏 —— 找到按钮就点，找不到就跳过。
 */
private fun com.example.autoa11y.core.dsl.ActionScope.tryBookmark() {
    click(TiktokSelectors.Home.bookmarkButton)
    pause(400L, 800L)
}

/**
 * 尝试浏览评论 —— 打开评论面板，停留后关闭。
 */
private fun com.example.autoa11y.core.dsl.ActionScope.tryViewComments() {
    click(TiktokSelectors.Home.commentButton)
    pause(3_000L, 8_000L)
    // 评论面板通过系统 back 关闭
    backForce()
    pause(800L, 1_200L)
}

/**
 * 上滑切换到下一个视频（全屏纵向滑动）。
 *
 * TikTok 视频 Feed 的特点是整屏切换，所以需要一个较大幅度的上滑
 * 从屏幕 80% 高度滑到 20% 高度。
 */
private fun com.example.autoa11y.core.dsl.ActionScope.swipeNextVideo() {
    swipe(fromX = 0.5f, fromY = 0.80f, toX = 0.5f, toY = 0.20f, durationMs = 400)
}
