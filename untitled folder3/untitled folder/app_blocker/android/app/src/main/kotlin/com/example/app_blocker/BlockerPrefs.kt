package com.example.app_blocker

import android.content.Context

object BlockerPrefs {
    private const val PREFS_NAME = "app_blocker_prefs"
    private const val KEY_BLOCKED_APPS = "blocked_apps"
    private const val KEY_BLOCK_MESSAGE = "block_message"
    private const val KEY_BLOCK_IMAGE = "block_image_path"

    fun getBlockedApps(context: Context): Set<String> {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getStringSet(KEY_BLOCKED_APPS, emptySet())?.toSet() ?: emptySet()
    }

    fun setBlockedApps(context: Context, packages: Set<String>) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putStringSet(KEY_BLOCKED_APPS, packages.toSet()).apply()
    }

    fun getBlockMessage(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_BLOCK_MESSAGE, "") ?: ""
    }

    fun setBlockMessage(context: Context, message: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_BLOCK_MESSAGE, message).apply()
    }

    fun getBlockImagePath(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_BLOCK_IMAGE, "") ?: ""
    }

    fun setBlockImagePath(context: Context, path: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_BLOCK_IMAGE, path).apply()
    }
}
