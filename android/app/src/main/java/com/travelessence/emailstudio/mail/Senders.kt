package com.travelessence.emailstudio.mail

import com.travelessence.emailstudio.core.Attachment
import com.travelessence.emailstudio.core.OutgoingEmail
import com.travelessence.emailstudio.core.SendException
import com.travelessence.emailstudio.core.Settings
import java.io.File

/**
 * A sending back-end. Used from one background thread: open() → send()… → close().
 * All calls block; callers run them on Dispatchers.IO.
 */
interface MailSender : AutoCloseable {
    val label: String
    fun open() {}
    fun send(email: OutgoingEmail)
    override fun close() {}
}

fun checkAttachments(attachments: List<Attachment>) {
    val missing = attachments.filter { !File(it.path).isFile }
    if (missing.isNotEmpty()) {
        throw SendException("Attachment not found: " + missing.joinToString { it.name })
    }
}

class SimulatedSender(private val delayMs: Long = 600) : MailSender {
    override val label = "Simulation (nothing is sent)"
    override fun send(email: OutgoingEmail) {
        checkAttachments(email.attachments)
        if (email.to.isEmpty()) throw SendException("No recipient")
        Thread.sleep(delayMs)
    }
}

fun backendLabel(settings: Settings): String = when (settings.backend) {
    "smtp" -> "SMTP · " + settings.smtpFromEmail.ifBlank { settings.smtpUsername.ifBlank { "not configured" } }
    "simulate" -> "Simulation mode (no emails are sent)"
    else -> "Microsoft 365 / Outlook · " + settings.msAccount.ifBlank { "not signed in" }
}

/** Builds the sender for the current settings. */
fun createSender(settings: Settings, smtpPassword: String, graph: GraphClient?): MailSender = when (settings.backend) {
    "smtp" -> SmtpSender(settings, smtpPassword)
    "simulate" -> SimulatedSender()
    else -> GraphSender(graph ?: throw SendException("Sign in to Microsoft 365 / Outlook in Settings first."))
}
