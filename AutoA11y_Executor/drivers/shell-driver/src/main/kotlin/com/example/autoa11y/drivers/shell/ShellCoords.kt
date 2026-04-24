package com.example.autoa11y.drivers.shell

import android.content.Context
import android.util.DisplayMetrics
import android.view.WindowManager

object ShellCoords {
    fun screenSize(ctx: Context): Pair<Int, Int> {
        val wm = ctx.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val dm = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(dm)
        return dm.widthPixels to dm.heightPixels
    }

    fun fromRatio(ctx: Context, rx: Float, ry: Float): Pair<Int, Int> {
        val (w, h) = screenSize(ctx)
        return (w * rx).toInt() to (h * ry).toInt()
    }
}
