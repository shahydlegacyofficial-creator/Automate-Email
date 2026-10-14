@file:OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)

package com.travelessence.emailstudio

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.travelessence.emailstudio.core.Draft
import com.travelessence.emailstudio.core.Recipient
import com.travelessence.emailstudio.core.SendResult
import com.travelessence.emailstudio.ui.screens.*
import com.travelessence.emailstudio.ui.theme.LocalTones
import com.travelessence.emailstudio.ui.theme.TravelEssenceTheme
import com.travelessence.emailstudio.ui.theme.isDark
import java.time.LocalDateTime

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val app = application as App
        if (BuildConfig.DEBUG) seedDemo(app, intent)
        val start = intent.getStringExtra("screen")?.let { s -> Screen.entries.firstOrNull { it.name == s } } ?: Screen.Dashboard
        setContent {
            val settings by app.state.settings.collectAsStateWithLifecycle()
            TravelEssenceTheme(isDark(settings.theme)) {
                AppRoot(app, start)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra("screen")?.let { s ->
            Screen.entries.firstOrNull { it.name == s }?.let { (application as App).state.navigate(it) }
        }
    }

    override fun onStop() {
        super.onStop()
        (application as App).state.flush()
    }

    /** Debug builds only: `--ez demo true` fills the app with sample data for screenshots. */
    private fun seedDemo(app: App, intent: Intent) {
        intent.getStringExtra("theme")?.let { t -> app.state.saveSettings { it.copy(theme = t) } }
        if (intent.getBooleanExtra("start_campaign", false) && !app.campaign.isRunning) {
            val d = app.state.draft.value
            app.campaign.start(app.state.recipients.value, d.subject, d.html, d.attachments, 10)
            return
        }
        if (!intent.getBooleanExtra("demo", false) || app.state.recipients.value.isNotEmpty()) return
        val s = app.state
        s.saveSettings { it.copy(backend = "simulate", msAccount = "info@travelessence.com") }
        s.addRecipients(listOf(
            Recipient("sarah.khan@gmail.com", "Sarah Khan"), Recipient("john.smith@outlook.com", "John Smith"),
            Recipient("maria.lopez@hotmail.com", "Maria Lopez"), Recipient("leo@icloud.com"),
            Recipient("ali.raza@yahoo.com", "Ali Raza"), Recipient("emma.wilson@gmail.com", "Emma Wilson"),
        ))
        s.replaceDraft(Draft(
            subject = "{first_name}, your exclusive Travel Essence holiday offers",
            html = "<p>Dear {first_name},</p><p>Thank you for travelling with <b>Travel Essence</b>. We have hand-picked " +
                "<span style=\"color:#0B7A8F\">exclusive summer packages</span> for you:</p><ul><li>Maldives – 5 nights from £899</li>" +
                "<li>Dubai city break – 4 nights from £499</li></ul><p>Kind regards,<br>The Travel Essence Team</p>",
        ))
        val now = LocalDateTime.now().minusDays(2).withNano(0)
        val queue = s.recipients.value.take(4)
        s.storage.saveSession(s.storage.newSession("campaign", "Spring offers for {first_name}", "simulate", 60, queue, emptyList()).copy(
            started = now.toString(), finished = now.plusMinutes(3).toString(), status = "completed", sent = 4,
            results = queue.mapIndexed { i, r -> SendResult(r.email, r.name, "sent", now.plusMinutes(i.toLong()).toString()) },
        ))
    }
}

private val BOTTOM = listOf(
    Triple(Screen.Dashboard, "Home", Icons.Filled.Dashboard),
    Triple(Screen.Compose, "Compose", Icons.Filled.Edit),
    Triple(Screen.Recipients, "Recipients", Icons.Filled.People),
    Triple(Screen.Automation, "Automation", Icons.Filled.Bolt),
    Triple(Screen.More, "More", Icons.Filled.Apps),
)
private val MORE_CHILDREN = setOf(Screen.QuickSend, Screen.Signature, Screen.Outlook, Screen.History, Screen.Settings)

@Composable
fun AppRoot(app: App, start: Screen) {
    val state = app.state
    var screen by rememberSaveable { mutableStateOf(start) }
    val snackbar = remember { SnackbarHostState() }
    val settings by state.settings.collectAsStateWithLifecycle()
    val campaign by app.campaign.state.collectAsStateWithLifecycle()

    LaunchedEffect(Unit) { state.navigation.collect { screen = it } }
    LaunchedEffect(Unit) { state.messages.collect { snackbar.showSnackbar(it, withDismissAction = true) } }

    BackHandler(enabled = screen != Screen.Dashboard) {
        screen = if (screen in MORE_CHILDREN) Screen.More else Screen.Dashboard
    }

    Scaffold(
        topBar = {
            Column {
                TopAppBar(
                    title = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                Modifier.size(34.dp).background(
                                    Brush.linearGradient(listOf(LocalTones.current.gradientStart, LocalTones.current.gradientEnd)),
                                    MaterialTheme.shapes.medium,
                                ),
                                contentAlignment = Alignment.Center,
                            ) { Icon(Icons.Filled.Flight, null, tint = Color.White, modifier = Modifier.size(20.dp)) }
                            Spacer(Modifier.width(10.dp))
                            Column {
                                Text("Travel Essence", style = MaterialTheme.typography.titleMedium)
                                Text(screen.title, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    },
                    navigationIcon = {
                        if (screen in MORE_CHILDREN) {
                            IconButton(onClick = { screen = Screen.More }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
                        }
                    },
                    actions = {
                        val dark = isDark(settings.theme)
                        IconButton(onClick = { state.saveSettings { it.copy(theme = if (dark) "light" else "dark") } }) {
                            Icon(if (dark) Icons.Filled.LightMode else Icons.Filled.DarkMode, "Toggle theme")
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
                )
                if (campaign.running && screen != Screen.Automation) {
                    Column(
                        Modifier.fillMaxWidth().background(LocalTones.current.accentSoft)
                            .clickable { screen = Screen.Automation }.padding(horizontal = 16.dp, vertical = 6.dp)
                    ) {
                        Text(
                            (if (campaign.paused) "Campaign paused" else "Campaign sending") + " · ${campaign.done} of ${campaign.total} processed",
                            style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary,
                        )
                        Spacer(Modifier.height(4.dp))
                        LinearProgressIndicator(
                            progress = { if (campaign.total == 0) 0f else campaign.done / campaign.total.toFloat() },
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
                HorizontalDivider(color = LocalTones.current.border)
            }
        },
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                BOTTOM.forEach { (target, label, icon) ->
                    val selected = screen == target || (target == Screen.More && screen in MORE_CHILDREN)
                    NavigationBarItem(
                        selected = selected,
                        onClick = { screen = target },
                        icon = { Icon(icon, label) },
                        label = { Text(label) },
                    )
                }
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        Box(Modifier.padding(padding).consumeWindowInsets(padding).imePadding()) {
            when (screen) {
                Screen.Dashboard -> DashboardScreen(app)
                Screen.Compose -> ComposeScreen(app)
                Screen.Recipients -> RecipientsScreen(app)
                Screen.Automation -> AutomationScreen(app)
                Screen.More -> MoreScreen(app) { screen = it }
                Screen.QuickSend -> QuickSendScreen(app)
                Screen.Signature -> SignatureScreen(app)
                Screen.Outlook -> OutlookScreen(app)
                Screen.History -> HistoryScreen(app)
                Screen.Settings -> SettingsScreen(app)
            }
        }
    }
}
