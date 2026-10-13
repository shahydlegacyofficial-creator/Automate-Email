package com.travelessence.emailstudio.mail

import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.core.OutgoingEmail
import com.travelessence.emailstudio.core.SendException
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.Base64

/** Persists the OAuth tokens (encrypted on Android). */
interface TokenStore {
    fun load(): String?
    fun save(value: String?)
}

data class DeviceCode(
    val deviceCode: String,
    val userCode: String,
    val verificationUri: String,
    val expiresIn: Int,
    val interval: Int,
    val message: String,
)

/**
 * Microsoft Graph access for Microsoft 365 work/school mailboxes and Outlook.com accounts.
 *
 * Sign-in uses the OAuth 2.0 device-code flow, so no redirect handling is needed: the app shows
 * a short code, the user enters it at microsoft.com/devicelogin and approves access.
 */
class GraphClient(
    private val clientId: String,
    private val tenant: String,
    private val tokens: TokenStore,
    private val graphBase: String = "https://graph.microsoft.com/v1.0",
    private val loginBase: String = "https://login.microsoftonline.com",
) {
    companion object {
        const val SCOPES = "offline_access User.Read Mail.ReadWrite Mail.Send Contacts.Read"
        const val SIMPLE_ATTACHMENT_LIMIT = 3 * 1024 * 1024
        private const val UPLOAD_CHUNK = 320 * 1024 * 10

        fun encode(s: String): String = URLEncoder.encode(s, "UTF-8").replace("+", "%20")
    }

    private val authority get() = "$loginBase/${tenant.ifBlank { "common" }}/oauth2/v2.0"

    class HttpResult(val code: Int, val body: String, val headers: Map<String, List<String>>)

    private fun http(
        method: String,
        url: String,
        body: ByteArray? = null,
        contentType: String? = null,
        headers: Map<String, String> = emptyMap(),
    ): HttpResult {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = 30_000
            conn.readTimeout = 120_000
            headers.forEach { (k, v) -> conn.setRequestProperty(k, v) }
            if (body != null) {
                conn.doOutput = true
                if (contentType != null) conn.setRequestProperty("Content-Type", contentType)
                conn.setFixedLengthStreamingMode(body.size)
                conn.outputStream.use { it.write(body) }
            }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
            return HttpResult(code, text, conn.headerFields.filterKeys { it != null })
        } catch (e: IOException) {
            throw SendException("Network error: ${e.message ?: e.javaClass.simpleName}", e)
        } finally {
            conn.disconnect()
        }
    }

    private fun form(vararg pairs: Pair<String, String>): ByteArray =
        pairs.joinToString("&") { "${encode(it.first)}=${encode(it.second)}" }.toByteArray()

    // ------------------------------------------------------------------ auth
    fun startDeviceLogin(): DeviceCode {
        if (clientId.isBlank()) throw SendException("Enter the Application (client) ID in Settings first.")
        val r = http("POST", "$authority/devicecode", form("client_id" to clientId, "scope" to SCOPES),
            "application/x-www-form-urlencoded")
        val json = parseJson(r.body)
        if (r.code != 200) throw SendException(authError(json, r.code))
        return DeviceCode(
            json.getString("device_code"), json.getString("user_code"),
            json.optString("verification_uri", "https://microsoft.com/devicelogin"),
            json.optInt("expires_in", 900), json.optInt("interval", 5), json.optString("message"),
        )
    }

    /** Polls until the user approves. Returns the signed-in account address. */
    fun completeDeviceLogin(code: DeviceCode, cancelled: () -> Boolean): String {
        var interval = code.interval.coerceAtLeast(2)
        val deadline = System.currentTimeMillis() + code.expiresIn * 1000L
        while (System.currentTimeMillis() < deadline) {
            if (cancelled()) throw SendException("Sign-in cancelled")
            Thread.sleep(interval * 1000L)
            val r = http("POST", "$authority/token", form(
                "grant_type" to "urn:ietf:params:oauth:grant-type:device_code",
                "client_id" to clientId,
                "device_code" to code.deviceCode,
            ), "application/x-www-form-urlencoded")
            val json = parseJson(r.body)
            if (r.code == 200) {
                storeTokens(json)
                return me()
            }
            when (json.optString("error")) {
                "authorization_pending" -> continue
                "slow_down" -> interval += 5
                else -> throw SendException(authError(json, r.code))
            }
        }
        throw SendException("The sign-in code expired. Please try again.")
    }

    private fun storeTokens(json: JSONObject, previousRefresh: String? = null) {
        val saved = JSONObject()
        saved.put("access_token", json.getString("access_token"))
        saved.put("refresh_token", json.optString("refresh_token", previousRefresh ?: ""))
        saved.put("expires_at", System.currentTimeMillis() + (json.optLong("expires_in", 3600) - 120) * 1000)
        tokens.save(saved.toString())
    }

    val isSignedIn: Boolean get() = tokens.load()?.let { runCatching { JSONObject(it).optString("refresh_token").isNotEmpty() }.getOrDefault(false) } == true

    fun signOut() = tokens.save(null)

    @Synchronized
    fun accessToken(): String {
        val raw = tokens.load() ?: throw SendException("Not signed in to Microsoft 365 / Outlook. Sign in from Settings.")
        val saved = JSONObject(raw)
        if (System.currentTimeMillis() < saved.optLong("expires_at")) return saved.getString("access_token")
        val refresh = saved.optString("refresh_token")
        if (refresh.isEmpty()) throw SendException("Your Microsoft sign-in has expired. Sign in again from Settings.")
        val r = http("POST", "$authority/token", form(
            "grant_type" to "refresh_token", "client_id" to clientId, "refresh_token" to refresh, "scope" to SCOPES,
        ), "application/x-www-form-urlencoded")
        val json = parseJson(r.body)
        if (r.code != 200) throw SendException("Your Microsoft sign-in has expired (${authError(json, r.code)}). Sign in again from Settings.")
        storeTokens(json, refresh)
        return json.getString("access_token")
    }

    // ------------------------------------------------------------------ REST
    fun request(method: String, pathOrUrl: String, json: JSONObject? = null): JSONObject {
        val url = if (pathOrUrl.startsWith("http")) pathOrUrl else graphBase + pathOrUrl
        for (attempt in 0..2) {
            val r = http(method, url, json?.toString()?.toByteArray(), if (json != null) "application/json" else null,
                mapOf("Authorization" to "Bearer ${accessToken()}", "Accept" to "application/json"))
            if ((r.code == 429 || r.code == 503 || r.code == 504) && attempt < 2) {
                val wait = r.headers["Retry-After"]?.firstOrNull()?.toLongOrNull() ?: (5L * (attempt + 1))
                Thread.sleep(wait.coerceIn(1, 60) * 1000)
                continue
            }
            if (r.code !in 200..299) throw SendException(graphError(r))
            return if (r.body.isBlank()) JSONObject() else parseJson(r.body)
        }
        throw SendException("Microsoft Graph is busy - try again later.")
    }

    fun me(): String {
        val me = request("GET", "/me?\$select=displayName,mail,userPrincipalName")
        return me.optString("mail").takeIf { it.isNotBlank() && it != "null" } ?: me.optString("userPrincipalName")
    }

    // ------------------------------------------------------------------ sending
    private fun recipients(list: List<String>) = JSONArray().apply {
        list.forEach { put(JSONObject().put("emailAddress", JSONObject().put("address", it))) }
    }

    fun send(email: OutgoingEmail) {
        checkAttachments(email.attachments)
        val (html, images) = Html.extractInlineImages(email.html)
        val message = JSONObject()
            .put("subject", email.subject)
            .put("body", JSONObject().put("contentType", "HTML").put("content", html))
            .put("toRecipients", recipients(email.to))
        if (email.cc.isNotEmpty()) message.put("ccRecipients", recipients(email.cc))
        if (email.bcc.isNotEmpty()) message.put("bccRecipients", recipients(email.bcc))

        val small = JSONArray()
        images.forEach { img ->
            small.put(JSONObject()
                .put("@odata.type", "#microsoft.graph.fileAttachment")
                .put("name", img.fileName).put("contentType", img.mime)
                .put("contentBytes", Base64.getEncoder().encodeToString(img.bytes))
                .put("isInline", true).put("contentId", img.cid))
        }
        val large = email.attachments.filter { File(it.path).length() > SIMPLE_ATTACHMENT_LIMIT }
        email.attachments.filter { it !in large }.forEach { a ->
            small.put(JSONObject()
                .put("@odata.type", "#microsoft.graph.fileAttachment")
                .put("name", a.name).put("contentType", a.mime)
                .put("contentBytes", Base64.getEncoder().encodeToString(File(a.path).readBytes())))
        }
        if (small.length() > 0) message.put("attachments", small)

        if (large.isEmpty()) {
            request("POST", "/me/sendMail", JSONObject().put("message", message).put("saveToSentItems", true))
            return
        }
        // Large files: create a draft, stream each file through an upload session, then send it.
        val draft = request("POST", "/me/messages", message)
        val id = draft.getString("id")
        try {
            for (a in large) upload(id, File(a.path), a.name, a.mime)
            request("POST", "/me/messages/${encode(id)}/send")
        } catch (e: Exception) {
            runCatching { request("DELETE", "/me/messages/${encode(id)}") }
            throw e
        }
    }

    private fun upload(messageId: String, file: File, name: String, mime: String) {
        val size = file.length()
        val session = request("POST", "/me/messages/${encode(messageId)}/attachments/createUploadSession",
            JSONObject().put("AttachmentItem", JSONObject()
                .put("attachmentType", "file").put("name", name).put("size", size).put("contentType", mime)))
        val uploadUrl = session.getString("uploadUrl")
        file.inputStream().use { input ->
            var offset = 0L
            val buffer = ByteArray(UPLOAD_CHUNK)
            while (offset < size) {
                val read = input.readNBytesCompat(buffer)
                if (read <= 0) break
                val chunk = if (read == buffer.size) buffer else buffer.copyOf(read)
                val r = http("PUT", uploadUrl, chunk, "application/octet-stream",
                    mapOf("Content-Range" to "bytes $offset-${offset + read - 1}/$size"))
                if (r.code !in 200..299) throw SendException("Uploading $name failed: ${graphError(r)}")
                offset += read
            }
        }
    }

    // ------------------------------------------------------------------ errors
    private fun parseJson(body: String): JSONObject = try {
        if (body.isBlank()) JSONObject() else JSONObject(body)
    } catch (e: Exception) {
        JSONObject().put("error_description", body.take(300))
    }

    private fun authError(json: JSONObject, code: Int): String {
        val desc = json.optString("error_description").lineSequence().firstOrNull().orEmpty()
        return when {
            "AADSTS7000218" in desc -> "Public client flows are not enabled for this app registration (Authentication → Allow public client flows = Yes)."
            "AADSTS700016" in desc -> "Application (client) ID not found. Check it in Settings."
            json.optString("error") == "access_denied" -> "Sign-in was declined."
            desc.isNotBlank() -> desc
            else -> "Sign-in failed (HTTP $code)"
        }
    }

    private fun graphError(r: HttpResult): String {
        val err = runCatching { JSONObject(r.body).getJSONObject("error") }.getOrNull()
        val message = err?.optString("message").orEmpty()
        return when {
            r.code == 401 -> "Microsoft rejected the sign-in ($message). Sign in again from Settings."
            r.code == 403 -> "Access denied - the account may not have a mailbox or permission ($message)."
            message.isNotBlank() -> message
            else -> "Microsoft Graph error HTTP ${r.code}"
        }
    }
}

private fun java.io.InputStream.readNBytesCompat(buffer: ByteArray): Int {
    var total = 0
    while (total < buffer.size) {
        val n = read(buffer, total, buffer.size - total)
        if (n < 0) break
        total += n
    }
    return total
}

class GraphSender(private val client: GraphClient) : MailSender {
    override val label = "Microsoft 365 / Outlook"
    override fun open() {
        client.accessToken()  // fail fast if the sign-in has expired
    }
    override fun send(email: OutgoingEmail) = client.send(email)
}
