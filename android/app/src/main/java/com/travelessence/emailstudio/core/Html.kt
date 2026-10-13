package com.travelessence.emailstudio.core

import java.security.MessageDigest
import java.util.Base64

data class InlineImage(val cid: String, val mime: String, val bytes: ByteArray) {
    val fileName: String get() = cid
}

object Html {
    val PLACEHOLDERS = linkedMapOf(
        "first_name" to "First name",
        "last_name" to "Last name",
        "name" to "Full name",
        "email" to "Email address",
    )
    private val PLACEHOLDER = Regex("\\{\\s*(first_name|last_name|name|email)\\s*\\}", RegexOption.IGNORE_CASE)
    private val BODY = Regex("<body([^>]*)>(.*)</body>", setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL))
    private val DATA_IMG = Regex(
        "(<img\\b[^>]*?\\bsrc\\s*=\\s*)([\"'])data:(image/[A-Za-z0-9+.\\-]+);base64,([A-Za-z0-9+/=\\s]+)\\2",
        RegexOption.IGNORE_CASE,
    )
    const val BASE_STYLE = "font-family:Calibri,Arial,Helvetica,sans-serif;font-size:11pt;color:#1F2937;line-height:1.45;"

    fun escape(s: String): String = s
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")

    fun personalize(text: String, r: Recipient, fallback: String = "", isHtml: Boolean = false): String {
        val values = mapOf(
            "first_name" to r.firstName.ifEmpty { fallback },
            "last_name" to r.lastName,
            "name" to r.name.ifEmpty { fallback },
            "email" to r.email,
        )
        return PLACEHOLDER.replace(text) { m ->
            val v = values.getValue(m.groupValues[1].lowercase())
            if (isHtml) escape(v) else v
        }
    }

    /** Returns the inner HTML of <body> (or the input when it is already a fragment). */
    fun bodyInner(document: String): String = BODY.find(document)?.groupValues?.get(2) ?: document

    /** Wraps editor content (an HTML fragment) into a complete email document. */
    fun buildEmail(fragment: String, signatureHtml: String = ""): String {
        val signature = if (signatureHtml.isNotBlank()) "<br>$signatureHtml" else ""
        return "<!DOCTYPE html>\n<html><head><meta http-equiv=\"Content-Type\" content=\"text/html; charset=utf-8\">" +
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"></head>\n" +
            "<body><div style=\"$BASE_STYLE\">${bodyInner(fragment)}$signature</div></body></html>"
    }

    /** Replaces embedded data: images with cid: references; returns the new HTML and the images. */
    fun extractInlineImages(document: String): Pair<String, List<InlineImage>> {
        val images = linkedMapOf<String, InlineImage>()
        val out = DATA_IMG.replace(document) { m ->
            val mime = m.groupValues[3].lowercase()
            val bytes = try {
                Base64.getMimeDecoder().decode(m.groupValues[4])
            } catch (e: IllegalArgumentException) {
                return@replace m.value
            }
            val digest = MessageDigest.getInstance("SHA-1").digest(bytes).joinToString("") { "%02x".format(it) }.take(12)
            val ext = when (mime) {
                "image/jpeg", "image/jpg" -> "jpg"
                "image/gif" -> "gif"
                "image/webp" -> "webp"
                else -> "png"
            }
            val cid = "te-img-$digest.$ext"
            images.getOrPut(cid) { InlineImage(cid, mime, bytes) }
            "${m.groupValues[1]}${m.groupValues[2]}cid:$cid${m.groupValues[2]}"
        }
        return out to images.values.toList()
    }

    /** Turns cid: references into data: URIs so an email loaded from the mailbox shows its pictures. */
    fun inlineCids(document: String, images: Map<String, Pair<String, ByteArray>>): String {
        var out = document
        for ((cid, value) in images) {
            val (mime, bytes) = value
            val uri = "data:$mime;base64," + Base64.getEncoder().encodeToString(bytes)
            out = out.replace(Regex("cid:" + Regex.escape(cid), RegexOption.IGNORE_CASE), uri)
        }
        return out.replace(Regex("<img\\b[^>]*\\bsrc\\s*=\\s*[\"']cid:[^\"']*[\"'][^>]*>", RegexOption.IGNORE_CASE), "")
    }

    fun toText(document: String): String {
        var s = document
        s = s.replace(Regex("<(style|script|head)[^>]*>.*?</\\1>", setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL)), "")
        s = s.replace(Regex("<a\\b[^>]*href\\s*=\\s*[\"'](https?://[^\"']+)[\"'][^>]*>(.*?)</a>", setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL)), "$2 ($1)")
        s = s.replace(Regex("<li\\b[^>]*>", RegexOption.IGNORE_CASE), "\n - ")
        s = s.replace(Regex("<br\\s*/?>", RegexOption.IGNORE_CASE), "\n")
        s = s.replace(Regex("</?(p|div|h[1-6]|tr|table|ul|ol)\\b[^>]*>", RegexOption.IGNORE_CASE), "\n")
        s = s.replace(Regex("<[^>]+>"), "")
        s = Xlsx.unescape(s).replace("&nbsp;", " ").replace('\u00A0', ' ')
        s = s.replace(Regex("[ \\t]+\\n"), "\n").replace(Regex("\\n{3,}"), "\n\n")
        return s.trim()
    }

    fun isBlank(document: String): Boolean =
        !Regex("<img\\b", RegexOption.IGNORE_CASE).containsMatchIn(document) && toText(document).isBlank()
}
