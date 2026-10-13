package com.travelessence.emailstudio.ui.screens

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.PowerManager
import android.provider.Settings as AndroidSettings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.Screen
import com.travelessence.emailstudio.campaign.ItemState
import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.core.Recipients
import com.travelessence.emailstudio.mail.backendLabel
import com.travelessence.emailstudio.ui.components.*
import com.travelessence.emailstudio.ui.theme.LocalTones
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

private val INTERVALS = listOf(30 to "30 sec", 60 to "1 min", 120 to "2 min", 300 to "5 min")

@Composable
fun AutomationScreen(app: App) {
    val state = app.state
    val context = LocalContext.current
    val controller = app.campaign
    val campaign by controller.state.collectAsStateWithLifecycle()
    val draft by state.draft.collectAsStateWithLifecycle()
    val recipients by state.recipients.collectAsStateWithLifecycle()
    val settings by state.settings.collectAsStateWithLifecycle()

    val suppression = remember(settings.suppressionList) { Recipients.parseSuppression(settings.suppressionList) }
    val eligible = remember(recipients, suppression) { recipients.filter { !Recipients.isSuppressed(it.email, suppression) } }
    val skipped = recipients.size - eligible.size
    var interval by remember { mutableIntStateOf(settings.intervalSeconds) }
    var customInterval by remember { mutableStateOf(settings.intervalSeconds.toString()) }
    var confirmStart by remember { mutableStateOf(false) }
    var confirmStop by remember { mutableStateOf(false) }
    var problem by remember { mutableStateOf<String?>(null) }
    var batteryOk by remember { mutableStateOf(isIgnoringBattery(context)) }

    val notificationPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }

    val running = campaign.running
    val showRun = campaign.phase != "idle"
    val subject = draft.subject.trim()

    fun validate(): String? = when {
        subject.isEmpty() || Html.isBlank(draft.html) -> "Please write a subject and email content first."
        eligible.isEmpty() -> "Add at least one recipient first."
        draft.attachments.any { !File(it.path).isFile } -> "An attachment can no longer be found - remove it and add it again."
        settings.backend == "microsoft" && (settings.msClientId.isBlank() || state.graphClient()?.isSignedIn != true) ->
            "Sign in to Microsoft 365 / Outlook in Settings, or choose another sending method."
        settings.backend == "smtp" && settings.smtpHost.isBlank() -> "Set up your SMTP server in Settings first."
        else -> null
    }

    Page {
        item { PageHeader("Automation", "Sends your email to one customer at a time, waiting between each one (default: 1 email every minute).") }
        if (settings.backend == "simulate") {
            item { Banner("Simulation mode is on - campaigns run normally but no emails are actually sent. Change it in Settings.") }
        }
        if (!batteryOk) {
            item {
                SectionCard {
                    Banner("For long campaigns, allow the app to run unrestricted in the background so Android doesn't pause it.", Tone.Accent, Icons.Filled.BatteryAlert)
                    TextButton(onClick = {
                        runCatching { context.startActivity(Intent(AndroidSettings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) }
                        batteryOk = true
                    }) { Text("Open battery settings") }
                }
            }
        }
        item {
            val total = if (showRun) campaign.total else eligible.size
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatCard("Recipients", "%,d".format(total), Icons.Filled.People, Tone.Accent, Modifier.weight(1f),
                        if (!showRun && skipped > 0) "$skipped skipped" else "")
                    StatCard("Sent", "%,d".format(if (showRun) campaign.sent else 0), Icons.Filled.CheckCircle, Tone.Success, Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatCard("Failed", "%,d".format(if (showRun) campaign.failed else 0), Icons.Filled.Cancel, Tone.Danger, Modifier.weight(1f))
                    StatCard("Remaining", "%,d".format(if (showRun) campaign.total - campaign.done else eligible.size), Icons.Filled.Schedule,
                        Tone.Warning, Modifier.weight(1f))
                }
            }
        }
        item {
            SectionCard(title = "Campaign", subtitle = "Review before starting.") {
                FieldLabel("Subject")
                Text(subject.ifEmpty { "No subject yet - write your email first" }, fontWeight = FontWeight.SemiBold)
                Text(if (draft.attachments.isEmpty()) "No attachments" else "📎 " + draft.attachments.joinToString { it.name },
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                FieldLabel("Sending via")
                Text(backendLabel(settings), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                HorizontalDivider(color = LocalTones.current.border)
                FieldLabel("Time between emails")
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    INTERVALS.forEach { (seconds, label) ->
                        FilterChip(selected = interval == seconds, enabled = !running, onClick = {
                            interval = seconds; customInterval = seconds.toString()
                        }, label = { Text(label) })
                    }
                }
                OutlinedTextField(
                    customInterval, { v ->
                        customInterval = v.filter { it.isDigit() }.take(4)
                        customInterval.toIntOrNull()?.let { interval = it.coerceIn(10, 3600) }
                    },
                    label = { Text("Custom (seconds, 10–3600)") }, singleLine = true, enabled = !running,
                    modifier = Modifier.fillMaxWidth(),
                )
                val every = if (interval % 60 == 0) "${interval / 60} minute${if (interval == 60) "" else "s"}" else "$interval seconds"
                Text("1 email every $every · about ${3600 / interval} emails per hour" +
                    if (!running && eligible.isNotEmpty()) " · ≈ ${formatDuration((eligible.size - 1L) * interval)} for ${eligible.size} emails" else "",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                HorizontalDivider(color = LocalTones.current.border)
                if (!running) {
                    PrimaryButton("Start sending", Icons.Filled.PlayArrow, Modifier.fillMaxWidth()) {
                        val error = validate()
                        if (error != null) problem = error else confirmStart = true
                    }
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (campaign.paused) PrimaryButton("Resume", Icons.Filled.PlayArrow, Modifier.weight(1f)) { controller.resume() }
                        else SecondaryButton("Pause", Icons.Filled.Pause, Modifier.weight(1f)) { controller.pause() }
                        SecondaryButton("Stop", Icons.Filled.Stop, Modifier.weight(1f), color = LocalTones.current.danger) { confirmStop = true }
                    }
                }
            }
        }
        item { ProgressCard(campaign, if (showRun) campaign.total else eligible.size) }
        if (campaign.autoPausedReason.isNotEmpty() && campaign.paused) {
            item {
                Banner("Sending was paused after several failures in a row. Last error: ${campaign.autoPausedReason}. " +
                    "Fix the problem (for example check your connection or sign-in) and press Resume.", Tone.Danger)
            }
        }
        item {
            Column {
                Text("Activity log", style = MaterialTheme.typography.titleMedium)
                Text("Every email in this session and its delivery status.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        val items = if (showRun) campaign.items else eligible.map { ItemState(it) }
        if (items.isEmpty()) item { Text("No recipients yet.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        itemsIndexed(items, key = { i, it -> "$i-${it.recipient.email}" }) { i, item -> LogRow(i + 1, item) }
        if (!running && campaign.phase in setOf("completed", "stopped", "error")) {
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SecondaryButton("Clear results", Icons.Filled.Refresh, Modifier.weight(1f)) { controller.dismissResult() }
                    SecondaryButton("View history", Icons.Filled.History, Modifier.weight(1f)) { state.navigate(Screen.History) }
                }
            }
        }
    }

    if (confirmStart) {
        val duration = formatDuration((eligible.size - 1L).coerceAtLeast(0) * interval)
        ConfirmDialog(
            "Start campaign",
            "Send “$subject” to ${eligible.size} customer${if (eligible.size == 1) "" else "s"}, one email every $interval seconds.\n\n" +
                "Sending via: ${backendLabel(settings)}\nEstimated duration: about $duration" +
                (if (skipped > 0) "\n\n$skipped address(es) on the do-not-email list will be skipped." else "") +
                "\n\nYou can leave the app - a notification shows progress and lets you pause or stop.",
            "Start", { confirmStart = false },
        ) {
            if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
                PackageManager.PERMISSION_GRANTED) {
                notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
            if (interval != settings.intervalSeconds) state.saveSettings { it.copy(intervalSeconds = interval) }
            controller.start(eligible, subject, draft.html, draft.attachments, interval)
        }
    }
    if (confirmStop) {
        ConfirmDialog("Stop campaign", "Stop sending? Customers not yet emailed will not receive it. You can re-queue them later from History.",
            "Stop", { confirmStop = false }) { controller.stop() }
    }
    problem?.let { MessageDialog("Not ready", it) { problem = null } }
}

private fun isIgnoringBattery(context: Context): Boolean =
    (context.getSystemService(Context.POWER_SERVICE) as PowerManager).isIgnoringBatteryOptimizations(context.packageName)

@Composable
private fun ProgressCard(c: com.travelessence.emailstudio.campaign.CampaignState, total: Int) {
    val tones = LocalTones.current
    val (label, tone) = when (c.phase) {
        "sending", "starting" -> "Sending" to Tone.Accent
        "waiting" -> "Running" to Tone.Accent
        "paused" -> "Paused" to Tone.Warning
        "completed" -> "Completed" to Tone.Success
        "stopped" -> "Stopped" to Tone.Warning
        "error" -> "Could not start" to Tone.Danger
        else -> "Ready" to Tone.Neutral
    }
    SectionCard(title = "Session progress", action = { Pill(label, tone) }) {
        Row(verticalAlignment = Alignment.Bottom) {
            Column(Modifier.weight(1f)) {
                Text("%,d / %,d".format(c.sent, total), style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Bold)
                Text("emails sent this session", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    when {
                        c.phase == "sending" -> "Now"
                        c.countdown > 0 -> "%02d:%02d".format(c.countdown / 60, c.countdown % 60)
                        else -> "--:--"
                    },
                    style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold,
                )
                Text(if (c.paused) "paused" else if (c.phase == "sending") "sending…" else "next email in",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        val fraction = if (c.total == 0) 0f else c.done / c.total.toFloat()
        Box(Modifier.fillMaxWidth().height(26.dp).clip(RoundedCornerShape(13.dp)).background(MaterialTheme.colorScheme.surfaceVariant)) {
            Box(Modifier.fillMaxHeight().fillMaxWidth(fraction).clip(RoundedCornerShape(13.dp))
                .background(androidx.compose.ui.graphics.Brush.horizontalGradient(listOf(tones.gradientStart, tones.gradientEnd))))
            Text("${c.done} of ${if (c.total == 0) total else c.total} processed · ${(fraction * 100).toInt()}%",
                Modifier.align(Alignment.Center), style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
        }
        val time = DateTimeFormatter.ofPattern("HH:mm")
        InfoRow("Now sending to", c.current?.let { if (it.name.isNotBlank()) "${it.name} <${it.email}>" else it.email }
            ?: if (c.phase == "waiting") "Waiting for the next send…" else "—")
        InfoRow("Started", c.startedAt?.format(DateTimeFormatter.ofPattern("dd MMM yyyy, HH:mm")) ?: "—")
        InfoRow("Estimated finish", when {
            c.running -> LocalDateTime.now().plusSeconds(c.etaSeconds).format(time) + "  (${formatDuration(c.etaSeconds)} left)"
            c.phase == "completed" -> "Finished"
            else -> "—"
        })
        InfoRow("Success rate", if (c.done > 0) "${c.sent * 100 / c.done}%" else "—")
        if (c.phase == "error") Text(c.error, color = tones.danger, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row {
        Text(label.uppercase(), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(130.dp).padding(top = 2.dp))
        Text(value, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun LogRow(number: Int, item: ItemState) {
    val tones = LocalTones.current
    val (label, color) = when (item.status) {
        "sent" -> "✓ Sent" to tones.success
        "failed" -> "✕ Failed" to tones.danger
        "sending" -> "… Sending" to MaterialTheme.colorScheme.primary
        else -> "Pending" to MaterialTheme.colorScheme.onSurfaceVariant
    }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(MaterialTheme.colorScheme.surface).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("$number", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(32.dp))
        Column(Modifier.weight(1f)) {
            Text(item.recipient.email, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val detail = listOf(item.recipient.name, item.time, item.message.ifEmpty { if (item.status == "sent") "Delivered" else "" })
                .filter { it.isNotBlank() }.joinToString(" · ")
            if (detail.isNotEmpty()) {
                Text(detail, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
        }
        Text(label, color = color, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelMedium)
    }
}
