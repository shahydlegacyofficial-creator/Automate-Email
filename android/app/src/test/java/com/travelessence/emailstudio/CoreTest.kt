package com.travelessence.emailstudio

import com.travelessence.emailstudio.core.Csv
import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.core.Recipient
import com.travelessence.emailstudio.core.Recipients
import com.travelessence.emailstudio.core.Xlsx
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Base64

class CoreTest {
    @Test
    fun parsesMixedText() {
        val r = Recipients.parseText(
            """
            Sarah Khan <Sarah.Khan@Gmail.com>
            john@outlook.com, John Smith
            maria@hotmail.com; leo@icloud.com
            "Ali Raza" <ali.raza@yahoo.com>
            sarah.khan@gmail.com
            not-an-email
            broken@domain
            """.trimIndent()
        )
        assertEquals(
            listOf("sarah.khan@gmail.com", "john@outlook.com", "maria@hotmail.com", "leo@icloud.com", "ali.raza@yahoo.com"),
            r.recipients.map { it.email },
        )
        val names = r.recipients.associate { it.email to it.name }
        assertEquals("Sarah Khan", names["sarah.khan@gmail.com"])
        assertEquals("John Smith", names["john@outlook.com"])
        assertEquals("Ali Raza", names["ali.raza@yahoo.com"])
        assertEquals("", names["maria@hotmail.com"])
        assertEquals(1, r.duplicates)
        assertTrue("broken@domain" in r.invalid)
    }

    @Test
    fun validation() {
        assertTrue(Recipients.isValid("a.b+tag@sub.example.co.uk"))
        assertFalse(Recipients.isValid("a..b@example.com"))
        assertFalse(Recipients.isValid(".a@example.com"))
        assertFalse(Recipients.isValid("a@example"))
        assertFalse(Recipients.isValid("a@-example.com"))
    }

    @Test
    fun csvWithHeaders() {
        val rows = Csv.parse("First Name;Last Name;E-mail;Phone\nSarah;Khan;sarah@x.com;123\nJohn;;JOHN@x.com;456\n;;bad@;0\n")
        val r = Recipients.parseRows(rows)
        assertEquals(listOf("sarah@x.com" to "Sarah Khan", "john@x.com" to "John"), r.recipients.map { it.email to it.name })
    }

    @Test
    fun csvQuotesAndRoundTrip() {
        val text = Csv.write(listOf(listOf("Email", "Name"), listOf("a@x.com", "Smith, \"Jo\"")))
        val rows = Csv.parse(text)
        assertEquals(listOf("a@x.com", "Smith, \"Jo\""), rows[1])
    }

    @Test
    fun xlsxRoundTrip() {
        val bytes = Xlsx.write(listOf(listOf("Customer Name", "Email Address"), listOf("Leo Messi", "leo@example.com"), listOf("", "maria@example.com")))
        val sheets = Xlsx.read(bytes)
        val r = Recipients.parseRows(sheets[0])
        assertEquals(listOf("leo@example.com" to "Leo Messi", "maria@example.com" to ""), r.recipients.map { it.email to it.name })
    }

    @Test
    fun mergeAndSuppression() {
        val (merged, added, dupes) = Recipients.merge(listOf(Recipient("a@x.com")), listOf(Recipient("a@x.com", "Ann"), Recipient("b@x.com")))
        assertEquals(1, added); assertEquals(1, dupes); assertEquals("Ann", merged[0].name)
        val entries = Recipients.parseSuppression("stop@x.com\n@competitor.com, other.org")
        assertTrue(Recipients.isSuppressed("STOP@x.com", entries))
        assertTrue(Recipients.isSuppressed("anyone@competitor.com", entries))
        assertTrue(Recipients.isSuppressed("me@other.org", entries))
        assertFalse(Recipients.isSuppressed("ok@x.com", entries))
    }

    @Test
    fun personalizeAndFallback() {
        val r = Recipient("sarah@x.com", "Sarah <Khan>")
        assertEquals("Hi Sarah / Sarah <Khan> / sarah@x.com", Html.personalize("Hi {first_name} / { NAME } / {email}", r))
        assertEquals("<p>Sarah &lt;Khan&gt;</p>", Html.personalize("<p>{name}</p>", r, isHtml = true))
        assertEquals("Dear Valued Customer,", Html.personalize("Dear {first_name},", Recipient("x@y.com"), "Valued Customer"))
    }

    @Test
    fun inlineImagesBecomeCid() {
        val png = Base64.getEncoder().encodeToString(byteArrayOf(1, 2, 3, 4))
        val html = "<p><img src=\"data:image/png;base64,$png\" style=\"max-width:100%\"></p><img src=\"data:image/png;base64,$png\"><img src='https://x.com/a.png'>"
        val (out, images) = Html.extractInlineImages(html)
        assertEquals(1, images.size)
        assertTrue(out.contains("src=\"cid:${images[0].cid}\""))
        assertTrue(out.contains("src='https://x.com/a.png'"))
        assertEquals(listOf<Byte>(1, 2, 3, 4), images[0].bytes.toList())
        val back = Html.inlineCids(out, mapOf(images[0].cid to ("image/png" to images[0].bytes)))
        assertTrue(back.contains("data:image/png;base64,$png"))
    }

    @Test
    fun textFallbackAndBlank() {
        assertEquals("Hello site (https://te.com)\n\n - One", Html.toText("<p>Hello <a href='https://te.com'>site</a></p><ul><li>One</li></ul>"))
        assertTrue(Html.isBlank("<p><br></p>"))
        assertFalse(Html.isBlank("<p><img src=\"x.png\"></p>"))
        val doc = Html.buildEmail("<p>Hi</p>", "<b>Travel Essence</b>")
        assertTrue(doc.indexOf("<p>Hi</p>") < doc.indexOf("Travel Essence"))
    }
}
