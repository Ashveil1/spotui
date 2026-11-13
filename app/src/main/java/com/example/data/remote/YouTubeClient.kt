package com.example.data.remote

import android.net.Uri
import com.example.data.model.LyricsData
import com.example.data.model.Track
import com.example.data.util.SpotUiTextUtils
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

class YouTubeClient {

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    private fun webContextJson(): JSONObject = JSONObject().apply {
        put("client", JSONObject().apply {
            put("clientName", "WEB")
            put("clientVersion", "2.20250101.00.00")
            put("hl", "en")
            put("gl", "US")
        })
    }

    private fun innertubePost(endpoint: String, body: JSONObject, userAgent: String = WEB_UA): JSONObject? {
        val req = Request.Builder()
            .url("https://www.youtube.com/youtubei/v1/$endpoint?prettyPrint=false")
            .header("User-Agent", userAgent)
            .header("Content-Type", "application/json")
            .header("Origin", "https://www.youtube.com")
            .post(body.toString().toRequestBody(jsonMediaType))
            .build()
        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) return null
            val raw = resp.body?.string() ?: return null
            return runCatching { JSONObject(raw) }.getOrNull()
        }
    }

    suspend fun search(query: String, limit: Int = 25): Result<List<Track>> = withContext(Dispatchers.IO) {
        runCatching {
            val trimmed = query.trim()
            if (trimmed.isEmpty()) return@runCatching emptyList()

            val body = JSONObject().apply {
                put("context", webContextJson())
                put("query", trimmed)
                put("params", "EgIQAQ%3D%3D") // videos filter
            }
            val root = innertubePost("search", body)
                ?: throw RuntimeException("YouTube search failed")

            val tracks = mutableListOf<Track>()
            val seenIds = mutableSetOf<String>()
            collectVideoRenderers(root, tracks, seenIds, limit)
            tracks
        }
    }

    suspend fun fetchRadioMix(videoId: String, limit: Int = 60): Result<List<Track>> = withContext(Dispatchers.IO) {
        runCatching {
            val playlistId = "RDAMVM$videoId"
            val body = JSONObject().apply {
                put("context", webContextJson())
                put("videoId", videoId)
                put("playlistId", playlistId)
            }
            val root = innertubePost("next", body)
                ?: throw RuntimeException("Radio mix unavailable")
            val tracks = mutableListOf<Track>()
            val seenIds = mutableSetOf<String>()
            collectPlaylistPanelRenderers(root, tracks, seenIds, limit)
            if (tracks.isEmpty()) {
                collectVideoRenderers(root, tracks, seenIds, limit)
            }
            tracks
        }
    }

    suspend fun fetchPlaylist(urlOrId: String, limit: Int = 200): Result<Pair<String?, List<Track>>> = withContext(Dispatchers.IO) {
        runCatching {
            val listId = extractPlaylistId(urlOrId)
                ?: throw IllegalArgumentException("No playlist ID found in link")
            val body = JSONObject().apply {
                put("context", webContextJson())
                put("browseId", if (listId.startsWith("VL")) listId else "VL$listId")
            }
            val root = innertubePost("browse", body)
                ?: throw RuntimeException("Could not load YouTube playlist")

            val title = extractPlaylistTitle(root)
            val tracks = mutableListOf<Track>()
            val seenIds = mutableSetOf<String>()
            collectPlaylistVideoRenderers(root, tracks, seenIds, limit)
            if (tracks.isEmpty()) {
                // fallback via next endpoint if it's a watch+list URL or mix
                val vidId = extractVideoId(urlOrId)
                val nextBody = JSONObject().apply {
                    put("context", webContextJson())
                    put("playlistId", listId)
                    if (vidId != null) put("videoId", vidId)
                }
                val nextRoot = innertubePost("next", nextBody)
                if (nextRoot != null) {
                    collectPlaylistPanelRenderers(nextRoot, tracks, seenIds, limit)
                }
            }
            title to tracks
        }
    }

    suspend fun resolveAudioStreamUrl(videoId: String): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
            for (spec in CLIENT_SPECS) {
                val url = tryPlayerClient(videoId, spec)
                if (!url.isNullOrBlank()) return@runCatching url
            }

            throw RuntimeException("No playable audio stream found")
        }
    }


    data class VideoStream(
        val videoUrl: String,
        val audioUrl: String?,
        val qualityLabel: String,
        val muxed: Boolean
    )

    suspend fun resolveVideoStream(videoId: String): Result<VideoStream> = withContext(Dispatchers.IO) {
        runCatching {
            for (spec in CLIENT_SPECS) {
                val vs = tryPlayerVideoClient(videoId, spec)
                if (vs != null) return@runCatching vs
            }
            throw RuntimeException("No playable video stream found")
        }
    }

    private fun tryPlayerVideoClient(videoId: String, spec: ClientSpec): VideoStream? {
        return runCatching {
            val clientObj = JSONObject().apply {
                put("clientName", spec.name)
                put("clientVersion", spec.version)
                put("hl", "en")
                put("gl", "US")
                if (spec.androidSdk != null) put("androidSdkVersion", spec.androidSdk)
                if (spec.osVersion != null) put("osVersion", spec.osVersion)
            }
            val body = JSONObject().apply {
                put("context", JSONObject().put("client", clientObj))
                put("videoId", videoId)
                put("contentCheckOk", true)
                put("racyCheckOk", true)
            }
            val root = innertubePost("player", body, userAgent = spec.userAgent) ?: return null
            val status = root.optJSONObject("playabilityStatus")?.optString("status")
            if (status != null && status != "OK") return null
            val streaming = root.optJSONObject("streamingData") ?: return null
            selectVideoStream(streaming)
        }.getOrNull()
    }

    private fun selectVideoStream(streaming: JSONObject): VideoStream? {
        val adaptive = streaming.optJSONArray("adaptiveFormats")
        // Prefer a high-quality video-only stream paired with the best audio.
        val videoOnly = pickBestVideo(adaptive, maxHeight = 1080, requireAudio = false)
        val audio = pickBestAudioUrl(adaptive)
        if (videoOnly != null && audio != null) {
            return VideoStream(videoOnly.first, audio, videoOnly.second, muxed = false)
        }
        // Otherwise the best muxed (audio+video) stream, usually 360p/720p.
        val mux = pickBestVideo(streaming.optJSONArray("formats"), maxHeight = 720, requireAudio = true)
            ?: pickBestVideo(adaptive, maxHeight = 720, requireAudio = true)
        if (mux != null) return VideoStream(mux.first, null, mux.second, muxed = true)
        return null
    }

    private fun pickBestVideo(arr: JSONArray?, maxHeight: Int, requireAudio: Boolean): Pair<String, String>? {
        if (arr == null) return null
        var anyUrl: String? = null
        var anyLabel = ""
        var anyH = -1
        var mp4Url: String? = null
        var mp4Label = ""
        var mp4H = -1
        for (i in 0 until arr.length()) {
            val f = arr.optJSONObject(i) ?: continue
            val mime = f.optString("mimeType")
            if (!mime.startsWith("video/")) continue
            if (requireAudio && f.optString("audioQuality").isEmpty()) continue
            if (!requireAudio && f.optString("audioQuality").isNotEmpty()) continue
            val h = f.optInt("height", 0)
            if (h <= 0 || h > maxHeight) continue
            val url = f.optString("url")
            if (url.isEmpty()) continue
            val label = f.optString("qualityLabel").ifEmpty { "${h}p" }
            if (mime.startsWith("video/mp4")) {
                if (h > mp4H) { mp4H = h; mp4Url = url; mp4Label = label }
            } else if (h > anyH) {
                anyH = h; anyUrl = url; anyLabel = label
            }
        }
        return if (mp4Url != null) mp4Url to mp4Label else anyUrl?.let { it to anyLabel }
    }

    private fun tryPlayerClient(videoId: String, spec: ClientSpec): String? {
        return runCatching {
            val clientObj = JSONObject().apply {
                put("clientName", spec.name)
                put("clientVersion", spec.version)
                put("hl", "en")
                put("gl", "US")
                if (spec.androidSdk != null) put("androidSdkVersion", spec.androidSdk)
                if (spec.osVersion != null) put("osVersion", spec.osVersion)
            }
            val body = JSONObject().apply {
                put("context", JSONObject().put("client", clientObj))
                put("videoId", videoId)
                put("contentCheckOk", true)
                put("racyCheckOk", true)
            }
            val root = innertubePost("player", body, userAgent = spec.userAgent) ?: return null
            val status = root.optJSONObject("playabilityStatus")?.optString("status")
            if (status != null && status != "OK") return null
            val streaming = root.optJSONObject("streamingData") ?: return null
            pickBestAudioUrl(streaming.optJSONArray("adaptiveFormats"))
                ?: pickBestAudioUrl(streaming.optJSONArray("formats"))
        }.getOrNull()
    }

    private fun pickBestAudioUrl(arr: JSONArray?): String? {
        if (arr == null) return null
        var bestUrl: String? = null
        var bestScore = -1
        for (i in 0 until arr.length()) {
            val f = arr.optJSONObject(i) ?: continue
            val url = f.optString("url", "")
            if (url.isBlank()) continue
            val mime = f.optString("mimeType", "")
            val isAudio = mime.startsWith("audio/")
            val bitrate = f.optInt("bitrate", 0)
            val isMp4 = mime.contains("audio/mp4")
            val score = when {
                isAudio && isMp4 -> 10_000_000 + bitrate
                isAudio -> 5_000_000 + bitrate
                else -> bitrate
            }
            if (score > bestScore) {
                bestScore = score
                bestUrl = url
            }
        }
        return bestUrl
    }


    suspend fun fetchLyrics(title: String, artist: String): LyricsData? = withContext(Dispatchers.IO) {
        if (title.isBlank() || artist.isBlank()) return@withContext null
        runCatching {
            val qTitle = URLEncoder.encode(title, "UTF-8")
            val qArtist = URLEncoder.encode(artist, "UTF-8")
            val req = Request.Builder()
                .url("https://lrclib.net/api/get?track_name=$qTitle&artist_name=$qArtist")
                .header("User-Agent", "spotui (android music player)")
                .build()
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return@runCatching null
                val raw = resp.body?.string() ?: return@runCatching null
                val data = JSONObject(raw)
                val plain = data.optString("plainLyrics", "").trim().ifEmpty { null }
                val syncedRaw = data.optString("syncedLyrics", "").trim().ifEmpty { null }
                val synced = SpotUiTextUtils.parseLrc(syncedRaw)
                if (plain == null && synced.isEmpty()) return@runCatching null
                LyricsData(
                    trackId = "",
                    plainText = plain,
                    synced = synced,
                    fetchedAtEpochSec = System.currentTimeMillis() / 1000L
                )
            }
        }.getOrNull()
    }

    private fun extractPlaylistId(input: String): String? {
        val trimmed = input.trim()
        if (trimmed.matches(Regex("^[A-Za-z0-9_-]{10,}$"))) return trimmed
        return runCatching {
            Uri.parse(trimmed).getQueryParameter("list")
        }.getOrNull()?.takeIf { it.isNotBlank() }
    }

    private fun extractVideoId(input: String): String? {
        return runCatching {
            val uri = Uri.parse(input.trim())
            uri.getQueryParameter("v") ?: uri.lastPathSegment
        }.getOrNull()?.takeIf { it.matches(SpotUiTextUtils.VALID_ID_REGEX) }
    }

    private fun extractPlaylistTitle(root: JSONObject): String? {
        val meta = root.optJSONObject("metadata")?.optJSONObject("playlistMetadataRenderer")
        val t1 = meta?.optString("title", "")?.trim()
        if (!t1.isNullOrEmpty()) return t1
        val header = root.optJSONObject("header")
        val h1 = header?.optJSONObject("playlistHeaderRenderer")?.optJSONObject("title")?.let(::readRunsText)
        if (!h1.isNullOrBlank()) return h1
        val pageHeader = header?.optJSONObject("pageHeaderRenderer")?.optString("pageTitle", "")?.trim()
        return pageHeader?.ifEmpty { null }
    }

    private fun readRunsText(obj: JSONObject?): String {
        if (obj == null) return ""
        val simple = obj.optString("simpleText", "")
        if (simple.isNotEmpty()) return simple
        val runs = obj.optJSONArray("runs") ?: return ""
        val sb = StringBuilder()
        for (i in 0 until runs.length()) {
            sb.append(runs.optJSONObject(i)?.optString("text", "") ?: "")
        }
        return sb.toString()
    }

    private fun parseVideoObject(v: JSONObject): Track? {
        val id = v.optString("videoId", "")
        if (!id.matches(SpotUiTextUtils.VALID_ID_REGEX)) return null
        val rawTitle = readRunsText(v.optJSONObject("title")).ifBlank { id }
        val uploader = readRunsText(v.optJSONObject("ownerText"))
            .ifBlank { readRunsText(v.optJSONObject("shortBylineText")) }
            .ifBlank { readRunsText(v.optJSONObject("longBylineText")) }
        val durText = readRunsText(v.optJSONObject("lengthText"))
        val durSec = SpotUiTextUtils.parseDurationText(durText)
        val (artist, cleanT) = SpotUiTextUtils.splitArtist(SpotUiTextUtils.cleanTitle(rawTitle), uploader)
        return Track(
            id = id,
            title = cleanT,
            artist = artist,
            durSec = durSec,
            url = "https://www.youtube.com/watch?v=$id",
            channel = uploader
        )
    }

    private fun collectVideoRenderers(
        node: Any?,
        out: MutableList<Track>,
        seen: MutableSet<String>,
        limit: Int
    ) {
        if (out.size >= limit || node == null) return
        when (node) {
            is JSONObject -> {
                val vr = node.optJSONObject("videoRenderer")
                    ?: node.optJSONObject("compactVideoRenderer")
                    ?: node.optJSONObject("gridVideoRenderer")
                if (vr != null) {
                    parseVideoObject(vr)?.let { t ->
                        if (seen.add(t.id)) out.add(t)
                    }
                }
                val keys = node.keys()
                while (keys.hasNext() && out.size < limit) {
                    collectVideoRenderers(node.opt(keys.next()), out, seen, limit)
                }
            }
            is JSONArray -> {
                for (i in 0 until node.length()) {
                    if (out.size >= limit) break
                    collectVideoRenderers(node.opt(i), out, seen, limit)
                }
            }
        }
    }

    private fun collectPlaylistPanelRenderers(
        node: Any?,
        out: MutableList<Track>,
        seen: MutableSet<String>,
        limit: Int
    ) {
        if (out.size >= limit || node == null) return
        when (node) {
            is JSONObject -> {
                val pv = node.optJSONObject("playlistPanelVideoRenderer")
                if (pv != null) {
                    parseVideoObject(pv)?.let { t ->
                        if (seen.add(t.id)) out.add(t)
                    }
                }
                val keys = node.keys()
                while (keys.hasNext() && out.size < limit) {
                    collectPlaylistPanelRenderers(node.opt(keys.next()), out, seen, limit)
                }
            }
            is JSONArray -> {
                for (i in 0 until node.length()) {
                    if (out.size >= limit) break
                    collectPlaylistPanelRenderers(node.opt(i), out, seen, limit)
                }
            }
        }
    }

    private fun collectPlaylistVideoRenderers(
        node: Any?,
        out: MutableList<Track>,
        seen: MutableSet<String>,
        limit: Int
    ) {
        if (out.size >= limit || node == null) return
        when (node) {
            is JSONObject -> {
                val pv = node.optJSONObject("playlistVideoRenderer")
                if (pv != null) {
                    parseVideoObject(pv)?.let { t ->
                        if (seen.add(t.id)) out.add(t)
                    }
                }
                val keys = node.keys()
                while (keys.hasNext() && out.size < limit) {
                    collectPlaylistVideoRenderers(node.opt(keys.next()), out, seen, limit)
                }
            }
            is JSONArray -> {
                for (i in 0 until node.length()) {
                    if (out.size >= limit) break
                    collectPlaylistVideoRenderers(node.opt(i), out, seen, limit)
                }
            }
        }
    }

    private data class ClientSpec(
        val name: String,
        val version: String,
        val userAgent: String,
        val androidSdk: Int?,
        val osVersion: String?
    )

    companion object {
        private val CLIENT_SPECS = listOf(
            ClientSpec("ANDROID_VR", "1.60.19", "com.google.android.apps.youtube.vr.oculus/1.60.19 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip", 32, "12L"),
            ClientSpec("IOS", "20.10.4", "com.google.ios.youtube/20.10.4 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)", null, null),
            ClientSpec("ANDROID", "20.10.38", "com.google.android.youtube/20.10.38 (Linux; U; Android 14) gzip", 34, "14")
        )
        private const val WEB_UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
}
