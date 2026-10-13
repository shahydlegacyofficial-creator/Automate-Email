package com.travelessence.emailstudio.campaign

import android.app.Notification
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.MainActivity
import com.travelessence.emailstudio.R
import kotlinx.coroutines.launch

/**
 * Foreground service that keeps the app alive (and the CPU awake) while a campaign waits
 * between emails, with a live progress notification and Pause / Stop actions.
 */
class CampaignService : LifecycleService() {
    companion object {
        const val NOTIFICATION_ID = 1
        const val ACTION_PAUSE = "pause"
        const val ACTION_RESUME = "resume"
        const val ACTION_STOP = "stop"
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var observing = false

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        val controller = App.instance.campaign
        when (intent?.action) {
            ACTION_PAUSE -> controller.pause()
            ACTION_RESUME -> controller.resume()
            ACTION_STOP -> controller.stop()
        }
        val type = if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0
        ServiceCompat.startForeground(this, NOTIFICATION_ID, build(controller.state.value), type)

        if (wakeLock == null) {
            wakeLock = (getSystemService(POWER_SERVICE) as PowerManager)
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "TravelEssence:campaign")
                .apply { acquire(24 * 60 * 60 * 1000L) }
        }
        if (!observing) {
            observing = true
            lifecycleScope.launch {
                controller.state.collect { s ->
                    if (!s.running) {
                        ServiceCompat.stopForeground(this@CampaignService, ServiceCompat.STOP_FOREGROUND_REMOVE)
                        stopSelf()
                    } else {
                        runCatching { NotificationManagerCompat.from(this@CampaignService).notify(NOTIFICATION_ID, build(s)) }
                    }
                }
            }
        }
        return START_NOT_STICKY
    }

    private fun action(name: String, label: String, code: Int): NotificationCompat.Action {
        val pi = PendingIntent.getService(this, code, Intent(this, CampaignService::class.java).setAction(name),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        return NotificationCompat.Action(0, label, pi)
    }

    private fun build(s: CampaignState): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java)
            .putExtra("screen", "Automation").addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE)
        val text = when (s.phase) {
            "paused" -> "Paused · ${s.done} of ${s.total} processed"
            "waiting" -> "${s.sent} sent · next email in ${s.countdown / 60}:${"%02d".format(s.countdown % 60)}"
            "sending" -> "Sending to ${s.current?.email.orEmpty()}…"
            else -> "${s.done} of ${s.total} processed"
        }
        return NotificationCompat.Builder(this, CampaignController.CHANNEL_PROGRESS)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Sending campaign · ${s.sent}/${s.total}")
            .setContentText(text)
            .setProgress(s.total.coerceAtLeast(1), s.done, false)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setContentIntent(open)
            .addAction(if (s.paused) action(ACTION_RESUME, "Resume", 1) else action(ACTION_PAUSE, "Pause", 1))
            .addAction(action(ACTION_STOP, "Stop", 2))
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    override fun onDestroy() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        super.onDestroy()
    }
}
