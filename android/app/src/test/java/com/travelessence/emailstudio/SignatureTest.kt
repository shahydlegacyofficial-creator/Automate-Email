package com.travelessence.emailstudio

import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.core.Signature
import com.travelessence.emailstudio.core.SignatureConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Mirrors tests/test_signature.py so both apps produce the same signature. */
class SignatureTest {
    private val icons: (String, String) -> String = { kind, name -> "https://icons.test/$kind/$name.png" }
    private val sample = SignatureConfig(email = "sales.marketing@travelessence.mv", phone = "+960 7978580",
        address = "H.Finivairoalhi, 2nd Floor\nRaivilla Magu, Henveiru", website = "travelessence.mv")

    @Test
    fun aNewUsersBlankSignatureAddsNothing() {
        assertEquals("", Signature.build(SignatureConfig(), icons))
    }

    @Test
    fun contactDetailsBecomeLinks() {
        val html = Signature.build(sample, icons)
        assertTrue(html.contains("href=\"mailto:sales.marketing@travelessence.mv\""))
        assertTrue(html.contains("href=\"tel:+9607978580\""))
        assertTrue(html.contains("H.Finivairoalhi, 2nd Floor<br>Raivilla Magu, Henveiru"))
        assertTrue(html.contains("href=\"https://travelessence.mv\"") && html.contains(">travelessence.mv</a>"))
        assertTrue(html.contains("background-color:#2B2B2B"))
        assertFalse(html.contains("/social/"))
    }

    @Test
    fun socialUrls() {
        assertEquals("https://www.facebook.com/travelessence", Signature.socialUrl("facebook", "travelessence"))
        assertEquals("https://www.instagram.com/travel.essence", Signature.socialUrl("instagram", "@travel.essence"))
        assertEquals("https://wa.me/9607978580", Signature.socialUrl("whatsapp", "+960 797-8580"))
        assertEquals("https://www.tiktok.com/@travelessence", Signature.socialUrl("tiktok", "@travelessence"))
        assertEquals("https://www.linkedin.com/company/te", Signature.socialUrl("linkedin", "https://www.linkedin.com/company/te"))
        assertEquals("https://x.com/travelessence", Signature.socialUrl("x", "x.com/travelessence"))
        assertEquals("", Signature.socialUrl("youtube", ""))
    }

    @Test
    fun hiddenFieldsSocialsLogoAndEscaping() {
        val cfg = sample.copy(phone = "", address = "", name = "Aisha <Sales>", theme = "light", accent = "#0B7A8F",
            socials = mapOf("instagram" to "@travelessence", "whatsapp" to "+960 7978580"))
        val html = Signature.build(cfg, icons, "https://icons.test/logo.png")
        assertFalse(html.contains("tel:") || html.contains("maps"))
        assertTrue(html.contains("Aisha &lt;Sales&gt;"))
        assertTrue(html.indexOf("/social/instagram.png") < html.indexOf("/social/whatsapp.png"))
        assertTrue(html.contains("href=\"https://wa.me/9607978580\""))
        assertTrue(html.contains("src=\"https://icons.test/logo.png\"") && html.contains("width=\"200\""))
        assertTrue(html.contains("color:#0B7A8F") && html.contains("background-color:#FFFFFF"))
    }

    @Test
    fun signatureFollowsMessageAndImagesBecomeInline() {
        val png = java.util.Base64.getEncoder().encodeToString(byteArrayOf(1, 2, 3))
        val doc = Html.buildEmail("<p>Hello</p>", Signature.build(sample, { _, _ -> "data:image/png;base64,$png" }))
        assertTrue(doc.indexOf("Hello") < doc.indexOf("sales.marketing@travelessence.mv"))
        val (rewritten, images) = Html.extractInlineImages(doc)
        assertEquals(1, images.size)
        assertFalse(rewritten.contains("data:image"))
    }
}
