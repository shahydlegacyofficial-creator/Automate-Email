package com.travelessence.emailstudio.agent

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
import com.travelessence.emailstudio.BuildConfig
import com.travelessence.emailstudio.MainActivity
import com.travelessence.emailstudio.R
import com.travelessence.emailstudio.agent.protocol.McpDispatcher
import com.travelessence.emailstudio.agent.protocol.McpHttpServer
import com.travelessence.emailstudio.campaign.CampaignController
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import java.net.Inet4Address
import java.net.NetworkInterface
import java.security.SecureRandom
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.Base64
import java.util.concurrent.atomic.AtomicLong

/**
 * Lets AI agents (Claude, Legacy AI, or any MCP client) use this app - the Android twin of the
 * desktop app's AI assistant connection. Off until the user switches it on. Only apps on this
 * phone can connect, unless the user also allows devices on the same Wi-Fi.
 */
class AgentServer(private val context: Context, private val state: AppState, campaign: CampaignController) {
    data class Activity(val time: String, val tool: String, val args: String, val ok: Boolean, val result: String)
    data class Status(val state: String = "off", val message: String = "Off", val urls: List<String> = emptyList())
    data class Approval(val id: Long, val title: String, val text: String, val approveLabel: String)

    companion object {
        const val CHANNEL = "agent_approval"
        const val NOTIFICATION_APPROVAL = 7
        const val APPROVAL_SECONDS = 120L
        private const val TOKEN_KEY = "ai_token"
    }

    private val _activity = MutableStateFlow<List<Activity>>(emptyList())
    val activity: StateFlow<List<Activity>> = _activity
    private val _status = MutableStateFlow(Status())
    val status: StateFlow<Status> = _status
    private val _approval = MutableStateFlow<Approval?>(null)
    val approval: StateFlow<Approval?> = _approval

    private val answers = java.util.concurrent.ConcurrentHashMap<Long, CompletableDeferred<Boolean>>()
    private val ids = AtomicLong(1)
    private var server: McpHttpServer? = null
    private var running: Triple<Int, Boolean, String>? = null

    private val tools = AgentTools(this, context, state, campaign)
    private val dispatcher = McpDispatcher(tools.all(), "legacy-ai-email-studio-android", BuildConfig.VERSION_NAME,
        "Legacy AI Email Studio", AgentTools.INSTRUCTIONS, ::record)

    init {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(CHANNEL, "AI agent approvals", NotificationManager.IMPORTANCE_HIGH).apply {
                    description = "Asks you before an AI agent sends email from this app"
                })
        }
    }

    // ------------------------------------------------------------------ token
    fun token(): String = state.secrets.get(TOKEN_KEY)?.takeIf { it.isNotBlank() } ?: newToken()

    fun newToken(): String {
        val bytes = ByteArray(24).also { SecureRandom().nextBytes(it) }
        val token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
        state.secrets.put(TOKEN_KEY, token)
        apply()
        return token
    }

    // ------------------------------------------------------------------ lifecycle
    /** Start, stop or restart the server to match the settings. Safe to call from any thread. */
    @Synchronized
    fun apply() {
        val s = state.settings.value
        if (!s.aiEnabled) {
            stop()
            _status.value = Status("off", "Off - AI agents can't use the app.")
            return
        }
        val token = state.secrets.get(TOKEN_KEY)?.takeIf { it.isNotBlank() }
            ?: Base64.getUrlEncoder().withoutPadding().encodeToString(ByteArray(24).also { SecureRandom().nextBytes(it) })
                .also { state.secrets.put(TOKEN_KEY, it) }
        val key = Triple(s.aiPort, s.aiLan, token)
        if (server?.running == true && running == key) return
        stop()
        val candidate = McpHttpServer(dispatcher, token, s.aiPort, s.aiLan) { lanAddresses().toSet() }
        try {
            candidate.start()
        } catch (e: Exception) {
            _status.value = Status("error", "Port ${s.aiPort} is in use (${e.message}). Choose another port.")
            return
        }
        server = candidate
        running = key
        _status.value = Status("on", if (s.aiLan) "Listening on this phone and your Wi-Fi" else "Listening on this phone", urls())
    }

    @Synchronized
    fun stop() {
        server?.stop()
        server = null
        running = null
    }

    fun urls(): List<String> {
        val s = state.settings.value
        val local = "http://127.0.0.1:${s.aiPort}/mcp"
        return if (s.aiLan) listOf(local) + lanAddresses().map { "http://$it:${s.aiPort}/mcp" } else listOf(local)
    }

    /** This phone's Wi-Fi / LAN IPv4 addresses. */
    fun lanAddresses(): List<String> = try {
        NetworkInterface.getNetworkInterfaces()?.toList().orEmpty()
            .filter { it.isUp && !it.isLoopback }
            .flatMap { it.inetAddresses.toList() }
            .filterIsInstance<Inet4Address>()
            .filter { it.isSiteLocalAddress }
            .mapNotNull { it.hostAddress }
            .distinct()
    } catch (_: Exception) {
        emptyList()
    }

    fun clientName(): String = dispatcher.clientName.ifBlank { "Your AI agent" }

    // ------------------------------------------------------------------ approvals
    /**
     * Ask the owner on the phone and wait (on the server thread) for the answer. Shows a dialog in the app
     * and a notification that opens it. No answer within two minutes = declined.
     */
    fun askOwner(title: String, text: String, approveLabel: String = "Approve & send"): Boolean {
        val id = ids.getAndIncrement()
        val answer = CompletableDeferred<Boolean>()
        answers[id] = answer
        _approval.value = Approval(id, title, text, approveLabel)
        notifyApproval(title, text)
        val result = runBlocking { withTimeoutOrNull(APPROVAL_SECONDS * 1000) { answer.await() } } ?: false
        answers.remove(id)
        if (_approval.value?.id == id) _approval.value = null
        NotificationManagerCompat.from(context).cancel(NOTIFICATION_APPROVAL)
        return result
    }

    fun answer(id: Long, approved: Boolean) {
        answers[id]?.complete(approved)
        if (_approval.value?.id == id) _approval.value = null
    }

    private fun notifyApproval(title: String, text: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val open = PendingIntent.getActivity(context, 7, Intent(context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_NEW_TASK), PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText("${clientName()} is waiting for your answer - tap to review")
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setContentIntent(open)
            .setAutoCancel(true)
            .setTimeoutAfter(APPROVAL_SECONDS * 1000)
            .build()
        NotificationManagerCompat.from(context).notify(NOTIFICATION_APPROVAL, n)
    }

    // ------------------------------------------------------------------ activity log
    private fun record(tool: String, args: JsonObject, result: JsonObject) {
        val isError = (result["isError"] as? JsonPrimitive)?.contentOrNull == "true"
        val text = runCatching {
            result["content"]!!.jsonArray[0].jsonObject["text"].let { (it as JsonPrimitive).content }
        }.getOrDefault("")
        val entry = Activity(
            time = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss")),
            tool = tool,
            args = if (args.isEmpty()) "" else args.toString().take(240),
            ok = !isError,
            result = if (isError) text.take(240) else AgentTools.summary(tool, result["structuredContent"] as? JsonObject),
        )
        _activity.value = (listOf(entry) + _activity.value).take(100)
    }
}
