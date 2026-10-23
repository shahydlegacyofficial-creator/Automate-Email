package com.travelessence.emailstudio.agent.protocol

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketException
import java.net.URI
import java.security.MessageDigest
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Streamable HTTP for MCP, answered as plain JSON (no SSE, no sessions) - small enough to need no
 * library. POST /mcp only. Every request must carry `Authorization: Bearer <token>`; the Host must be
 * this device (DNS-rebinding protection) and browser requests from other sites are refused.
 *
 * @param lan false = only apps on this phone can connect (127.0.0.1); true = devices on the same Wi-Fi too.
 * @param localHosts the names/addresses this device answers to on the network (checked against Host).
 */
class McpHttpServer(
    private val dispatcher: McpDispatcher,
    private val token: String,
    private val port: Int = 8765,
    private val lan: Boolean = false,
    private val localHosts: () -> Set<String> = { emptySet() },
) {
    companion object {
        const val ENDPOINT = "/mcp"
        const val MAX_BODY = 2 * 1024 * 1024
        private const val MAX_HEADER = 32 * 1024
        private val LOOPBACK = setOf("127.0.0.1", "localhost", "::1", "[::1]")
    }

    private var socket: ServerSocket? = null
    private var pool: ExecutorService? = null
    private var acceptThread: Thread? = null

    val boundPort: Int get() = socket?.localPort ?: port
    val running: Boolean get() = socket?.isClosed == false

    init { require(token.isNotEmpty()) { "A token is required" } }

    /** Bind and serve in the background. Throws (e.g. BindException) when the port is taken. */
    fun start() {
        if (running) return
        val server = ServerSocket()
        server.reuseAddress = true
        val address = if (lan) InetAddress.getByName("0.0.0.0") else InetAddress.getLoopbackAddress()
        server.bind(InetSocketAddress(address, port), 16)
        socket = server
        pool = Executors.newFixedThreadPool(6) { r -> Thread(r, "mcp-http").apply { isDaemon = true } }
        acceptThread = Thread({
            while (!server.isClosed) {
                val client = try { server.accept() } catch (_: SocketException) { break } catch (_: Exception) { continue }
                pool?.execute { serve(client) } ?: client.close()
            }
        }, "mcp-accept").apply { isDaemon = true; start() }
    }

    fun stop() {
        try { socket?.close() } catch (_: Exception) { }
        socket = null
        pool?.shutdownNow()
        pool?.awaitTermination(2, TimeUnit.SECONDS)
        pool = null
        acceptThread = null
    }

    // ------------------------------------------------------------------ one connection
    private class Request(val method: String, val path: String, val headers: Map<String, String>, val body: ByteArray)

    private fun serve(client: Socket) {
        client.use { s ->
            s.soTimeout = 30_000
            val input = BufferedInputStream(s.getInputStream())
            val output = s.getOutputStream()
            val request = try { read(input) } catch (_: Exception) { null }
            if (request == null) {
                respond(output, 400, buildJsonObject { put("error", "Bad request") })
                return
            }
            try {
                route(request, output)
            } catch (e: Exception) {
                respond(output, 500, McpDispatcher.error(JsonNull, Mcp.INTERNAL_ERROR, "Internal error: ${e.message}"))
            }
        }
    }

    private fun readLine(input: InputStream, budget: IntArray): String? {
        val buf = ByteArrayOutputStream()
        while (true) {
            val b = input.read()
            if (b == -1) return if (buf.size() == 0) null else buf.toString(Charsets.ISO_8859_1.name())
            if (--budget[0] < 0) throw IllegalStateException("headers too large")
            if (b == '\n'.code) return buf.toString(Charsets.ISO_8859_1.name()).trimEnd('\r')
            buf.write(b)
        }
    }

    private fun read(input: InputStream): Request? {
        val budget = intArrayOf(MAX_HEADER)
        val first = readLine(input, budget) ?: return null
        val parts = first.split(" ")
        if (parts.size < 2) return null
        val headers = mutableMapOf<String, String>()
        while (true) {
            val line = readLine(input, budget) ?: break
            if (line.isEmpty()) break
            val colon = line.indexOf(':')
            if (colon > 0) headers[line.substring(0, colon).trim().lowercase()] = line.substring(colon + 1).trim()
        }
        val length = headers["content-length"]?.toIntOrNull() ?: 0
        if (length < 0 || length > MAX_BODY) {
            headers["x-too-large"] = "1"
            return Request(parts[0].uppercase(), parts[1], headers, ByteArray(0))
        }
        val body = ByteArray(length)
        var read = 0
        while (read < length) {
            val n = input.read(body, read, length - read)
            if (n < 0) break
            read += n
        }
        return Request(parts[0].uppercase(), parts[1], headers, body.copyOf(read))
    }

    private fun hostOnly(value: String): String {
        val v = value.trim().lowercase()
        if (v.startsWith("[")) return v.substringBefore("]") + "]"
        return if (v.count { it == ':' } == 1) v.substringBefore(":") else v
    }

    private fun isLocalHost(host: String): Boolean =
        host in LOOPBACK || (lan && host in localHosts().map { it.lowercase() })

    private fun route(req: Request, out: OutputStream) {
        val path = try { URI(req.path).path.trimEnd('/') } catch (_: Exception) { req.path }
        if (path != ENDPOINT) return respond(out, 404, buildJsonObject { put("error", "Not found. The MCP endpoint is $ENDPOINT") })
        if (!isLocalHost(hostOnly(req.headers["host"].orEmpty()))) {
            return respond(out, 403, buildJsonObject { put("error", "Connect using this phone's address.") })
        }
        val origin = req.headers["origin"]
        if (origin != null && origin != "null") {
            val host = try { URI(origin).host?.lowercase().orEmpty() } catch (_: Exception) { "" }
            if (!isLocalHost(host)) return respond(out, 403, buildJsonObject { put("error", "Requests from web pages are not allowed.") })
        }
        val auth = req.headers["authorization"].orEmpty()
        val given = if (auth.length > 7 && auth.substring(0, 7).equals("bearer ", true)) auth.substring(7).trim() else ""
        if (given.isEmpty() || !MessageDigest.isEqual(given.toByteArray(), token.toByteArray())) {
            return respond(out, 401, buildJsonObject {
                put("error", "Missing or wrong access token - copy it from the app's AI agents screen.")
            }, mapOf("WWW-Authenticate" to "Bearer realm=\"Legacy AI Email Studio\""))
        }
        when (req.method) {
            "POST" -> Unit
            "GET", "DELETE" -> return respond(out, 405, buildJsonObject { put("error", "Use POST.") }, mapOf("Allow" to "POST"))
            else -> return respond(out, 405, buildJsonObject { put("error", "Use POST.") }, mapOf("Allow" to "POST"))
        }
        if (req.headers["x-too-large"] != null) {
            return respond(out, 413, McpDispatcher.error(JsonNull, Mcp.INVALID_REQUEST, "Request body is too large."))
        }
        val message: JsonElement = try {
            Mcp.json.parseToJsonElement(req.body.toString(Charsets.UTF_8))
        } catch (_: Exception) {
            return respond(out, 400, McpDispatcher.error(JsonNull, Mcp.PARSE_ERROR, "Body is not valid JSON."))
        }
        val version = req.headers["mcp-protocol-version"]
        if (version != null && version !in Mcp.SUPPORTED_VERSIONS) {
            // 400 as the spec asks, with the request's own id so the client falls back to `initialize`.
            val id = (message as? JsonObject)?.get("id") ?: JsonNull
            return respond(out, 400, McpDispatcher.error(id, Mcp.INVALID_REQUEST,
                "Unsupported MCP-Protocol-Version: $version. Supported: ${Mcp.SUPPORTED_VERSIONS.joinToString(", ")}"))
        }
        val response = dispatcher.handle(message)
        if (response == null) respond(out, 202, null) else respond(out, 200, response)
    }

    private fun respond(out: OutputStream, status: Int, body: JsonElement?, extra: Map<String, String> = emptyMap()) {
        val payload = body?.let { Mcp.json.encodeToString(JsonElement.serializer(), it).toByteArray() } ?: ByteArray(0)
        val reason = mapOf(200 to "OK", 202 to "Accepted", 400 to "Bad Request", 401 to "Unauthorized", 403 to "Forbidden",
            404 to "Not Found", 405 to "Method Not Allowed", 413 to "Payload Too Large", 500 to "Internal Server Error")
        val head = StringBuilder("HTTP/1.1 $status ${reason[status] ?: "OK"}\r\n")
        if (body != null) head.append("Content-Type: application/json; charset=utf-8\r\n")
        head.append("Content-Length: ${payload.size}\r\nCache-Control: no-store\r\nConnection: close\r\n")
        extra.forEach { (k, v) -> head.append("$k: $v\r\n") }
        head.append("\r\n")
        try {
            out.write(head.toString().toByteArray(Charsets.ISO_8859_1))
            out.write(payload)
            out.flush()
        } catch (_: Exception) { }
    }
}
