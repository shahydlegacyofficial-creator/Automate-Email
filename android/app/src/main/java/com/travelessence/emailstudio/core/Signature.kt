package com.travelessence.emailstudio.core

import kotlinx.serialization.Serializable
import java.net.URLEncoder

/**
 * Branded email signature - a line-for-line port of the desktop app's `core/signature.py`,
 * so both apps produce the same email-safe HTML (tables, inline styles, PNG icons).
 */
@Serializable
data class SignatureConfig(
    val enabled: Boolean = true,
    val theme: String = "dark",                 // dark | light
    val accent: String = "#1E88E5",
    val name: String = "",
    val title: String = "",
    val email: String = "sales.marketing@travelessence.mv",
    val phone: String = "+960 7978580",
    val address: String = "H.Finivairoalhi, 2nd Floor\nRaivilla Magu, Henveiru",
    val website: String = "travelessence.mv",
    val logoPath: String = "",
    val logoWidth: Int = 200,
    val socials: Map<String, String> = emptyMap(),
)

object Signature {
    /** key, label, prefix used when only a handle / number is entered. */
    val SOCIALS = listOf(
        Triple("facebook", "Facebook", "https://www.facebook.com/"),
        Triple("instagram", "Instagram", "https://www.instagram.com/"),
        Triple("whatsapp", "WhatsApp", "https://wa.me/"),
        Triple("tiktok", "TikTok", "https://www.tiktok.com/@"),
        Triple("linkedin", "LinkedIn", "https://www.linkedin.com/company/"),
        Triple("youtube", "YouTube", "https://www.youtube.com/@"),
        Triple("x", "X (Twitter)", "https://x.com/"),
    )

    private data class Colors(val background: String, val text: String, val strong: String)
    private val THEMES = mapOf(
        "dark" to Colors("#2B2B2B", "#BDBDBD", "#FFFFFF"),
        "light" to Colors("#FFFFFF", "#4B5563", "#111827"),
    )

    private val HTTP = Regex("^https?://", RegexOption.IGNORE_CASE)

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8").replace("+", "%20")
    private fun e(s: String) = Html.escape(s).replace("'", "&#x27;")

    fun socialUrl(platform: String, raw: String): String {
        val value = raw.trim()
        if (value.isEmpty()) return ""
        if (HTTP.containsMatchIn(value)) return value
        if (Regex("^(www\\.)?[\\w-]+\\.[a-z]{2,}/", RegexOption.IGNORE_CASE).containsMatchIn(value)) return "https://$value"
        val prefix = SOCIALS.firstOrNull { it.first == platform }?.third ?: "https://"
        if (platform == "whatsapp") {
            val digits = value.filter { it.isDigit() }
            return if (digits.isEmpty()) "" else prefix + digits
        }
        return prefix + enc(value.trimStart('@').trim('/'))
    }

    fun websiteUrl(raw: String): String {
        val value = raw.trim()
        if (value.isEmpty()) return ""
        return if (HTTP.containsMatchIn(value)) value else "https://$value"
    }

    /** [iconSrc] (kind = "contact" | "social", name) returns the image source for an icon. */
    fun build(cfg: SignatureConfig, iconSrc: (String, String) -> String, logoSrc: String = ""): String {
        val c = THEMES[cfg.theme] ?: THEMES.getValue("dark")
        val accent = cfg.accent.ifBlank { "#1E88E5" }
        val font = "font-family:Arial,Helvetica,sans-serif;"
        val textStyle = "${font}font-size:14px;line-height:20px;color:${c.text};"
        val linkStyle = "color:${c.text};text-decoration:none;"
        val rows = StringBuilder()

        fun row(icon: String, content: String) {
            rows.append("<tr><td width=\"30\" valign=\"top\" style=\"padding:4px 0;\">")
                .append("<img src=\"${e(iconSrc("contact", icon))}\" width=\"20\" height=\"20\" alt=\"\" ")
                .append("style=\"display:block;border:0;width:20px;height:20px;\"></td>")
                .append("<td valign=\"top\" style=\"padding:4px 0 4px 6px;$textStyle\">$content</td></tr>")
        }

        if (cfg.name.isNotBlank() || cfg.title.isNotBlank()) {
            val title = if (cfg.title.isNotBlank()) "<br><span style=\"$textStyle\">${e(cfg.title.trim())}</span>" else ""
            rows.append("<tr><td colspan=\"2\" style=\"padding:0 0 8px 0;\">")
                .append("<span style=\"${font}font-size:16px;font-weight:bold;color:${c.strong};\">${e(cfg.name.trim())}</span>")
                .append(title).append("</td></tr>")
        }
        cfg.email.trim().takeIf { it.isNotEmpty() }?.let {
            row("email", "<a href=\"mailto:${e(it)}\" style=\"$linkStyle\">${e(it)}</a>")
        }
        cfg.phone.trim().takeIf { it.isNotEmpty() }?.let {
            val tel = it.filter { ch -> ch.isDigit() || ch == '+' }
            row("phone", "<a href=\"tel:${e(tel)}\" style=\"$linkStyle\">${e(it)}</a>")
        }
        val lines = cfg.address.lines().map { it.trim() }.filter { it.isNotEmpty() }
        if (lines.isNotEmpty()) {
            val maps = "https://www.google.com/maps/search/?api=1&query=" + enc(lines.joinToString(", "))
            row("address", "<a href=\"${e(maps)}\" style=\"$linkStyle\">${lines.joinToString("<br>") { e(it) }}</a>")
        }
        val site = websiteUrl(cfg.website)
        if (site.isNotEmpty()) {
            val shown = site.replace(HTTP, "").trimEnd('/')
            row("website", "<a href=\"${e(site)}\" style=\"color:$accent;font-weight:bold;text-decoration:none;\">${e(shown)}</a>")
        }

        val icons = SOCIALS.mapNotNull { (key, label, _) ->
            val url = socialUrl(key, cfg.socials[key].orEmpty())
            if (url.isEmpty()) null
            else "<a href=\"${e(url)}\" title=\"${e(label)}\" style=\"text-decoration:none;\">" +
                "<img src=\"${e(iconSrc("social", key))}\" width=\"28\" height=\"28\" alt=\"${e(label)}\" " +
                "style=\"border:0;width:28px;height:28px;\"></a>"
        }
        if (icons.isNotEmpty()) {
            rows.append("<tr><td colspan=\"2\" style=\"padding:12px 0 0 0;\">${icons.joinToString("&nbsp;&nbsp;")}</td></tr>")
        }
        if (logoSrc.isNotEmpty()) {
            val width = cfg.logoWidth.coerceIn(80, 360)
            var logo = "<img src=\"${e(logoSrc)}\" width=\"$width\" alt=\"Logo\" style=\"display:block;border:0;width:${width}px;height:auto;\">"
            if (site.isNotEmpty()) logo = "<a href=\"${e(site)}\" style=\"text-decoration:none;\">$logo</a>"
            rows.append("<tr><td colspan=\"2\" style=\"padding:18px 0 0 0;\">$logo</td></tr>")
        }
        if (rows.isEmpty()) return ""
        return "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" " +
            "style=\"border-collapse:collapse;background-color:${c.background};\">" +
            "<tr><td bgcolor=\"${c.background}\" style=\"padding:18px 22px;\">" +
            "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"border-collapse:collapse;\">" +
            "$rows</table></td></tr></table>"
    }
}
