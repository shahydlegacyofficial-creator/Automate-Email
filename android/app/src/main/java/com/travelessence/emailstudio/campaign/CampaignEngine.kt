package com.travelessence.emailstudio.campaign

import com.travelessence.emailstudio.core.Attachment
import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.core.OutgoingEmail
import com.travelessence.emailstudio.core.Recipient
import com.travelessence.emailstudio.core.SendResult
import com.travelessence.emailstudio.core.Session
import com.travelessence.emailstudio.mail.MailSender
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import kotlin.math.ceil

data class ItemState(
    val recipient: Recipient,
    val status: String = "pending",   // pending | sending | sent | failed
    val time: String = "",
    val message: String = "",
)

data class CampaignState(
    val phase: String = "idle",       // idle | starting | sending | waiting | paused | completed | stopped | error
    val total: Int = 0,
    val done: Int = 0,
    val failed: Int = 0,
    val countdown: Int = 0,
    val interval: Int = 60,
    val current: Recipient? = null,
    val items: List<ItemState> = emptyList(),
    val subject: String = "",
    val startedAt: LocalDateTime? = null,
    val error: String = "",
    val autoPausedReason: String = "",
) {
    val sent get() = done - failed
    val running get() = phase in setOf("starting", "sending", "waiting", "paused")
    val paused get() = phase == "paused"

    /** Seconds until the last email goes out. */
    val etaSeconds: Long
        get() {
            val remaining = total - done
            if (remaining <= 0) return 0
            return countdown + (remaining - 1).toLong() * interval
        }
}

/**
 * Sends one email per recipient, waiting [interval] seconds between sends (measured from the
 * start of one send to the start of the next). Pausing freezes the countdown; stopping takes
 * effect immediately, even mid-wait.
 */
class CampaignEngine(
    private val sender: MailSender,
    private val recipients: List<Recipient>,
    private val subject: String,
    private val html: String,
    private val attachments: List<Attachment>,
    private val interval: Int,
    private val fallback: String,
    initialSession: Session,
    private val onSession: (Session) -> Unit,
) {
    companion object {
        const val MAX_CONSECUTIVE_FAILURES = 3
        private val TIME = DateTimeFormatter.ofPattern("HH:mm:ss")
    }

    private val _state = MutableStateFlow(
        CampaignState(
            phase = "starting", total = recipients.size, interval = interval, subject = subject,
            items = recipients.map { ItemState(it) }, startedAt = LocalDateTime.now(),
        )
    )
    val state: StateFlow<CampaignState> = _state

    var session: Session = initialSession
        private set

    @Volatile private var stopRequested = false
    @Volatile private var pauseRequested = false

    fun pause() {
        pauseRequested = true
        _state.update { if (it.running) it.copy(phase = "paused") else it }
    }

    fun resume() {
        pauseRequested = false
        _state.update { if (it.phase == "paused") it.copy(phase = if (it.countdown > 0) "waiting" else "sending", autoPausedReason = "") else it }
    }

    fun stop() {
        stopRequested = true
        pauseRequested = false
    }

    private fun record(r: Recipient, status: String, message: String) {
        val now = LocalDateTime.now()
        session = session.copy(
            results = session.results + SendResult(r.email, r.name, status, now.withNano(0).toString(), message),
            sent = session.sent + if (status == "sent") 1 else 0,
            failed = session.failed + if (status == "sent") 0 else 1,
        )
        runCatching { onSession(session) }
    }

    private fun setItem(index: Int, transform: (ItemState) -> ItemState) {
        _state.update { s ->
            val items = s.items.toMutableList()
            items[index] = transform(items[index])
            s.copy(items = items)
        }
    }

    private suspend fun waitWhilePaused() {
        while (pauseRequested && !stopRequested) delay(100)
    }

    private suspend fun waitInterval(startedAtMs: Long) {
        var remaining = interval * 1000L - (System.currentTimeMillis() - startedAtMs)
        var last = System.currentTimeMillis()
        var shown = -1
        while (remaining > 0 && !stopRequested) {
            val now = System.currentTimeMillis()
            if (!pauseRequested) remaining -= now - last
            last = now
            val seconds = ceil(remaining.coerceAtLeast(0) / 1000.0).toInt()
            if (seconds != shown) {
                shown = seconds
                _state.update { it.copy(countdown = seconds, phase = if (pauseRequested) "paused" else "waiting", current = null) }
            }
            delay(100)
        }
        _state.update { it.copy(countdown = 0) }
    }

    suspend fun run(): Session = withContext(Dispatchers.IO) {
        try {
            sender.open()
        } catch (e: Exception) {
            session = session.copy(status = "error", error = e.message ?: e.javaClass.simpleName,
                finished = LocalDateTime.now().withNano(0).toString())
            runCatching { onSession(session) }
            _state.update { it.copy(phase = "error", error = session.error) }
            return@withContext session
        }

        var consecutiveFailures = 0
        try {
            for ((index, recipient) in recipients.withIndex()) {
                if (stopRequested) break
                waitWhilePaused()
                if (stopRequested) break

                val startedAt = System.currentTimeMillis()
                _state.update { it.copy(phase = "sending", current = recipient) }
                setItem(index) { it.copy(status = "sending") }
                val email = OutgoingEmail(
                    to = listOf(recipient.email),
                    subject = Html.personalize(subject, recipient, fallback),
                    html = Html.personalize(html, recipient, fallback, isHtml = true),
                    attachments = attachments,
                )
                var status = "sent"
                var message = ""
                try {
                    sender.send(email)
                    consecutiveFailures = 0
                } catch (e: Exception) {
                    status = "failed"
                    message = e.message ?: e.javaClass.simpleName
                    consecutiveFailures++
                }
                record(recipient, status, message)
                setItem(index) { it.copy(status = status, message = message, time = LocalDateTime.now().format(TIME)) }
                _state.update { it.copy(done = it.done + 1, failed = it.failed + if (status == "sent") 0 else 1) }

                if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES && !pauseRequested) {
                    pauseRequested = true
                    consecutiveFailures = 0
                    _state.update { it.copy(phase = "paused", autoPausedReason = message) }
                }
                if (index < recipients.size - 1) waitInterval(startedAt)
            }
        } finally {
            runCatching { sender.close() }
        }

        val processed = session.sent + session.failed
        session = session.copy(
            status = if (processed < recipients.size) "stopped" else "completed",
            finished = LocalDateTime.now().withNano(0).toString(),
        )
        runCatching { onSession(session) }
        _state.update { it.copy(phase = session.status, current = null, countdown = 0) }
        session
    }
}
