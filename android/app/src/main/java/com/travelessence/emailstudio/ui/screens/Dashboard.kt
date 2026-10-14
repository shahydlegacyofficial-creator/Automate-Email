package com.travelessence.emailstudio.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.Screen
import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.core.Session
import com.travelessence.emailstudio.mail.backendLabel
import com.travelessence.emailstudio.ui.components.*
import com.travelessence.emailstudio.ui.theme.LocalTones
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

fun formatIso(iso: String?): String = try {
    if (iso.isNullOrBlank()) "" else LocalDateTime.parse(iso).format(DateTimeFormatter.ofPattern("dd MMM yyyy, HH:mm"))
} catch (e: Exception) { iso.orEmpty() }

/** Standard scrolling page with the shared padding. */
@Composable
fun Page(content: androidx.compose.foundation.lazy.LazyListScope.() -> Unit) {
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
        content = content,
    )
}

@Composable
fun DashboardScreen(app: App) {
    val state = app.state
    val recipients by state.recipients.collectAsStateWithLifecycle()
    val draft by state.draft.collectAsStateWithLifecycle()
    val settings by state.settings.collectAsStateWithLifecycle()
    val historyVersion by state.historyVersion.collectAsStateWithLifecycle()
    val campaign by app.campaign.state.collectAsStateWithLifecycle()
    var sessions by remember { mutableStateOf<List<Session>>(emptyList()) }
    LaunchedEffect(historyVersion) { sessions = withContext(Dispatchers.IO) { state.storage.loadSessions() } }

    val hour = LocalDateTime.now().hour
    val greeting = if (hour < 12) "Good morning" else if (hour < 18) "Good afternoon" else "Good evening"
    val ready = draft.subject.isNotBlank() && !Html.isBlank(draft.html)

    Page {
        item { PageHeader(greeting, "Compose once, then let the app send it to each customer one by one.") }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatCard("Recipients", "%,d".format(recipients.size), Icons.Filled.People, Tone.Accent, Modifier.weight(1f), "in your list")
                    StatCard("Emails sent", "%,d".format(sessions.sumOf { it.sent }), Icons.AutoMirrored.Filled.Send, Tone.Success, Modifier.weight(1f), "all time")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatCard("Campaigns", "%,d".format(sessions.count { it.kind == "campaign" }), Icons.Filled.Bolt, Tone.Warning, Modifier.weight(1f), "sessions")
                    StatCard("Failed", "%,d".format(sessions.sumOf { it.failed }), Icons.Filled.Cancel, Tone.Danger, Modifier.weight(1f), "all time")
                }
            }
        }
        item {
            SectionCard(title = "Get a campaign out in 3 steps") {
                StepRow(1, "Write your email", "Subject, message, attachments and personal fields.", Icons.Filled.Edit,
                    if (ready) "Ready" else "To do", if (ready) Tone.Success else Tone.Warning) { state.navigate(Screen.Compose) }
                HorizontalDivider(color = LocalTones.current.border)
                StepRow(2, "Add recipients", "Paste addresses, import a spreadsheet or collect them from Outlook.", Icons.Filled.People,
                    if (recipients.isEmpty()) "To do" else "${recipients.size} added", if (recipients.isEmpty()) Tone.Warning else Tone.Success) {
                    state.navigate(Screen.Recipients)
                }
                HorizontalDivider(color = LocalTones.current.border)
                val stepThree = when {
                    campaign.running -> "Running" to Tone.Accent
                    ready && recipients.isNotEmpty() -> "Ready to start" to Tone.Accent
                    else -> "Waiting" to Tone.Neutral
                }
                StepRow(3, "Start the automation", "One email per customer, one minute apart, with live progress.", Icons.Filled.Bolt,
                    stepThree.first, stepThree.second) { state.navigate(Screen.Automation) }
            }
        }
        item {
            SectionCard(title = "Sending status") {
                Text(backendLabel(settings), style = MaterialTheme.typography.bodyLarge)
                Text(
                    when (settings.backend) {
                        "simulate" -> "Practice mode: nothing is actually sent."
                        "smtp" -> "Emails are delivered directly through your SMTP server."
                        else -> if (settings.msAccount.isBlank()) "Sign in from Settings to send from your Outlook mailbox."
                        else "Emails go out from your Outlook mailbox and are saved in Sent Items."
                    },
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                TextButton(onClick = { state.navigate(Screen.Settings) }) { Text("Change in Settings") }
            }
        }
        item {
            SectionCard(title = "Last campaign") {
                val last = sessions.firstOrNull { it.kind == "campaign" }
                if (last == null) Text("No campaigns yet.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                else {
                    Text(last.subject, style = MaterialTheme.typography.titleSmall)
                    Text("${formatIso(last.started)} · ${last.sent} sent · ${last.failed} failed · ${last.status.replaceFirstChar { it.uppercase() }}",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                TextButton(onClick = { state.navigate(Screen.History) }) { Text("View history") }
            }
        }
    }
}

@Composable
private fun StepRow(number: Int, title: String, text: String, icon: ImageVector, status: String, tone: Tone, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        IconBadge(icon, Tone.Accent, 42)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("$number. $title", style = MaterialTheme.typography.titleSmall)
                Spacer(Modifier.width(8.dp))
                Pill(status, tone)
            }
            Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun MoreScreen(app: App, open: (Screen) -> Unit) {
    val settings by app.state.settings.collectAsStateWithLifecycle()
    Page {
        item { PageHeader("More tools", "Manual sending, Outlook data, history and settings.") }
        item {
            SectionCard {
                MoreRow(Icons.Filled.Mail, "Write & send", "Compose a one-off email and send it now") { open(Screen.QuickSend) }
                HorizontalDivider(color = LocalTones.current.border)
                MoreRow(Icons.Filled.Badge, "Email signature", "Contact details, social links and logo under every email") { open(Screen.Signature) }
                HorizontalDivider(color = LocalTones.current.border)
                MoreRow(Icons.Filled.Storage, "Outlook data", "Collect customers and past emails from your mailbox") { open(Screen.Outlook) }
                HorizontalDivider(color = LocalTones.current.border)
                MoreRow(Icons.Filled.History, "History", "Every campaign with per-customer results") { open(Screen.History) }
                HorizontalDivider(color = LocalTones.current.border)
                MoreRow(Icons.Filled.Settings, "Settings", "Sending method, sign-in, defaults, theme") { open(Screen.Settings) }
            }
        }
        item {
            SectionCard(title = "Appearance") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("system" to "System", "light" to "Light", "dark" to "Dark").forEach { (key, label) ->
                        FilterChip(selected = settings.theme == key, onClick = { app.state.saveSettings { it.copy(theme = key) } },
                            label = { Text(label) },
                            leadingIcon = {
                                Icon(when (key) { "light" -> Icons.Filled.LightMode; "dark" -> Icons.Filled.DarkMode; else -> Icons.Filled.Contrast }, null,
                                    Modifier.size(18.dp))
                            })
                    }
                }
            }
        }
    }
}

@Composable
private fun MoreRow(icon: ImageVector, title: String, text: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        IconBadge(icon, Tone.Accent, 40)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleSmall)
            Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
