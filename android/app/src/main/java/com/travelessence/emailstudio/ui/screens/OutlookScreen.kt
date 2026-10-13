@file:OptIn(ExperimentalMaterial3Api::class)

package com.travelessence.emailstudio.ui.screens

import android.Manifest
import android.content.pm.PackageManager
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
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.Screen
import com.travelessence.emailstudio.core.Draft
import com.travelessence.emailstudio.core.Recipient
import com.travelessence.emailstudio.core.Recipients
import com.travelessence.emailstudio.core.SendException
import com.travelessence.emailstudio.core.Xlsx
import com.travelessence.emailstudio.data.*
import com.travelessence.emailstudio.ui.Files
import com.travelessence.emailstudio.ui.components.*
import com.travelessence.emailstudio.ui.theme.LocalTones
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.concurrent.atomic.AtomicBoolean

private val SOURCES = listOf(
    "graph" to "Microsoft 365 / Outlook.com",
    "imap" to "Email account (IMAP)",
    "phone" to "Phone contacts",
)

@Composable
fun OutlookScreen(app: App) {
    val state = app.state
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings by state.settings.collectAsStateWithLifecycle()

    var source by rememberSaveableString(if (settings.backend == "smtp") "imap" else "graph")
    var folder by rememberSaveableString("sent")
    var from by remember { mutableStateOf(LocalDate.now().minusMonths(6)) }
    var to by remember { mutableStateOf(LocalDate.now()) }
    var subjectFilter by remember { mutableStateOf("") }
    var exclude by remember { mutableStateOf(settings.outlookExclude) }
    var maxItems by remember { mutableStateOf("2000") }
    var datePicker by remember { mutableStateOf<String?>(null) }

    var running by remember { mutableStateOf(false) }
    var progress by remember { mutableFloatStateOf(0f) }
    var progressText by remember { mutableStateOf("") }
    var job by remember { mutableStateOf<Job?>(null) }
    val cancelFlag = remember { AtomicBoolean(false) }
    var result by remember { mutableStateOf<CollectResult?>(null) }
    var tab by remember { mutableIntStateOf(0) }
    var search by remember { mutableStateOf("") }
    val selected = remember { mutableStateListOf<String>() }
    var templateTarget by remember { mutableStateOf<MessageRow?>(null) }
    var problem by remember { mutableStateOf<String?>(null) }

    fun collect() {
        if (exclude != settings.outlookExclude) state.saveSettings { it.copy(outlookExclude = exclude) }
        val options = CollectOptions(
            folder = folder,
            from = from.atStartOfDay(),
            to = to.atTime(LocalTime.MAX),
            subjectContains = subjectFilter,
            exclude = exclude.replace(';', ',').split(',').map { it.trim().lowercase() }.filter { it.isNotEmpty() },
            maxItems = maxItems.toIntOrNull()?.coerceIn(10, 100_000) ?: 2000,
        )
        cancelFlag.set(false)
        running = true
        progress = 0f
        progressText = "Connecting…"
        selected.clear()
        val report: Progress = { current, total, message ->
            scope.launch {
                progressText = message
                progress = if (total > 0) (current.toFloat() / total).coerceIn(0f, 1f) else 0f
            }
        }
        job = scope.launch {
            val outcome = withContext(Dispatchers.IO) {
                runCatching {
                    when (source) {
                        "phone" -> PhoneContacts.collect(context, options.exclude, report)
                        "imap" -> ImapMailbox.collect(settings, state.smtpPassword, options, report) { cancelFlag.get() }
                        else -> {
                            val client = state.graphClient() ?: throw SendException("Add your Application (client) ID and sign in under Settings → Microsoft 365.")
                            if (!client.isSignedIn) throw SendException("Sign in to Microsoft 365 / Outlook in Settings first.")
                            GraphMailbox.collect(client, options, report) { cancelFlag.get() }
                        }
                    }
                }
            }
            running = false
            outcome.onSuccess {
                result = it
                progress = 1f
                progressText = "Scanned ${it.scanned} items"
                tab = if (it.messages.isEmpty()) 0 else tab
                state.notify("Collected ${it.contacts.size} customers and ${it.messages.size} emails")
            }.onFailure {
                progressText = ""
                problem = it.message ?: it.javaClass.simpleName
            }
        }
    }

    val contactsPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) collect() else problem = "Contacts permission is needed to read phone contacts."
    }

    val exporter = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    ) { uri ->
        val r = result
        if (uri != null && r != null) scope.launch {
            val rows = if (tab == 0) {
                listOf(listOf("Email", "Name", "Company", "Phone", "Emails", "Last contact", "Last subject")) +
                    r.contacts.map { listOf(it.email, it.name, it.company, it.phone, it.interactions.toString(), formatDate(it.lastContact), it.lastSubject) }
            } else {
                listOf(listOf("Date", "Folder", "From", "To", "Subject", "Attachments")) +
                    r.messages.map { listOf(formatDate(it.date), it.folder, it.sender, it.recipients, it.subject, if (it.attachments > 0) "Yes" else "") }
            }
            withContext(Dispatchers.IO) { Files.write(context, uri, Xlsx.write(rows, if (tab == 0) "Customers" else "Emails")) }
            state.notify("Exported to Excel")
        }
    }

    val r = result
    val needle = search.trim().lowercase()
    val contacts = r?.contacts.orEmpty().filter { needle.isEmpty() || needle in it.email || needle in it.name.lowercase() || needle in it.company.lowercase() }
    val messages = r?.messages.orEmpty().filter { needle.isEmpty() || needle in it.subject.lowercase() || needle in it.recipients || needle in it.sender }

    Page {
        item { PageHeader("Outlook data", "Collect customer addresses and the emails Travel Essence has sent - then reuse them as recipients or templates.") }
        item {
            SectionCard(title = "Source", subtitle = "Your own addresses are always excluded.") {
                Dropdown("Read from", SOURCES, source) { source = it; if (it != "graph" && folder == "contacts") folder = "sent" }
                if (source == "graph") {
                    if (settings.msAccount.isBlank()) Banner("Sign in under Settings → Sending method → Microsoft 365 to read your Outlook mailbox.", Tone.Accent)
                    else Text("Signed in as ${settings.msAccount}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (source == "imap" && settings.imapHost.isBlank()) {
                    Banner("Set the IMAP server in Settings → SMTP to read your mailbox.", Tone.Accent)
                }
                if (source == "phone") {
                    Text("Reads email contacts saved on this phone, including contacts synced by the Outlook app.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    val folders = if (source == "graph") FOLDER_CHOICES else FOLDER_CHOICES.filter { it.first != "contacts" }
                    Dropdown("Folder", folders, folder) { folder = it }
                    if (folder != "contacts") {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            DateField("From", from, Modifier.weight(1f)) { datePicker = "from" }
                            DateField("To", to, Modifier.weight(1f)) { datePicker = "to" }
                        }
                        OutlinedTextField(subjectFilter, { subjectFilter = it }, Modifier.fillMaxWidth(), singleLine = true,
                            label = { Text("Subject contains") }, placeholder = { Text("e.g. Travel Essence, Booking, Quotation") })
                        OutlinedTextField(maxItems, { maxItems = it.filter(Char::isDigit).take(6) }, Modifier.fillMaxWidth(), singleLine = true,
                            label = { Text("Max emails") })
                    }
                }
                OutlinedTextField(exclude, { exclude = it }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("Exclude addresses / domains") }, placeholder = { Text("@travelessence.com, noreply@…") })
                if (running) {
                    LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth())
                    Text(progressText, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    SecondaryButton("Cancel", Icons.Filled.Stop, Modifier.fillMaxWidth()) { cancelFlag.set(true); job?.cancel(); running = false }
                } else {
                    if (progressText.isNotEmpty()) Text(progressText, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    PrimaryButton("Collect data", Icons.Filled.Storage, Modifier.fillMaxWidth()) {
                        if (source == "phone" && ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
                            contactsPermission.launch(Manifest.permission.READ_CONTACTS)
                        } else collect()
                    }
                }
            }
        }
        if (r != null) {
            item {
                SectionCard(title = "Results", action = { Pill("${r.contacts.size} customers · ${r.messages.size} emails", Tone.Accent) }) {
                    TabRow(selectedTabIndex = tab, containerColor = MaterialTheme.colorScheme.surface) {
                        Tab(tab == 0, { tab = 0 }, text = { Text("Customers (${r.contacts.size})") })
                        Tab(tab == 1, { tab = 1 }, text = { Text("Emails (${r.messages.size})") })
                    }
                    OutlinedTextField(search, { search = it }, Modifier.fillMaxWidth(), singleLine = true,
                        leadingIcon = { Icon(Icons.Filled.Search, null) }, placeholder = { Text("Search") })
                    if (tab == 0) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            PrimaryButton(if (selected.isEmpty()) "Add selected" else "Add ${selected.size}", Icons.Filled.PersonAdd,
                                Modifier.weight(1f), enabled = selected.isNotEmpty()) {
                                val pick = r.contacts.filter { it.email in selected }.map { Recipient(it.email, it.name) }
                                val (added, dupes) = state.addRecipients(pick)
                                selected.clear()
                                state.notify("$added added to recipients" + if (dupes > 0) " · $dupes already in the list" else "")
                            }
                            SecondaryButton("Add all", Icons.Filled.People, Modifier.weight(1f), enabled = contacts.isNotEmpty()) {
                                val (added, dupes) = state.addRecipients(contacts.filter { Recipients.isValid(it.email) }.map { Recipient(it.email, it.name) })
                                state.notify("$added added to recipients" + if (dupes > 0) " · $dupes already in the list" else "")
                            }
                        }
                        TextButton(onClick = {
                            if (selected.size == contacts.size) selected.clear() else { selected.clear(); selected.addAll(contacts.map { it.email }) }
                        }) { Text(if (selected.size == contacts.size && contacts.isNotEmpty()) "Select none" else "Select all") }
                    } else {
                        Text("Tap an email to reuse its subject, content and attachments as your campaign email.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    SecondaryButton("Export to Excel", Icons.Filled.Download, Modifier.fillMaxWidth()) {
                        exporter.launch(if (tab == 0) "travel-essence-customers.xlsx" else "travel-essence-emails.xlsx")
                    }
                }
            }
            if (tab == 0) {
                items(contacts, key = { it.email }) { c ->
                    val isSelected = c.email in selected
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
                            .background(if (isSelected) LocalTones.current.accentSoft else MaterialTheme.colorScheme.surface)
                            .clickable { if (isSelected) selected -= c.email else selected += c.email }
                            .padding(start = 4.dp, end = 12.dp, top = 6.dp, bottom = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Checkbox(isSelected, { if (it) selected += c.email else selected -= c.email })
                        Column(Modifier.weight(1f)) {
                            Text(c.name.ifBlank { c.email }, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(listOf(if (c.name.isNotBlank()) c.email else "", c.company, c.phone).filter { it.isNotBlank() }.joinToString(" · "),
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                            if (c.lastContact != null) {
                                Text("${c.interactions} email${if (c.interactions == 1) "" else "s"} · last ${formatDate(c.lastContact)} · ${c.lastSubject}",
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                        }
                    }
                }
            } else {
                items(messages, key = { it.id }) { m ->
                    Column(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(MaterialTheme.colorScheme.surface)
                            .clickable { templateTarget = m }.padding(12.dp),
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(m.subject.ifBlank { "(no subject)" }, style = MaterialTheme.typography.titleSmall, maxLines = 1,
                                overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                            if (m.attachments > 0) Icon(Icons.Filled.AttachFile, "Has attachments", Modifier.size(16.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text("${formatDate(m.date)} · ${m.folder}", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("To: ${m.recipients}", style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }

    datePicker?.let { which ->
        val initial = if (which == "from") from else to
        val pickerState = rememberDatePickerState(initialSelectedDateMillis = initial.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli())
        DatePickerDialog(
            onDismissRequest = { datePicker = null },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let { ms ->
                        val d = Instant.ofEpochMilli(ms).atZone(ZoneOffset.UTC).toLocalDate()
                        if (which == "from") from = d else to = d
                    }
                    datePicker = null
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { datePicker = null }) { Text("Cancel") } },
        ) { DatePicker(pickerState) }
    }

    templateTarget?.let { m ->
        ConfirmDialog("Use as template", "Replace the email in Compose with “${m.subject}”?", "Use it", { templateTarget = null }) {
            progressText = "Loading email…"
            scope.launch {
                val loaded = withContext(Dispatchers.IO) {
                    runCatching {
                        val save: SaveAttachment = { name, mime, bytes -> state.storage.storeAttachment(name, mime, bytes) }
                        if (m.id.startsWith("graph:")) {
                            GraphMailbox.load(state.graphClient() ?: throw SendException("Not signed in"), m.id.removePrefix("graph:"), save)
                        } else {
                            ImapMailbox.load(settings, state.smtpPassword, m.id.removePrefix("imap:"), save)
                        }
                    }
                }
                progressText = ""
                loaded.onSuccess {
                    state.replaceDraft(Draft(it.subject, it.html, it.attachments))
                    state.notify("Email loaded into Compose" + if (it.skipped.isNotEmpty()) " (${it.skipped.size} attachment(s) skipped - only JPG, PNG and PDF)" else "")
                    state.navigate(Screen.Compose)
                }.onFailure { problem = it.message }
            }
        }
    }
    problem?.let { MessageDialog("Outlook data", it) { problem = null } }
}

@Composable
private fun DateField(label: String, date: LocalDate, modifier: Modifier, onClick: () -> Unit) {
    Box(modifier) {
        OutlinedTextField(date.format(DateTimeFormatter.ofPattern("dd MMM yyyy")), {}, readOnly = true, singleLine = true,
            label = { Text(label) }, trailingIcon = { Icon(Icons.Filled.CalendarMonth, null) }, modifier = Modifier.fillMaxWidth())
        Box(Modifier.matchParentSize().clickable(onClick = onClick))
    }
}

@Composable
fun rememberSaveableString(initial: String): MutableState<String> =
    androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf(initial) }
