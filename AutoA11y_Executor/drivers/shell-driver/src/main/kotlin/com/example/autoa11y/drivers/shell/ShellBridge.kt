package com.example.autoa11y.drivers.shell

import android.util.Log
import java.io.BufferedReader

class ShellBridge(private val ctx: android.content.Context? = null) {
    data class Result(val rc: Int, val out: String, val err: String)

    private fun run(vararg cmd: String): Result {
        return try {
            val p = Runtime.getRuntime().exec(cmd)
            val rc = p.waitFor()
            val out = p.inputStream.bufferedReader().use(BufferedReader::readText)
            val err = p.errorStream.bufferedReader().use(BufferedReader::readText)
            Log.i(TAG, "exec rc=$rc cmd=${cmd.joinToString(" ")}")
            Result(rc, out, err)
        } catch (e: Throwable) {
            Log.e(TAG, "exec error: ${e.message}")
            Result(-1, "", e.message ?: "")
        }
    }

    private fun suOrSh(arg: String): Result {
        val su = run("su", "-c", arg)
        return if (su.rc == 0) su else run("sh", "-c", arg)
    }

    private fun suOnly(arg: String): Result = run("su", "-c", arg)

    fun runCommand(arg: String, preferSu: Boolean = true): Result =
        if (preferSu) suOrSh(arg) else run("sh", "-c", arg)

    fun listFileNames(dirAbs: String): List<String> {
        val escaped = shellQuote(dirAbs)
        val result = suOrSh("if [ -d '$escaped' ]; then ls -1A '$escaped'; fi")
        if (result.rc != 0) return emptyList()
        return result.out
            .lineSequence()
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .toList()
    }

    fun readInterfaceRxBytes(interfaceName: String): Long? {
        val result = suOrSh("cat /proc/net/dev")
        if (result.rc != 0) return null
        val target = "$interfaceName:"
        return result.out
            .lineSequence()
            .map { it.trim() }
            .firstOrNull { it.startsWith(target) }
            ?.substringAfter(":")
            ?.trim()
            ?.split(Regex("\\s+"))
            ?.firstOrNull()
            ?.toLongOrNull()
    }

    fun removeFile(absPath: String): Boolean {
        val escaped = shellQuote(absPath)
        val result = suOnly("rm -f -- '$escaped'")
        if (result.rc != 0) return false
        return !pathExists(absPath)
    }

    fun pathExists(absPath: String): Boolean {
        val escaped = shellQuote(absPath)
        val result = suOrSh("if [ -e '$escaped' ]; then echo 1; else echo 0; fi")
        return result.rc == 0 && result.out.trim() == "1"
    }

    fun inputTap(x: Int, y: Int): Boolean =
        suOrSh("input tap $x $y").rc == 0

    fun inputSwipe(x1: Int, y1: Int, x2: Int, y2: Int, durMs: Int): Boolean =
        suOrSh("input swipe $x1 $y1 $x2 $y2 $durMs").rc == 0

    fun inputKey(keyCode: Int): Boolean =
        suOrSh("input keyevent $keyCode").rc == 0

    fun inputText(raw: String): Boolean {
        val encoded = encodeForInput(raw)
        return suOrSh("input text \"$encoded\"").rc == 0
    }

    fun amStart(target: String): Boolean {
        val cmd = if (target.contains("/")) {
            "am start -W -n $target"
        } else {
            "monkey -p $target -c android.intent.category.LAUNCHER 1 || am start -W $target"
        }
        return suOrSh(cmd).rc == 0
    }

    fun amForceStop(pkg: String): Boolean =
        suOrSh("am force-stop $pkg").rc == 0

    fun screenCap(absPath: String): Boolean =
        suOrSh("screencap -p '${shellQuote(absPath)}'").rc == 0

    fun dumpWindowHierarchy(absPath: String): Boolean =
        suOrSh("uiautomator dump '${shellQuote(absPath)}'").rc == 0

    fun copyDir(srcAbs: String, dstAbs: String): Boolean =
        suOrSh("mkdir -p '${shellQuote(dstAbs)}' && cp -r '${shellQuote(srcAbs)}'/. '${shellQuote(dstAbs)}'").rc == 0

    companion object {
        private const val TAG = "ShellBridge"

        private fun shellQuote(raw: String): String = raw.replace("'", "'\\''")

        private fun encodeForInput(raw: String): String {
            val specials = setOf('&', '|', '<', '>', ';', '(', ')', '{', '}', '$', '*', '?', '!', '\\')
            return buildString {
                raw.forEach { ch ->
                    when (ch) {
                        ' ' -> append("%s")
                        '"' -> append("\\\"")
                        '\'' -> append("\\'")
                        in specials -> {
                            append('\\')
                            append(ch)
                        }
                        else -> append(ch)
                    }
                }
            }
        }
    }
}
