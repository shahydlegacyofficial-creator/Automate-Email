package com.travelessence.emailstudio

import com.travelessence.emailstudio.core.Attachment
import com.travelessence.emailstudio.core.OutgoingEmail
import com.travelessence.emailstudio.data.CollectOptions
import com.travelessence.emailstudio.data.GraphMailbox
import com.travelessence.emailstudio.mail.GraphClient
import com.travelessence.emailstudio.mail.TokenStore
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.BufferedInputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.URLDecoder
import java.nio.file.Files
import java.util.Base64
import java.util.concurrent.atomic.AtomicInteger
import kotlin.concurrent.thread

/** Exercises the Microsoft Graph client against a local fake of the Microsoft endpoints. */
class GraphClientTest {
    private val requests = mutableListOf<Triple<String, String, String>>()   // method, path+query, body
    private val polls = AtomicInteger()
    private var base = ""

    private class MemoryTokens : TokenStore {
        var value: String? = null
        override fun load() = value
        override fun save(value: String?) { this.value = value }
    }

    private lateinit var socket: ServerSocket
    @Volatile private var serving = true

    private fun route(method: String, path: String, body: String): Pair<Int, String> = when {
        path.endsWith("/devicecode") -> 200 to """{"device_code":"DEV","user_code":"ABC-123","verification_uri":"https://microsoft.com/devicelogin","expires_in":60,"interval":1}"""
        path.endsWith("/token") && "device_code" in body ->
            if (polls.incrementAndGet() < 2) 400 to """{"error":"authorization_pending"}"""
            else 200 to """{"access_token":"AT1","refresh_token":"RT1","expires_in":3600}"""
        path.endsWith("/token") && "refresh_token" in body -> 200 to """{"access_token":"AT2","expires_in":3600}"""
        path.startsWith("/graph/me?") -> 200 to """{"displayName":"Travel Essence","mail":"info@travelessence.com"}"""
        path == "/graph/me/sendMail" -> 202 to ""
        path == "/graph/me/messages" -> 201 to """{"id":"MSG1"}"""
        path.endsWith("/createUploadSession") -> 201 to """{"uploadUrl":"$base/upload/1"}"""
        path.startsWith("/upload/") -> 200 to "{}"
        path.endsWith("/send") -> 202 to ""
        path.startsWith("/graph/me/mailFolders/sentitems/messages") -> 200 to """{"value":[
            {"id":"m1","subject":"Travel Essence offers","sentDateTime":"2026-10-01T09:00:00Z","from":{"emailAddress":{"address":"info@travelessence.com"}},
             "toRecipients":[{"emailAddress":{"address":"Sarah@Gmail.com","name":"Sarah Khan"}}],"hasAttachments":true},
            {"id":"m2","subject":"Internal note","sentDateTime":"2026-09-30T09:00:00Z","from":{"emailAddress":{"address":"info@travelessence.com"}},
             "toRecipients":[{"emailAddress":{"address":"boss@travelessence.com","name":"Boss"}}],"hasAttachments":false}
            ]}"""
        else -> 404 to """{"error":{"code":"NotFound","message":"no route $path"}}"""
    }

    /** Minimal HTTP/1.1 server (one request per connection) - enough for HttpURLConnection. */
    private fun handle(client: Socket) = client.use { sock ->
        val input = BufferedInputStream(sock.getInputStream())
        fun readLine(): String {
            val sb = StringBuilder()
            while (true) {
                val c = input.read()
                if (c < 0 || c == '\n'.code) break
                if (c != '\r'.code) sb.append(c.toChar())
            }
            return sb.toString()
        }
        val (method, path) = readLine().split(" ").let { it[0] to it[1] }
        var length = 0
        while (true) {
            val line = readLine()
            if (line.isEmpty()) break
            if (line.lowercase().startsWith("content-length:")) length = line.substringAfter(':').trim().toInt()
        }
        val bytes = ByteArray(length)
        var read = 0
        while (read < length) { val n = input.read(bytes, read, length - read); if (n < 0) break; read += n }
        val body = String(bytes, Charsets.ISO_8859_1)
        synchronized(requests) { requests += Triple(method, path, body) }
        val (code, response) = route(method, path, body)
        val payload = response.toByteArray()
        val out = sock.getOutputStream()
        out.write(("HTTP/1.1 $code X\r\nContent-Type: application/json\r\nContent-Length: ${payload.size}\r\n" +
            "Connection: close\r\n\r\n").toByteArray())
        out.write(payload)
        out.flush()
    }

    @Before
    fun start() {
        socket = ServerSocket(0, 50, InetAddress.getByName("127.0.0.1"))
        base = "http://127.0.0.1:${socket.localPort}"
        thread(isDaemon = true) {
            while (serving) {
                val client = try { socket.accept() } catch (e: Exception) { break }
                thread(isDaemon = true) { runCatching { handle(client) } }
            }
        }
    }

    @After
    fun stop() {
        serving = false
        socket.close()
    }

    private fun client(tokens: TokenStore = MemoryTokens()) =
        GraphClient("client-id", "common", tokens, graphBase = "$base/graph", loginBase = base)

    @Test
    fun deviceLoginThenSendWithInlineImage() {
        val tokens = MemoryTokens()
        val c = client(tokens)
        val code = c.startDeviceLogin()
        assertEquals("ABC-123", code.userCode)
        assertEquals("info@travelessence.com", c.completeDeviceLogin(code) { false })
        assertTrue(c.isSignedIn)

        val png = Base64.getEncoder().encodeToString(byteArrayOf(1, 2, 3))
        c.send(OutgoingEmail(listOf("sarah@gmail.com"), "Hello", "<p>Hi</p><img src=\"data:image/png;base64,$png\">"))
        val send = requests.last { it.second == "/graph/me/sendMail" }
        val json = JSONObject(send.third)
        assertTrue(json.getBoolean("saveToSentItems"))
        val msg = json.getJSONObject("message")
        assertEquals("sarah@gmail.com", msg.getJSONArray("toRecipients").getJSONObject(0).getJSONObject("emailAddress").getString("address"))
        val att = msg.getJSONArray("attachments").getJSONObject(0)
        assertTrue(att.getBoolean("isInline"))
        assertTrue(msg.getJSONObject("body").getString("content").contains("cid:" + att.getString("contentId")))
    }

    @Test
    fun refreshesExpiredToken() {
        val tokens = MemoryTokens()
        tokens.value = JSONObject().put("access_token", "OLD").put("refresh_token", "RT1").put("expires_at", 0).toString()
        assertEquals("AT2", client(tokens).accessToken())
        assertEquals("RT1", JSONObject(tokens.value!!).getString("refresh_token"))
    }

    @Test
    fun largeAttachmentUsesUploadSession() {
        val tokens = MemoryTokens()
        tokens.value = JSONObject().put("access_token", "AT").put("refresh_token", "RT").put("expires_at", Long.MAX_VALUE).toString()
        val big = Files.createTempFile("brochure", ".pdf").toFile().apply { writeBytes(ByteArray(GraphClient.SIMPLE_ATTACHMENT_LIMIT + 10)) }
        client(tokens).send(OutgoingEmail(listOf("a@x.com"), "Brochure", "<p>Attached</p>",
            listOf(Attachment("brochure.pdf", big.path, big.length(), "application/pdf"))))
        val paths = requests.map { it.second }
        assertTrue(paths.toString(), paths.contains("/graph/me/messages"))
        assertTrue(paths.any { it.endsWith("/createUploadSession") })
        val uploaded = requests.filter { it.second.startsWith("/upload/") }.sumOf { it.third.toByteArray(Charsets.ISO_8859_1).size }
        assertTrue(paths.last().endsWith("/send"))
        assertTrue(uploaded > 0)
    }

    @Test
    fun collectsCustomersFromSentItems() {
        val tokens = MemoryTokens()
        tokens.value = JSONObject().put("access_token", "AT").put("refresh_token", "RT").put("expires_at", Long.MAX_VALUE).toString()
        val result = GraphMailbox.collect(client(tokens), CollectOptions(folder = "sent", exclude = listOf("@travelessence.com")), { _, _, _ -> }) { false }
        assertEquals(2, result.messages.size)
        assertEquals(listOf("sarah@gmail.com" to "Sarah Khan"), result.contacts.map { it.email to it.name })
        val query = URLDecoder.decode(requests.first { it.second.contains("mailFolders") }.second, "UTF-8")
        assertTrue(query, query.contains("sentDateTime ge"))
    }
}
