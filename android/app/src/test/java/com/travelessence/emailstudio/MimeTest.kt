package com.travelessence.emailstudio

import com.travelessence.emailstudio.core.Attachment
import com.travelessence.emailstudio.core.OutgoingEmail
import com.travelessence.emailstudio.core.Settings
import com.travelessence.emailstudio.mail.Mime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.util.Base64
import javax.mail.Multipart
import javax.mail.Part

class MimeTest {
    @Test
    fun buildsRelatedAndMixedParts() {
        val pdf = Files.createTempFile("Itinerary", ".pdf").toFile().apply { writeBytes("%PDF-1.4".toByteArray()) }
        val png = Base64.getEncoder().encodeToString(byteArrayOf(9, 8, 7))
        val email = OutgoingEmail(
            to = listOf("sarah@example.com"), cc = listOf("cc@example.com"), bcc = listOf("hidden@example.com"),
            subject = "Your trip ✈", html = "<p>Hello <b>Sarah</b></p><img src=\"data:image/png;base64,$png\">",
            attachments = listOf(Attachment("Itinerary.pdf", pdf.path, pdf.length(), "application/pdf")),
        )
        val session = Mime.smtpSession(Settings(smtpHost = "localhost"))
        val msg = Mime.build(session, "info@travelessence.com", "Travel Essence", email)
        val raw = ByteArrayOutputStream().also { msg.writeTo(it) }.toString(Charsets.UTF_8)

        assertEquals("Your trip ✈", msg.subject)
        assertTrue(raw.contains("Travel Essence"))
        assertTrue(!raw.contains("hidden@example.com"))

        val mixed = msg.content as Multipart
        assertEquals(2, mixed.count)
        val attachment = mixed.getBodyPart(1)
        assertEquals(Part.ATTACHMENT, attachment.disposition)
        assertEquals("Itinerary.pdf", attachment.fileName)
        val alternative = mixed.getBodyPart(0).content as Multipart
        assertTrue(alternative.getBodyPart(0).isMimeType("text/plain"))
        val related = alternative.getBodyPart(1).content as Multipart
        val html = related.getBodyPart(0).content.toString()
        val image = related.getBodyPart(1)
        val cid = image.getHeader("Content-ID")[0].trim('<', '>')
        assertTrue(html.contains("cid:$cid"))
    }
}
