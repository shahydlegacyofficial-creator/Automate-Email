package com.travelessence.emailstudio.agent.protocol

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put

/**
 * The Model Context Protocol, the part this app needs - the Kotlin twin of the desktop app's
 * `core/mcp_server.py`: the `initialize` handshake (2024-11-05 … 2025-11-25), `ping`,
 * `tools/list` and `tools/call`, as plain JSON-RPC. No Android code in here, so it is unit-tested
 * on the JVM against the official MCP client.
 */
object Mcp {
    val SUPPORTED_VERSIONS = listOf("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
    val LATEST = SUPPORTED_VERSIONS.first()
    const val PARSE_ERROR = -32700
    const val INVALID_REQUEST = -32600
    const val METHOD_NOT_FOUND = -32601
    const val INVALID_PARAMS = -32602
    const val INTERNAL_ERROR = -32603
    val json = Json { ignoreUnknownKeys = true; encodeDefaults = true; explicitNulls = false }
}

/** A problem the AI can fix - returned to it as a tool result with isError = true. */
class ToolError(message: String) : Exception(message)

/** One property of a tool's input. */
data class Param(
    val type: String,                       // string | integer | number | boolean | array | object
    val description: String = "",
    val enum: List<String>? = null,
    val minimum: Long? = null,
    val maximum: Long? = null,
    val items: String? = null,              // element type for arrays
) {
    fun schema(): JsonObject = buildJsonObject {
        put("type", type)
        if (description.isNotEmpty()) put("description", description)
        enum?.let { values -> put("enum", buildJsonArray { values.forEach { add(JsonPrimitive(it)) } }) }
        minimum?.let { put("minimum", it) }
        maximum?.let { put("maximum", it) }
        items?.let { put("items", buildJsonObject { put("type", it) }) }
    }
}

class AgentTool(
    val name: String,
    val title: String,
    val description: String,
    val params: Map<String, Param> = emptyMap(),
    val required: List<String> = emptyList(),
    val readOnly: Boolean = false,
    val destructive: Boolean = false,
    val idempotent: Boolean = false,
    val openWorld: Boolean = false,
    val handler: (Args) -> JsonElement,
) {
    fun describe(): JsonObject = buildJsonObject {
        put("name", name)
        put("title", title)
        put("description", description)
        put("inputSchema", buildJsonObject {
            put("type", "object")
            put("properties", JsonObject(params.mapValues { it.value.schema() }))
            put("required", buildJsonArray { required.forEach { add(JsonPrimitive(it)) } })
            put("additionalProperties", false)
        })
        put("annotations", buildJsonObject {
            put("title", title)
            put("readOnlyHint", readOnly)
            put("destructiveHint", destructive)
            put("idempotentHint", idempotent)
            put("openWorldHint", openWorld)
        })
    }
}

/** Validated arguments with typed getters. */
class Args(val raw: JsonObject) {
    private fun p(name: String) = (raw[name] as? JsonPrimitive)?.takeUnless { it is JsonNull }
    fun string(name: String): String? = p(name)?.contentOrNull
    fun int(name: String): Int? = p(name)?.longOrNull?.toInt()
    fun bool(name: String): Boolean? = p(name)?.booleanOrNull
    fun strings(name: String): List<String> =
        (raw[name] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull } ?: emptyList()
    fun has(name: String) = raw[name] != null && raw[name] !is JsonNull
}

fun checkArguments(tool: AgentTool, element: JsonElement?): Args {
    val args = when (element) {
        null, JsonNull -> JsonObject(emptyMap())
        is JsonObject -> element
        else -> throw ToolError("Arguments must be a JSON object.")
    }
    val missing = tool.required.filter { name ->
        val v = args[name]
        v == null || v is JsonNull || (v is JsonPrimitive && v.isString && v.content.isEmpty())
    }
    if (missing.isNotEmpty()) throw ToolError("Missing required argument(s): ${missing.joinToString(", ")}.")
    val unknown = args.keys.filter { it !in tool.params }
    if (unknown.isNotEmpty()) {
        throw ToolError("Unknown argument(s): ${unknown.joinToString(", ")}. " +
            "Allowed: ${tool.params.keys.joinToString(", ").ifEmpty { "none" }}.")
    }
    for ((name, value) in args) {
        if (value is JsonNull) continue
        val spec = tool.params.getValue(name)
        val a = if (spec.type[0] in "aeiou") "an" else "a"
        fun bad(): Nothing = throw ToolError("'$name' must be $a ${spec.type}.")
        when (spec.type) {
            "string" -> if (value !is JsonPrimitive || !value.isString) bad()
            "boolean" -> if (value !is JsonPrimitive || value.isString || value.booleanOrNull == null) bad()
            "integer", "number" -> {
                if (value !is JsonPrimitive || value.isString) bad()
                val number = value.doubleOrNull ?: bad()
                if (spec.type == "integer" && number != Math.floor(number)) bad()
                spec.minimum?.let { if (number < it) throw ToolError("'$name' must be at least $it.") }
                spec.maximum?.let { if (number > it) throw ToolError("'$name' must be at most $it.") }
            }
            "array" -> {
                if (value !is JsonArray) bad()
                if (spec.items == "string" && value.any { it !is JsonPrimitive || !it.isString }) {
                    throw ToolError("'$name' must be a list of strings.")
                }
            }
            "object" -> if (value !is JsonObject) bad()
        }
        if (spec.enum != null && (value as? JsonPrimitive)?.contentOrNull !in spec.enum) {
            throw ToolError("'$name' must be one of: ${spec.enum.joinToString(", ")}.")
        }
    }
    return Args(args)
}

/** Transport-independent JSON-RPC handling. */
class McpDispatcher(
    tools: List<AgentTool>,
    private val serverName: String,
    private val serverVersion: String,
    private val serverTitle: String = "",
    private val instructions: String = "",
    private val onCall: ((tool: String, args: JsonObject, result: JsonObject) -> Unit)? = null,
) {
    val tools: Map<String, AgentTool> = tools.associateBy { it.name }

    @Volatile var clientName: String = ""
        private set

    private class RpcError(val code: Int, message: String) : Exception(message)

    /** Handle one decoded message (or batch). Returns the response, or null when none is due. */
    fun handle(message: JsonElement): JsonElement? {
        if (message is JsonArray) {
            val responses = message.mapNotNull { handleOne(it) }
            return if (responses.isEmpty()) null else JsonArray(responses)
        }
        return handleOne(message)
    }

    private fun handleOne(message: JsonElement): JsonObject? {
        val obj = message as? JsonObject
        if (obj == null || (obj["jsonrpc"] as? JsonPrimitive)?.contentOrNull != "2.0") {
            return error(JsonNull, Mcp.INVALID_REQUEST, "Invalid JSON-RPC 2.0 message.")
        }
        if (!obj.containsKey("method")) return null          // a response to us - we never ask anything
        val id = obj["id"] ?: return null                     // a notification
        val method = (obj["method"] as? JsonPrimitive)?.contentOrNull
        val params = when (val p = obj["params"]) {
            null, JsonNull -> JsonObject(emptyMap())
            is JsonObject -> p
            else -> return error(id, Mcp.INVALID_PARAMS, "params must be an object.")
        }
        return try {
            val result = when (method) {
                "initialize" -> initialize(params)
                "ping" -> JsonObject(emptyMap())
                "tools/list" -> buildJsonObject { put("tools", JsonArray(tools.values.map { it.describe() })) }
                "tools/call" -> call(params)
                else -> return error(id, Mcp.METHOD_NOT_FOUND, "Method not found: $method")
            }
            buildJsonObject { put("jsonrpc", "2.0"); put("id", id); put("result", result) }
        } catch (e: RpcError) {
            error(id, e.code, e.message ?: "")
        } catch (e: Exception) {
            error(id, Mcp.INTERNAL_ERROR, "Internal error: ${e.message}")
        }
    }

    private fun initialize(params: JsonObject): JsonObject {
        val info = params["clientInfo"] as? JsonObject
        clientName = ((info?.get("title") ?: info?.get("name")) as? JsonPrimitive)?.contentOrNull?.take(60).orEmpty()
        val requested = (params["protocolVersion"] as? JsonPrimitive)?.contentOrNull
        return buildJsonObject {
            put("protocolVersion", if (requested in Mcp.SUPPORTED_VERSIONS) requested else Mcp.LATEST)
            put("capabilities", buildJsonObject { put("tools", buildJsonObject { put("listChanged", false) }) })
            put("serverInfo", buildJsonObject {
                put("name", serverName)
                put("version", serverVersion)
                if (serverTitle.isNotEmpty()) put("title", serverTitle)
            })
            if (instructions.isNotEmpty()) put("instructions", instructions)
        }
    }

    private fun call(params: JsonObject): JsonObject {
        val name = (params["name"] as? JsonPrimitive)?.contentOrNull
        val tool = tools[name] ?: throw RpcError(Mcp.INVALID_PARAMS,
            "Unknown tool: $name. Call tools/list to see the available tools.")
        var args = JsonObject(emptyMap())
        val result = try {
            val checked = checkArguments(tool, params["arguments"])
            args = checked.raw
            toolResult(tool.handler(checked), false)
        } catch (e: ToolError) {
            toolResult(JsonPrimitive(e.message ?: "Refused"), true)
        } catch (e: Exception) {
            toolResult(JsonPrimitive("The app hit an unexpected error: ${e.message ?: e.javaClass.simpleName}"), true)
        }
        try { onCall?.invoke(tool.name, args, result) } catch (_: Exception) { }
        return result
    }

    companion object {
        fun toolResult(data: JsonElement, isError: Boolean): JsonObject {
            val text = if (data is JsonPrimitive && data.isString) data.content
                else Json { prettyPrint = true }.encodeToString(JsonElement.serializer(), data)
            return buildJsonObject {
                put("content", buildJsonArray { add(buildJsonObject { put("type", "text"); put("text", text) }) })
                put("isError", isError)
                if (!isError && data is JsonObject) put("structuredContent", data)
            }
        }

        fun error(id: JsonElement, code: Int, message: String): JsonObject = buildJsonObject {
            put("jsonrpc", "2.0")
            put("id", id)
            put("error", buildJsonObject { put("code", code); put("message", message) })
        }

        /** Convenience for handlers: a JSON object from plain Kotlin values. */
        fun obj(vararg pairs: Pair<String, Any?>): JsonObject = JsonObject(pairs.associate { (k, v) -> k to toJson(v) })

        fun toJson(v: Any?): JsonElement = when (v) {
            null -> JsonNull
            is JsonElement -> v
            is String -> JsonPrimitive(v)
            is Number -> JsonPrimitive(v)
            is Boolean -> JsonPrimitive(v)
            is Map<*, *> -> JsonObject(v.entries.associate { (k, value) -> k.toString() to toJson(value) })
            is Iterable<*> -> JsonArray(v.map { toJson(it) })
            else -> JsonPrimitive(v.toString())
        }
    }
}

/** Reads a string from a JsonObject result (used by tests and the activity log). */
fun JsonObject.str(key: String): String? = (this[key] as? JsonPrimitive)?.contentOrNull
