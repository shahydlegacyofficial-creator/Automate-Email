package com.travelessence.emailstudio.campaign

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.travelessence.emailstudio.AppState
import com.travelessence.emailstudio.MainActivity
import com.travelessence.emailstudio.R
import com.travelessence.emailstudio.SignatureAssets
import com.travelessence.emailstudio.core.Attachment
import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.core.Recipient
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** Owns the running campaign. Lives in the Application so it survives leaving the screen. */
class CampaignController(private val context: Context, private val app: AppState) {
    companion object {
        const val CHANNEL_PROGRESS = "campaign_progress"
        const val CHANNEL_DONE = "campaign_done"
        const val NOTIFICATION_DONE = 2
    }

    private val _state = MutableStateFlow(CampaignState())
    val state: StateFlow<CampaignState> = _state
    private var engine: CampaignEngine? = null
    private var job: Job? = null

    val isRunning: Boolean get() = job?.isActive == true

    init {
        createChannels()
    }

    private fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL_PROGRESS, "Campaign progress", NotificationManager.IMPORTANCE_LOW).apply {
            description = "Shows the email campaign that is currently sending"
            setShowBadge(false)
        })
        nm.createNotificationChannel(NotificationChannel(CHANNEL_DONE, "Campaign finished", NotificationManager.IMPORTANCE_DEFAULT).apply {
            description = "Tells you when a campaign has finished"
        })
    }

    fun start(recipients: List<Recipient>, subject: String, fragmentHtml: String, attachments: List<Attachment>, interval: Int) {
        if (isRunning) return
        val settings = app.settings.value
        val session = app.storage.newSession("campaign", subject, settings.backend, interval, recipients, attachments)
        app.storage.saveSession(session)
        val e = CampaignEngine(
            sender = app.makeSender(),
            recipients = recipients,
            subject = subject,
            html = Html.buildEmail(fragmentHtml, SignatureAssets.forSettings(context, settings)),
            attachments = attachments,
            interval = interval,
            fallback = settings.nameFallback,
            initialSession = session,
            onSession = app.storage::saveSession,
        )
        engine = e
        _state.value = e.state.value
        job = app.scope.launch {
            val collector = launch { e.state.collect { _state.value = it } }
            val result = e.run()
            collector.cancel()
            _state.value = e.state.value
            app.historyVersion.value++
            val summary = when (result.status) {
                "error" -> "Campaign could not start: ${result.error}"
                "stopped" -> "Campaign stopped · ${result.sent} sent, ${result.failed} failed"
                else -> "Campaign complete · ${result.sent} sent, ${result.failed} failed"
            }
            app.notify(summary)
            notifyFinished(summary)
        }
        try {
            ContextCompat.startForegroundService(context, Intent(context, CampaignService::class.java))
        } catch (e: Exception) {
            // Android refuses a foreground service when the app is not on screen (Android 12+). The campaign
            // still runs; it just has no progress notification and may be paused by the system.
            app.notify("Open the app to keep the campaign running in the background.")
        }
    }

    fun pause() = engine?.pause()
    fun resume() = engine?.resume()
    fun stop() = engine?.stop()

    fun dismissResult() {
        if (!isRunning) _state.value = CampaignState()
    }

    private fun notifyFinished(text: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(context, CHANNEL_DONE)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Email campaign")
            .setContentText(text)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(NOTIFICATION_DONE, n)
    }
}
