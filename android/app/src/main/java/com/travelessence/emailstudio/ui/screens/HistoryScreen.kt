package com.travelessence.emailstudio.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.Screen
import com.travelessence.emailstudio.core.Session
import com.travelessence.emailstudio.ui.Files
import com.travelessence.emailstudio.ui.components.*
import com.travelessence.emailstudio.ui.theme.LocalTones
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private val KIND = mapOf("campaign" to "Automation", "manual" to "Manual")

private fun statusTone(status: String) = when (status) {
    "completed" -> Tone.Success
    "stopped" -> Tone.Warning
    "error" -> Tone.Danger
    "running" -> Tone.Accent
    else -> Tone.Neutral
}

@Composable
fun HistoryScreen(app: App) {
    val state = app.state
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val version by state.historyVersion.collectAsStateWithLifecycle()
    var sessions by remember { mutableStateOf<List<Session>>(emptyList()) }
    var expanded by remember { mutableStateOf<String?>(null) }
    var toDelete by remember { mutableStateOf<Session?>(null) }
    var toRequeue by remember { mutableStateOf<Session?>(null) }
    var exporting by remember { mutableStateOf<Session?>(null) }

    LaunchedEffect(version) {
        sessions = withContext(Dispatchers.IO) { state.storage.loadSessions() }
        if (expanded == null) expanded = sessions.firstOrNull()?.id
    }

    val exporter = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("text/csv")) { uri ->
        val s = exporting
        if (uri != null && s != null) scope.launch {
            withContext(Dispatchers.IO) { Files.write(context, uri, state.storage.sessionCsv(s).toByteArray()) }
            state.notify("Session exported")
        }
    }

    Page {
        item { PageHeader("History", "Every automation session and manual email, with per-customer results.") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                StatCard("Emails sent", "%,d".format(sessions.sumOf { it.sent }), Icons.Filled.CheckCircle, Tone.Success, Modifier.weight(1f), "all time")
                StatCard("Sessions", "%,d".format(sessions.size), Icons.Filled.History, Tone.Accent, Modifier.weight(1f))
            }
        }
        if (sessions.isEmpty()) item { Text("Nothing sent yet.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        items(sessions, key = { it.id }) { s ->
            val open = expanded == s.id
            Card(
                Modifier.fillMaxWidth().clickable { expanded = if (open) null else s.id },
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                border = BorderStroke(1.dp, if (open) MaterialTheme.colorScheme.primary else LocalTones.current.border),
            ) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(s.subject.ifBlank { "(no subject)" }, style = MaterialTheme.typography.titleSmall,
                            modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Pill(s.status.replaceFirstChar { it.uppercase() }, statusTone(s.status))
                    }
                    Text("${KIND[s.kind] ?: s.kind} · ${formatIso(s.started)}", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        Text("${s.total} recipients", style = MaterialTheme.typography.bodySmall)
                        Text("${s.sent} sent", style = MaterialTheme.typography.bodySmall, color = LocalTones.current.success, fontWeight = FontWeight.SemiBold)
                        Text("${s.failed} failed", style = MaterialTheme.typography.bodySmall, color = LocalTones.current.danger, fontWeight = FontWeight.SemiBold)
                    }
                    if (s.error.isNotBlank()) Text(s.error, style = MaterialTheme.typography.bodySmall, color = LocalTones.current.danger)
                    if (open) {
                        HorizontalDivider(color = LocalTones.current.border)
                        val canRequeue = s.kind == "campaign" && s.status != "running"
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (canRequeue) SecondaryButton("Re-queue", Icons.Filled.Replay, Modifier.weight(1f)) { toRequeue = s }
                            SecondaryButton("Export", Icons.Filled.Download, Modifier.weight(1f)) {
                                exporting = s; exporter.launch("session-${s.id}.csv")
                            }
                            IconButton(onClick = { toDelete = s }) { Icon(Icons.Filled.Delete, "Delete", tint = LocalTones.current.danger) }
                        }
                        s.results.forEach { r ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(r.email, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Text(listOf(r.name, formatIso(r.time), r.message).filter { it.isNotBlank() }.joinToString(" · "),
                                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        maxLines = 2, overflow = TextOverflow.Ellipsis)
                                }
                                Text(if (r.status == "sent") "✓ Sent" else "✕ Failed",
                                    color = if (r.status == "sent") LocalTones.current.success else LocalTones.current.danger,
                                    style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
                            }
                        }
                        val notReached = s.total - s.results.size
                        if (notReached > 0) {
                            Text("$notReached customer(s) were not reached before the campaign stopped.",
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
    }

    toDelete?.let { s ->
        ConfirmDialog("Delete session", "Delete this session from history?", "Delete", { toDelete = null }) {
            if (s.status == "running" && app.campaign.isRunning) state.notify("This campaign is still running.")
            else {
                state.storage.deleteSession(s.id)
                state.historyVersion.value++
            }
        }
    }
    toRequeue?.let { s ->
        val sent = s.results.filter { it.status == "sent" }.map { it.email }.toSet()
        val pending = s.queue.filter { it.email !in sent }
        if (pending.isEmpty()) {
            MessageDialog("Re-queue", "Every customer in this session received the email.") { toRequeue = null }
        } else {
            ConfirmDialog("Re-queue", "Replace the current recipient list with the ${pending.size} customer(s) who did not receive this email (failed or never reached)?",
                "Re-queue", { toRequeue = null }) {
                state.setRecipients(pending)
                state.notify("${pending.size} customer(s) queued for the next campaign")
                state.navigate(Screen.Automation)
            }
        }
    }
}
