package com.example.app_blocker

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.widget.ImageView
import android.widget.TextView
import androidx.core.app.NotificationCompat
import java.io.File

class AppBlockerService : Service(), SharedPreferences.OnSharedPreferenceChangeListener {
    private val handler = Handler(Looper.getMainLooper())
    private val checkIntervalMs = 1000L
    private val notificationChannelId = "app_blocker_service"
    private val notificationId = 1001

    private lateinit var windowManager: WindowManager
    private var overlayView: View? = null
    private var blockedApps: Set<String> = emptySet()

    private val checkRunnable = object : Runnable {
        override fun run() {
            checkForegroundApp()
            handler.postDelayed(this, checkIntervalMs)
        }
    }

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        blockedApps = BlockerPrefs.getBlockedApps(this)

        val prefs = getSharedPreferences("app_blocker_prefs", Context.MODE_PRIVATE)
        prefs.registerOnSharedPreferenceChangeListener(this)

        startForeground(notificationId, buildNotification())
        handler.post(checkRunnable)
    }

    override fun onDestroy() {
        handler.removeCallbacks(checkRunnable)
        removeOverlay()
        val prefs = getSharedPreferences("app_blocker_prefs", Context.MODE_PRIVATE)
        prefs.unregisterOnSharedPreferenceChangeListener(this)
        super.onDestroy()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onSharedPreferenceChanged(sharedPreferences: SharedPreferences?, key: String?) {
        if (key == "blocked_apps") {
            blockedApps = BlockerPrefs.getBlockedApps(this)
        }
    }

    private fun checkForegroundApp() {
        if (!BlockerPermissions.hasUsageAccess(this)) {
            removeOverlay()
            return
        }

        val currentPackage = getForegroundPackage() ?: run {
            removeOverlay()
            return
        }

        if (currentPackage == packageName) {
            removeOverlay()
            return
        }

        if (blockedApps.contains(currentPackage)) {
            showOverlay(currentPackage)
        } else {
            removeOverlay()
        }
    }

    private fun getForegroundPackage(): String? {
        val usageStatsManager = getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val endTime = System.currentTimeMillis()
        val beginTime = endTime - 10000

        val events = usageStatsManager.queryEvents(beginTime, endTime)
        val event = UsageEvents.Event()
        var lastForeground: String? = null

        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            if (event.eventType == UsageEvents.Event.MOVE_TO_FOREGROUND) {
                lastForeground = event.packageName
            }
        }

        return lastForeground
    }

    private fun showOverlay(packageName: String) {
        if (overlayView != null) return
        if (!BlockerPermissions.canDrawOverlays(this)) return

        val layoutInflater = getSystemService(Context.LAYOUT_INFLATER_SERVICE) as LayoutInflater
        val view = layoutInflater.inflate(R.layout.overlay_block, null)

        val appNameView = view.findViewById<TextView>(R.id.blocked_app_name)
        val messageView = view.findViewById<TextView>(R.id.blocked_message)
        val imageView = view.findViewById<ImageView>(R.id.blocked_image)
        val appLabel = try {
            val appInfo = packageManager.getApplicationInfo(packageName, 0)
            packageManager.getApplicationLabel(appInfo).toString()
        } catch (e: Exception) {
            packageName
        }
        appNameView.text = appLabel
        val message = BlockerPrefs.getBlockMessage(this).ifBlank { "Nice try. Focus mode says no." }
        messageView.text = message

        val imagePath = BlockerPrefs.getBlockImagePath(this)
        if (imagePath.isNotBlank() && File(imagePath).exists()) {
            val bitmap = android.graphics.BitmapFactory.decodeFile(imagePath)
            imageView.setImageBitmap(bitmap)
            imageView.visibility = View.VISIBLE
        } else {
            imageView.visibility = View.GONE
        }

        val layoutType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            layoutType,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.TOP or Gravity.START

        windowManager.addView(view, params)
        overlayView = view
    }

    private fun removeOverlay() {
        overlayView?.let {
            windowManager.removeView(it)
            overlayView = null
        }
    }

    private fun buildNotification(): Notification {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                notificationChannelId,
                "App Blocker Service",
                NotificationManager.IMPORTANCE_LOW
            )
            manager.createNotificationChannel(channel)
        }

        return NotificationCompat.Builder(this, notificationChannelId)
            .setContentTitle("App Blocker is running")
            .setContentText("Blocking selected apps")
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setOngoing(true)
            .build()
    }
}
