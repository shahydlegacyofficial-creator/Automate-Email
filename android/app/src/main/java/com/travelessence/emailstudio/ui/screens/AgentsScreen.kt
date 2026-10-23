package com.travelessence.emailstudio.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.launch
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.agent.AgentTools
import com.travelessence.emailstudio.ui.components.*
import com.travelessence.emailstudio.ui.theme.LocalTones

@Composable
fun AgentsScreen(app: App) {
    val state = app.state
    val agent = app.agent
    val settings by state.settings.collectAsStateWithLifecycle()
    val status by agent.status.collectAsStateWithLifecycle()
    val activity by agent.activity.collectAsStateWithLifecycle()
    val clipboard = LocalClipboardManager.current
    var showToken by remember { mutableStateOf(false) }
    var confirmNew by remember { mutableStateOf(false) }
    var port by remember(settings.aiPort) { mutableStateOf(settings.aiPort.toString()) }
    val token = remember(settings.aiEnabled, status) { if (settings.aiEnabled) agent.token() else "" }
    val urls = status.urls.ifEmpty { agent.urls() }
    val wifiUrl = urls.firstOrNull { !it.contains("127.0.0.1") }

    fun copy(text: String, what: String) {
        clipboard.setText(AnnotatedString(text))
        state.notify("$what copied")
    }

    Page {
        item {
            PageHeader("AI agents", "Let your AI agent - Claude, Legacy AI or any MCP-compatible assistant - write and " +
                "send emails through this app, with your approval.")
        }
        item {
            SectionCard(title = "Connection", action = {
                Pill(when (status.state) { "on" -> "Ready"; "error" -> "Problem"; else -> "Off" },
                    when (status.state) { "on" -> Tone.Success; "error" -> Tone.Danger; else -> Tone.Neutral })
            }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Let AI agents use this app", style = MaterialTheme.typography.bodyLarge)
                        Text(status.message, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Switch(settings.aiEnabled, { on -> state.saveSettings { it.copy(aiEnabled = on) } })
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Allow devices on my Wi-Fi", style = MaterialTheme.typography.bodyLarge)
                        Text("Off: only apps on this phone can connect. On: your computer on the same Wi-Fi can too.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Switch(settings.aiLan, { on -> state.saveSettings { it.copy(aiLan = on) } })
                }
                if (settings.aiEnabled) {
                    FieldLabel("ADDRESS")
                    urls.forEach { url ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(url, Modifier.weight(1f), fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
                            IconButton(onClick = { copy(url, "Address") }) { Icon(Icons.Filled.ContentCopy, "Copy address") }
                        }
                    }
                    FieldLabel("ACCESS TOKEN")
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(if (showToken) token else "•".repeat(24), Modifier.weight(1f), fontFamily = FontFamily.Monospace,
                            style = MaterialTheme.typography.bodySmall)
                        IconButton(onClick = { showToken = !showToken }) {
                            Icon(if (showToken) Icons.Filled.VisibilityOff else Icons.Filled.Visibility, "Show token")
                        }
                        IconButton(onClick = { copy(token, "Access token") }) { Icon(Icons.Filled.ContentCopy, "Copy token") }
                    }
                    Text("Agents send it as “Authorization: Bearer <token>”. Anyone with the token can ask to send email, so " +
                        "keep it private.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        OutlinedTextField(port, { port = it.filter(Char::isDigit).take(5) }, Modifier.width(130.dp), singleLine = true,
                            label = { Text("Port") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                        SecondaryButton("Apply", Icons.Filled.Check) {
                            port.toIntOrNull()?.takeIf { it in 1024..65535 }?.let { p -> state.saveSettings { it.copy(aiPort = p) } }
                                ?: state.notify("Choose a port between 1024 and 65535")
                        }
                        TextButton(onClick = { confirmNew = true }) { Text("New token") }
                    }
                }
            }
        }
        item {
            SectionCard(title = "Approval", subtitle = "When the app asks you before an AI agent sends email.") {
                AgentTools.APPROVAL_CHOICES.forEach { (key, label) ->
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(settings.aiApproval == key, { state.saveSettings { it.copy(aiApproval = key) } })
                        Text(label, style = MaterialTheme.typography.bodyMedium)
                    }
                }
                Text("Requests you don't answer within 2 minutes are declined. Campaigns can only start while this app is " +
                    "on screen.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        if (settings.aiEnabled) item {
            val url = wifiUrl ?: urls.first()
            val claudeCode = "claude mcp add --transport http email-studio $url --header \"Authorization: Bearer $token\""
            val desktop = """{
  "mcpServers": {
    "email-studio": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "$url", "--allow-http", "--header", "Authorization:${'$'}{AUTH}"],
      "env": { "AUTH": "Bearer $token" }
    }
  }
}"""
            SectionCard(title = "Connect your agent", subtitle = if (wifiUrl == null)
                "Turn on “Allow devices on my Wi-Fi” to connect from a computer." else "From a computer on the same Wi-Fi:") {
                FieldLabel("CLAUDE CODE")
                CodeBox(claudeCode) { copy(claudeCode, "Command") }
                FieldLabel("CLAUDE DESKTOP, CURSOR AND OTHER APPS (claude_desktop_config.json / mcp.json)")
                CodeBox(desktop) { copy(desktop, "Configuration") }
                FieldLabel("LEGACY AI")
                Text("Settings → Tool armory → add a URL connection with the address and the token above.",
                    style = MaterialTheme.typography.bodySmall)
                Text("Keep this app open while your agent works - Android pauses apps in the background. A campaign keeps " +
                    "sending on its own once it has started.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        item {
            SectionCard(title = "What the AI did", subtitle = "Every request since the app started.") {
                if (activity.isEmpty()) Text("Nothing yet.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                activity.take(30).forEachIndexed { i, a ->
                    if (i > 0) HorizontalDivider(color = LocalTones.current.border)
                    Row(Modifier.padding(vertical = 6.dp)) {
                        Text(a.time, style = MaterialTheme.typography.labelSmall, modifier = Modifier.width(64.dp))
                        Column(Modifier.weight(1f)) {
                            Text(a.tool.replace('_', ' ').replaceFirstChar { it.uppercase() }, style = MaterialTheme.typography.bodyMedium)
                            Text(if (a.ok) a.result else "Refused: ${a.result}", style = MaterialTheme.typography.bodySmall,
                                color = if (a.ok) LocalTones.current.success else MaterialTheme.colorScheme.error)
                        }
                    }
                }
            }
        }
    }

    if (confirmNew) {
        ConfirmDialog("New access token", "Agents using the old token are disconnected until you give them the new one.",
            "Create", { confirmNew = false }) {
            state.scope.launch { agent.newToken() }
            showToken = true
            state.notify("New access token created")
        }
    }
}

@Composable
private fun CodeBox(text: String, onCopy: () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = MaterialTheme.shapes.small) {
        Row(Modifier.padding(start = 10.dp), verticalAlignment = Alignment.Top) {
            Text(text, Modifier.weight(1f).padding(vertical = 10.dp), fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodySmall)
            IconButton(onClick = onCopy) { Icon(Icons.Filled.ContentCopy, "Copy") }
        }
    }
}
