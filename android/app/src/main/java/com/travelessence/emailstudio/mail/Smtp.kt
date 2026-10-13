package com.travelessence.emailstudio.mail

import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.core.OutgoingEmail
import com.travelessence.emailstudio.core.SendException
import com.travelessence.emailstudio.core.Settings
import java.io.File
import java.util.Date
import java.util.Properties
import javax.activation.DataHandler
import javax.activation.FileDataSource
import javax.mail.AuthenticationFailedException
import javax.mail.Flags
import javax.mail.Folder
import javax.mail.Message
import javax.mail.MessagingException
import javax.mail.Part
import javax.mail.Session
import javax.mail.Store
import javax.mail.Transport
import javax.mail.internet.InternetAddress
import javax.mail.internet.MimeBodyPart
import javax.mail.internet.MimeMessage
import javax.mail.internet.MimeMultipart
import javax.mail.util.ByteArrayDataSource

object Mime {
    fun smtpSession(settings: Settings): Session {
        val p = Properties()
        p["mail.smtp.host"] = settings.smtpHost
        p["mail.smtp.port"] = settings.smtpPort.toString()
        p["mail.smtp.auth"] = settings.smtpUsername.isNotBlank().toString()
        p["mail.smtp.connectiontimeout"] = "30000"
        p["mail.smtp.timeout"] = "60000"
        p["mail.smtp.writetimeout"] = "60000"
        when (settings.smtpSecurity) {
            "ssl" -> {
                p["mail.smtp.ssl.enable"] = "true"
                p["mail.smtp.ssl.checkserveridentity"] = "true"
            }
            "starttls" -> {
                p["mail.smtp.starttls.enable"] = "true"
                p["mail.smtp.starttls.required"] = "true"
                p["mail.smtp.ssl.checkserveridentity"] = "true"
            }
        }
        p["mail.imaps.host"] = settings.imapHost
        p["mail.imaps.port"] = settings.imapPort.toString()
        p["mail.imaps.connectiontimeout"] = "30000"
        p["mail.imaps.timeout"] = "60000"
        p["mail.imaps.ssl.checkserveridentity"] = "true"
        p["mail.mime.charset"] = "UTF-8"
        return Session.getInstance(p)
    }

    /** multipart/mixed { alternative { text, related { html, inline images } }, attachments } */
    fun build(session: Session, fromEmail: String, fromName: String, email: OutgoingEmail): MimeMessage {
        val (html, images) = Html.extractInlineImages(email.html)
        val msg = MimeMessage(session)
        msg.setFrom(if (fromName.isNotBlank()) InternetAddress(fromEmail, fromName, "UTF-8") else InternetAddress(fromEmail))
        msg.setRecipients(Message.RecipientType.TO, email.to.joinToString(","))
        if (email.cc.isNotEmpty()) msg.setRecipients(Message.RecipientType.CC, email.cc.joinToString(","))
        msg.setSubject(email.subject, "UTF-8")
        msg.sentDate = Date()

        val textPart = MimeBodyPart().apply { setText(Html.toText(email.html).ifBlank { " " }, "UTF-8") }
        val htmlPart = MimeBodyPart().apply { setContent(html, "text/html; charset=utf-8") }
        val htmlContainer: MimeBodyPart = if (images.isEmpty()) htmlPart else {
            val related = MimeMultipart("related")
            related.addBodyPart(htmlPart)
            for (img in images) {
                related.addBodyPart(MimeBodyPart().apply {
                    dataHandler = DataHandler(ByteArrayDataSource(img.bytes, img.mime))
                    setHeader("Content-ID", "<${img.cid}>")
                    disposition = Part.INLINE
                    fileName = img.fileName
                })
            }
            MimeBodyPart().apply { setContent(related) }
        }
        val alternative = MimeMultipart("alternative").apply {
            addBodyPart(textPart)
            addBodyPart(htmlContainer)
        }
        if (email.attachments.isEmpty()) {
            msg.setContent(alternative)
        } else {
            val mixed = MimeMultipart("mixed")
            mixed.addBodyPart(MimeBodyPart().apply { setContent(alternative) })
            for (a in email.attachments) {
                mixed.addBodyPart(MimeBodyPart().apply {
                    dataHandler = DataHandler(FileDataSource(File(a.path)))
                    setHeader("Content-Type", a.mime)
                    fileName = a.name
                    disposition = Part.ATTACHMENT
                })
            }
            msg.setContent(mixed)
        }
        msg.saveChanges()
        return msg
    }

    fun findSentFolder(store: Store): Folder? {
        val all = try { store.defaultFolder.list("*").toList() } catch (e: MessagingException) { emptyList() }
        all.firstOrNull { f ->
            (f as? com.sun.mail.imap.IMAPFolder)?.attributes?.any { it.equals("\\Sent", true) } == true
        }?.let { return it }
        val names = listOf("sent items", "sent", "sent mail", "[gmail]/sent mail", "inbox.sent", "sent messages")
        for (n in names) all.firstOrNull { it.fullName.equals(n, true) }?.let { return it }
        return all.firstOrNull { "sent" in it.name.lowercase() }
    }
}

class SmtpSender(private val settings: Settings, private val password: String) : MailSender {
    override val label = "SMTP"
    private val session = Mime.smtpSession(settings)
    private var transport: Transport? = null
    private var imap: Store? = null

    private fun connect() {
        if (settings.smtpHost.isBlank()) throw SendException("SMTP server is not configured (Settings → Sending method).")
        if (settings.smtpFromEmail.isBlank() && settings.smtpUsername.isBlank()) {
            throw SendException("A 'From' email address is required for SMTP.")
        }
        try {
            val t = session.getTransport("smtp")
            if (settings.smtpUsername.isNotBlank()) {
                t.connect(settings.smtpHost, settings.smtpPort, settings.smtpUsername, password)
            } else t.connect()
            transport = t
        } catch (e: AuthenticationFailedException) {
            throw SendException("SMTP login failed - check the username and password (use an app password if your provider requires one).", e)
        } catch (e: MessagingException) {
            throw SendException("Could not connect to ${settings.smtpHost}:${settings.smtpPort} - ${e.message}", e)
        }
    }

    override fun open() = connect()

    override fun send(email: OutgoingEmail) {
        checkAttachments(email.attachments)
        val from = settings.smtpFromEmail.ifBlank { settings.smtpUsername }
        val msg = Mime.build(session, from, settings.smtpFromName, email)
        val all = (email.to + email.cc + email.bcc).map { InternetAddress(it) }.toTypedArray()
        for (attempt in 0..1) {
            try {
                if (transport?.isConnected != true) connect()
                transport!!.sendMessage(msg, all)
                saveToSent(msg)
                return
            } catch (e: javax.mail.SendFailedException) {
                throw SendException("Recipient refused by server: ${e.message}", e)
            } catch (e: MessagingException) {
                // Idle connections are often dropped between campaign sends; reconnect once.
                try { transport?.close() } catch (_: Exception) {}
                transport = null
                if (attempt == 1) throw SendException(e.message ?: "SMTP error", e)
            }
        }
    }

    /** With IMAP configured, keep a copy in the mailbox's Sent folder like Outlook does. */
    private fun saveToSent(msg: MimeMessage) {
        if (settings.imapHost.isBlank()) return
        try {
            val store = imap?.takeIf { it.isConnected } ?: session.getStore("imaps").also {
                it.connect(settings.imapHost, settings.imapPort, settings.smtpUsername, password)
                imap = it
            }
            val sent = Mime.findSentFolder(store) ?: return
            msg.setFlag(Flags.Flag.SEEN, true)
            sent.appendMessages(arrayOf(msg))
        } catch (_: Exception) {
            // Sending succeeded; a failed copy to Sent is not worth failing the email for.
        }
    }

    override fun close() {
        try { transport?.close() } catch (_: Exception) {}
        try { imap?.close() } catch (_: Exception) {}
        transport = null
        imap = null
    }
}
