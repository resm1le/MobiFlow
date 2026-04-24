package com.example.autoa11y.core.common

import com.example.autoa11y.core.api.Selector

/**
 * 设备级键盘/输入法相关的“通用坐标”定义。
 *
 * 注意：
 * - 这是设备相关的经验值（例如 Pixel 6 + 当前输入法布局）。
 * - 若更换设备/分辨率/输入法主题，请更新这些坐标或改用更稳定的 selector。
 */
object DeviceKeyboard {
    /** 键盘“回车/搜索/完成”键的固定像素坐标（px）。 */
    val enterKey: Selector = Selector.CoordPx(x = 1000, y = 2200)
}

