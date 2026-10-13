package com.travelessence.emailstudio.core

import kotlinx.serialization.Serializable

@Serializable
data class Recipient(val email: String, val name: String = "") {
    val firstName: String get() = name.trim().split(Regex("\\s+")).firstOrNull().orEmpty()
    val lastName: String
        get() {
            val parts = name.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
            return if (parts.size > 1) parts.last() else ""
        }
}

@Serializable
data class Attachment(
    val name: String,
    val path: String,
    val size: Long,
    val mime: String,
)

@Serializable
data class Draft(
    val subject: String = "",
    val html: String = "",
    val attachments: List<Attachment> = emptyList(),
)

@Serializable
data class Template(
    val name: String,
    val subject: String,
    val html: String,
    val attachments: List<Attachment> = emptyList(),
    val saved: String = "",
)

@Serializable
data class SendResult(
    val email: String,
    val name: String = "",
    val status: String,          // sent | failed
    val time: String,
    val message: String = "",
)

@Serializable
data class Session(
    val id: String,
    val kind: String,            // campaign | manual
    val started: String,
    val finished: String? = null,
    val subject: String,
    val backend: String,
    val interval: Int = 0,
    val total: Int = 0,
    val sent: Int = 0,
    val failed: Int = 0,
    val status: String = "running",   // running | completed | stopped | error
    val error: String = "",
    val attachments: List<String> = emptyList(),
    val queue: List<Recipient> = emptyList(),
    val results: List<SendResult> = emptyList(),
)

@Serializable
data class Settings(
    val theme: String = "system",            // system | light | dark
    val backend: String = "microsoft",       // microsoft | smtp | simulate
    val msClientId: String = "",
    val msTenant: String = "common",
    val msAccount: String = "",
    val intervalSeconds: Int = 60,
    val nameFallback: String = "Valued Customer",
    val testEmail: String = "",
    val signatureHtml: String = "",
    val smtpHost: String = "",
    val smtpPort: Int = 587,
    val smtpSecurity: String = "starttls",   // starttls | ssl | none
    val smtpUsername: String = "",
    val smtpFromEmail: String = "",
    val smtpFromName: String = "Travel Essence",
    val imapHost: String = "",
    val imapPort: Int = 993,
    val suppressionList: String = "",
    val outlookExclude: String = "",
)

data class OutgoingEmail(
    val to: List<String>,
    val subject: String,
    val html: String,
    val attachments: List<Attachment> = emptyList(),
    val cc: List<String> = emptyList(),
    val bcc: List<String> = emptyList(),
)

class SendException(message: String, cause: Throwable? = null) : Exception(message, cause)
