package com.example.autoa11y.shared
import java.text.SimpleDateFormat
import java.util.*
object Time {
    fun now(): Long = System.currentTimeMillis()
    fun iso(ts: Long = now()): String {
        val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US)
        return sdf.format(Date(ts))
    }
    fun runId(): String {
        val sdf = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US)
        return sdf.format(Date(now()))
    }
}
