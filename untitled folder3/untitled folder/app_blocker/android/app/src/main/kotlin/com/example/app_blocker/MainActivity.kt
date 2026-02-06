package com.example.app_blocker

import android.content.Intent
import android.os.Build
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val channelName = "app_blocker/native"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName).setMethodCallHandler { call, result ->
            when (call.method) {
                "startService" -> {
                    val intent = Intent(this, AppBlockerService::class.java)
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        startForegroundService(intent)
                    } else {
                        startService(intent)
                    }
                    result.success(true)
                }
                "stopService" -> {
                    stopService(Intent(this, AppBlockerService::class.java))
                    result.success(true)
                }
                "setBlockedApps" -> {
                    val apps = call.argument<List<String>>("packages") ?: emptyList()
                    BlockerPrefs.setBlockedApps(this, apps.toSet())
                    result.success(true)
                }
                "setBlockScreenConfig" -> {
                    val message = call.argument<String>("message") ?: ""
                    val imagePath = call.argument<String>("imagePath") ?: ""
                    BlockerPrefs.setBlockMessage(this, message)
                    BlockerPrefs.setBlockImagePath(this, imagePath)
                    result.success(true)
                }
                "getBlockScreenConfig" -> {
                    val message = BlockerPrefs.getBlockMessage(this)
                    val imagePath = BlockerPrefs.getBlockImagePath(this)
                    result.success(mapOf("message" to message, "imagePath" to imagePath))
                }
                "getInstalledApps" -> {
                    val pm = packageManager
                    val intent = Intent(Intent.ACTION_MAIN, null).apply {
                        addCategory(Intent.CATEGORY_LAUNCHER)
                    }
                    val resolveInfos = pm.queryIntentActivities(intent, 0)
                    val apps = resolveInfos.map { info ->
                        val pkg = info.activityInfo.packageName
                        val label = info.loadLabel(pm)?.toString() ?: pkg
                        mapOf("package" to pkg, "label" to label)
                    }.sortedBy { it["label"]?.lowercase() }
                    result.success(apps)
                }
                "isUsageAccessGranted" -> {
                    result.success(BlockerPermissions.hasUsageAccess(this))
                }
                "openUsageAccessSettings" -> {
                    startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
                    result.success(true)
                }
                "isOverlayGranted" -> {
                    result.success(BlockerPermissions.canDrawOverlays(this))
                }
                "openOverlaySettings" -> {
                    val intent = Intent(
                        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        android.net.Uri.parse("package:$packageName")
                    )
                    startActivity(intent)
                    result.success(true)
                }
                else -> result.notImplemented()
            }
        }
    }
}
