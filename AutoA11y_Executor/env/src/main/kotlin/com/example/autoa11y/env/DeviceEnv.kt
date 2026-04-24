package com.example.autoa11y.env

import android.content.Context
import com.example.autoa11y.drivers.shell.ShellBridge

data class EnvReport(val ok: Boolean, val details: Map<String, String>)

interface DeviceEnv {
    fun prepare(): EnvReport
    fun restore(): EnvReport
}

/**
 * 设备环境准备（root 环境下的便捷设置）：
 * - 关闭动画、保持唤醒、免打扰、固定竖屏、亮度等
 *
 * 说明：这里仍用 su -c 执行通用 settings/svc 命令，避免对 ShellBridge 增加通用 run API。
 */
class RootDeviceEnv(
    private val context: Context,
    private val shell: ShellBridge
) : DeviceEnv {
    private data class SettingSnapshot(val key: String, val value: String, val restoreCommand: String)

    private val snapshots = mutableListOf<SettingSnapshot>()
    private var prepared = false

    override fun prepare(): EnvReport {
        val cmds = listOf(
            Triple("global.window_animation_scale", readSetting("global", "window_animation_scale"), "settings put global window_animation_scale 0"),
            Triple("global.transition_animation_scale", readSetting("global", "transition_animation_scale"), "settings put global transition_animation_scale 0"),
            Triple("global.animator_duration_scale", readSetting("global", "animator_duration_scale"), "settings put global animator_duration_scale 0"),
            Triple("global.stay_on_while_plugged_in", readSetting("global", "stay_on_while_plugged_in"), "settings put global stay_on_while_plugged_in 3"),
            Triple("global.zen_mode", readSetting("global", "zen_mode"), "settings put global zen_mode 2"),
            Triple("system.accelerometer_rotation", readSetting("system", "accelerometer_rotation"), "settings put system accelerometer_rotation 0"),
            Triple("system.user_rotation", readSetting("system", "user_rotation"), "settings put system user_rotation 0"),
            Triple("system.screen_brightness", readSetting("system", "screen_brightness"), "settings put system screen_brightness 80")
        )
        if (!prepared) {
            snapshots.clear()
            cmds.forEach { (key, previous, _) ->
                snapshots += SettingSnapshot(
                    key = key,
                    value = previous,
                    restoreCommand = restoreCommandFor(key, previous)
                )
            }
        }

        val commandResults = mutableMapOf<String, String>()
        var ok = true
        cmds.forEach { (_, _, command) ->
            val result = shell.runCommand(command)
            commandResults[command] = result.rc.toString()
            ok = ok && result.rc == 0
        }
        val stayOnResult = shell.runCommand("svc power stayon true")
        commandResults["svc power stayon true"] = stayOnResult.rc.toString()
        ok = ok && stayOnResult.rc == 0
        prepared = ok
        return EnvReport(ok = ok, details = commandResults)
    }

    override fun restore(): EnvReport {
        if (!prepared && snapshots.isEmpty()) {
            return EnvReport(ok = true, details = emptyMap())
        }

        val commandResults = mutableMapOf<String, String>()
        var ok = true
        snapshots.forEach { snapshot ->
            val result = shell.runCommand(snapshot.restoreCommand)
            commandResults[snapshot.restoreCommand] = result.rc.toString()
            ok = ok && result.rc == 0
        }
        val stayOnResult = shell.runCommand("svc power stayon false")
        commandResults["svc power stayon false"] = stayOnResult.rc.toString()
        ok = ok && stayOnResult.rc == 0
        prepared = false
        snapshots.clear()
        return EnvReport(ok = ok, details = commandResults)
    }

    private fun readSetting(scope: String, key: String): String =
        shell.runCommand("settings get $scope $key").out.trim().ifBlank { "null" }

    private fun restoreCommandFor(key: String, value: String): String {
        val parts = key.split(".")
        val scope = parts.first()
        val name = parts.last()
        return if (value == "null") {
            "settings delete $scope $name"
        } else {
            "settings put $scope $name $value"
        }
    }
}
