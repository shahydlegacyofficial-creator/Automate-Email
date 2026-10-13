package com.travelessence.emailstudio.ui.screens

import android.content.ClipboardManager
import android.content.Context
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.Screen
import com.travelessence.emailstudio.core.Recipients
import com.travelessence.emailstudio.ui.Files
import com.travelessence.emailstudio.ui.components.*
import com.travelessence.emailstudio.ui.theme.LocalTones
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun RecipientsScreen(app: App) {
    val state = app.state
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val recipients by state.recipients.collectAsStateWithLifecycle()
    val settings by state.settings.collectAsStateWithLifecycle()
    val suppression = remember(settings.suppressionList) { Recipients.parseSuppression(settings.suppressionList) }

    var paste by remember { mutableStateOf("") }
    var result by remember { mutableStateOf("") }
    var search by remember { mutableStateOf("") }
    val selected = remember { mutableStateListOf<String>() }
    var editing by remember { mutableStateOf<String?>(null) }
    var confirmClear by remember { mutableStateOf(false) }

    fun report(r: Recipients.Result, source: String) {
        val (added, dupes) = state.addRecipients(r.recipients)
        val parts = mutableListOf("$added added from $source")
        val totalDupes = dupes + r.duplicates
        if (totalDupes > 0) parts += "$totalDupes duplicate${if (totalDupes == 1) "" else "s"} skipped"
        if (r.invalid.isNotEmpty()) parts += "${r.invalid.size} invalid: " + r.invalid.take(5).joinToString() + if (r.invalid.size > 5) "…" else ""
        result = parts.joinToString(" · ")
        state.notify("$added recipient${if (added == 1) "" else "s"} added")
    }

    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) scope.launch {
            val parsed = withContext(Dispatchers.IO) { runCatching { Files.parseRecipients(context, uri) } }
            parsed.onSuccess { (name, r) -> report(r, name) }.onFailure { state.notify("Could not read the file: ${it.message}") }
        }
    }
    val exporter = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("text/csv")) { uri ->
        if (uri != null) scope.launch {
            withContext(Dispatchers.IO) { Files.write(context, uri, Recipients.toCsv(state.recipients.value).toByteArray()) }
            state.notify("Recipient list exported")
        }
    }

    val needle = search.trim().lowercase()
    val visible = if (needle.isEmpty()) recipients else recipients.filter { needle in it.email || needle in it.name.lowercase() }
    val suppressedCount = recipients.count { Recipients.isSuppressed(it.email, suppression) }

    Page {
        item { PageHeader("Recipients", "Paste addresses in bulk or import a CSV, Excel or TXT file. Duplicates and invalid addresses are removed.") }
        item {
            SectionCard(title = "Add recipients", subtitle = "One per line, or separated by commas / semicolons. “Name <email>” and copied spreadsheet rows work too.") {
                OutlinedTextField(
                    paste, { paste = it }, modifier = Modifier.fillMaxWidth().heightIn(min = 140.dp),
                    placeholder = { Text("sarah.khan@gmail.com\nJohn Smith <john@outlook.com>\nAli Raza, ali.raza@yahoo.com") },
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    PrimaryButton("Add to list", Icons.Filled.Add, Modifier.weight(1f), enabled = paste.isNotBlank()) {
                        val r = Recipients.parseText(paste)
                        if (r.recipients.isEmpty() && r.invalid.isEmpty()) result = "No email addresses were found in the text."
                        else { report(r, "pasted text"); paste = "" }
                    }
                    SecondaryButton("Paste", Icons.Filled.ContentPaste, Modifier.weight(1f)) {
                        val clip = (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).primaryClip
                        val text = clip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(context)?.toString().orEmpty()
                        if (text.isBlank()) state.notify("The clipboard is empty") else {
                            val r = Recipients.parseText(text)
                            report(r, "clipboard")
                        }
                    }
                }
                SecondaryButton("Import CSV, Excel or TXT", Icons.Filled.Upload, Modifier.fillMaxWidth()) {
                    importer.launch(arrayOf("text/*", "text/csv", "text/comma-separated-values", "application/csv",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel",
                        "application/octet-stream"))
                }
                TextButton(onClick = { state.navigate(Screen.Outlook) }) {
                    Icon(Icons.Filled.Storage, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Collect from Outlook…")
                }
                if (result.isNotEmpty()) Text(result, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        item {
            SectionCard(title = "Recipient list", action = { Pill("%,d".format(recipients.size), Tone.Accent) }) {
                OutlinedTextField(search, { search = it }, Modifier.fillMaxWidth(), singleLine = true,
                    leadingIcon = { Icon(Icons.Filled.Search, null) }, placeholder = { Text("Search email or name") })
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SecondaryButton(if (selected.isEmpty()) "Remove" else "Remove (${selected.size})", Icons.Filled.Delete,
                        Modifier.weight(1f), enabled = selected.isNotEmpty()) {
                        val n = state.removeEmails(selected.toSet()); selected.clear()
                        state.notify("Removed $n recipient${if (n == 1) "" else "s"}")
                    }
                    SecondaryButton("Export", Icons.Filled.Download, Modifier.weight(1f), enabled = recipients.isNotEmpty()) {
                        exporter.launch("recipients.csv")
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (suppressedCount > 0) {
                        SecondaryButton("Do-not-email ($suppressedCount)", Icons.Filled.Block, Modifier.weight(1f)) {
                            val n = state.removeEmails(recipients.filter { Recipients.isSuppressed(it.email, suppression) }.map { it.email }.toSet())
                            state.notify("Removed $n address(es) on the do-not-email list")
                        }
                    }
                    SecondaryButton("Clear all", Icons.Filled.DeleteSweep, Modifier.weight(1f), enabled = recipients.isNotEmpty(),
                        color = LocalTones.current.danger) { confirmClear = true }
                }
                if (visible.size < recipients.size) {
                    Text("Showing ${visible.size} of ${recipients.size}", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (recipients.isEmpty()) {
                    Text("No recipients yet - paste addresses above or import a file.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        items(visible, key = { it.email }) { r ->
            val isSelected = r.email in selected
            val suppressed = Recipients.isSuppressed(r.email, suppression)
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
                    .background(if (isSelected) LocalTones.current.accentSoft else MaterialTheme.colorScheme.surface)
                    .clickable { editing = r.email }.padding(start = 4.dp, end = 12.dp, top = 4.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Checkbox(isSelected, { if (it) selected += r.email else selected -= r.email })
                Column(Modifier.weight(1f)) {
                    Text(r.email, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(r.name.ifBlank { "No name · tap to add" }, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                }
                if (suppressed) Pill("Do not email", Tone.Danger)
            }
        }
        item {
            PrimaryButton("Continue to automation", Icons.Filled.Bolt, Modifier.fillMaxWidth()) { state.navigate(Screen.Automation) }
        }
    }

    editing?.let { email ->
        val current = recipients.firstOrNull { it.email == email }
        TextInputDialog("Edit name", email, "Customer name", current?.name.orEmpty(), "Save", { editing = null }) {
            state.renameRecipient(email, it)
        }
    }
    if (confirmClear) {
        ConfirmDialog("Clear recipients", "Remove all ${recipients.size} recipients from the list?", "Clear", { confirmClear = false }) {
            state.setRecipients(emptyList()); selected.clear()
        }
    }
}
