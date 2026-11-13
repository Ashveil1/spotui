package com.example.data.local

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.doublePreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.example.data.model.EqPreset
import com.example.data.model.PlaybackSession
import com.example.data.model.ShuffleMode
import com.example.data.model.SimilarCache
import com.example.data.model.SortMode
import com.example.data.model.SpotTheme
import com.example.data.model.Track
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import org.json.JSONArray
import org.json.JSONObject

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "spotui_prefs")

data class SpotUiPreferences(
    val theme: SpotTheme = SpotTheme.SPOTIFY,
    val volume: Int = 70,
    val shuffleMode: ShuffleMode = ShuffleMode.SPREAD,
    val sortMode: SortMode = SortMode.DEFAULT,
    val autoplay: Boolean = true,
    val timeLeft: Boolean = false,
    val eqPreset: EqPreset = EqPreset.OFF,
    val volumeLeveling: Boolean = false,
    val histDedupe: Boolean = false,
    val zenMode: Boolean = false,
    val reducedMotion: Boolean = false,
    val firstPlayEpochSec: Double? = null,
    val lastSearchEpochSec: Double = 0.0,
    val similarCache: SimilarCache = SimilarCache(),
    val session: PlaybackSession = PlaybackSession()
)

class PreferencesRepository(private val context: Context) {

    private object Keys {
        val THEME = stringPreferencesKey("theme")
        val VOLUME = intPreferencesKey("volume")
        val SHUFFLE_MODE = stringPreferencesKey("shuffle_mode")
        val SORT_MODE = stringPreferencesKey("sort_mode")
        val AUTOPLAY = booleanPreferencesKey("autoplay")
        val TIME_LEFT = booleanPreferencesKey("time_left")
        val EQ_PRESET = stringPreferencesKey("eq_preset")
        val LEVELING = booleanPreferencesKey("volume_leveling")
        val HIST_DEDUPE = booleanPreferencesKey("hist_dedupe")
        val ZEN = booleanPreferencesKey("zen_mode")
        val REDUCED_MOTION = booleanPreferencesKey("reduced_motion")
        val FIRST_PLAY = doublePreferencesKey("first_play")
        val LAST_SEARCH = doublePreferencesKey("last_search")
        val SIMILAR_JSON = stringPreferencesKey("similar_json")
        val SESSION_JSON = stringPreferencesKey("session_json")
    }

    val preferences: Flow<SpotUiPreferences> = context.dataStore.data.map { p ->
        val fp = p[Keys.FIRST_PLAY]
        SpotUiPreferences(
            theme = SpotTheme.fromName(p[Keys.THEME]),
            volume = (p[Keys.VOLUME] ?: 70).coerceIn(0, 100),
            shuffleMode = ShuffleMode.fromKey(p[Keys.SHUFFLE_MODE]),
            sortMode = SortMode.fromKey(p[Keys.SORT_MODE]),
            autoplay = p[Keys.AUTOPLAY] ?: true,
            timeLeft = p[Keys.TIME_LEFT] ?: false,
            eqPreset = EqPreset.fromKey(p[Keys.EQ_PRESET]),
            volumeLeveling = p[Keys.LEVELING] ?: false,
            histDedupe = p[Keys.HIST_DEDUPE] ?: false,
            zenMode = p[Keys.ZEN] ?: false,
            reducedMotion = p[Keys.REDUCED_MOTION] ?: false,
            firstPlayEpochSec = if (fp != null && fp.isFinite() && fp > 0.0) fp else null,
            lastSearchEpochSec = p[Keys.LAST_SEARCH] ?: 0.0,
            similarCache = decodeSimilar(p[Keys.SIMILAR_JSON]),
            session = decodeSession(p[Keys.SESSION_JSON])
        )
    }

    suspend fun setTheme(theme: SpotTheme) = edit { it[Keys.THEME] = theme.displayName }
    suspend fun setVolume(vol: Int) = edit { it[Keys.VOLUME] = vol.coerceIn(0, 100) }
    suspend fun setShuffleMode(mode: ShuffleMode) = edit { it[Keys.SHUFFLE_MODE] = mode.key }
    suspend fun setSortMode(mode: SortMode) = edit { it[Keys.SORT_MODE] = mode.key }
    suspend fun setAutoplay(on: Boolean) = edit { it[Keys.AUTOPLAY] = on }
    suspend fun setTimeLeft(on: Boolean) = edit { it[Keys.TIME_LEFT] = on }
    suspend fun setEqPreset(preset: EqPreset) = edit { it[Keys.EQ_PRESET] = preset.key }
    suspend fun setVolumeLeveling(on: Boolean) = edit { it[Keys.LEVELING] = on }
    suspend fun setHistDedupe(on: Boolean) = edit { it[Keys.HIST_DEDUPE] = on }
    suspend fun setZenMode(on: Boolean) = edit { it[Keys.ZEN] = on }
    suspend fun setReducedMotion(on: Boolean) = edit { it[Keys.REDUCED_MOTION] = on }
    suspend fun setFirstPlayIfUnset(epochSec: Double) = edit {
        if ((it[Keys.FIRST_PLAY] ?: 0.0) <= 0.0) it[Keys.FIRST_PLAY] = epochSec
    }
    suspend fun clearFirstPlay() = edit { it.remove(Keys.FIRST_PLAY) }
    suspend fun setLastSearch(epochSec: Double) = edit { it[Keys.LAST_SEARCH] = epochSec }
    suspend fun setSimilarCache(cache: SimilarCache) = edit { it[Keys.SIMILAR_JSON] = encodeSimilar(cache) }
    suspend fun setSession(session: PlaybackSession) = edit { it[Keys.SESSION_JSON] = encodeSession(session) }

    private suspend fun edit(block: (androidx.datastore.preferences.core.MutablePreferences) -> Unit) {
        context.dataStore.edit(block)
    }

    companion object {
        fun trackToJson(t: Track): JSONObject = JSONObject().apply {
            put("id", t.id)
            put("title", t.title)
            put("artist", t.artist)
            if (t.durSec != null) put("dur", t.durSec) else put("dur", JSONObject.NULL)
            put("url", t.url)
            if (t.channel.isNotEmpty()) put("ch", t.channel)
            if (t.addedDate != null) put("added", t.addedDate)
        }

        fun trackFromJson(o: JSONObject): Track? {
            val id = o.optString("id", "").takeIf { it.matches(Regex("^[A-Za-z0-9_-]+$")) } ?: return null
            val title = o.optString("title", "").ifBlank { "Unknown title" }
            val artist = o.optString("artist", "").ifBlank { "Unknown artist" }
            val dur = if (o.isNull("dur")) null else o.optInt("dur", -1).takeIf { it >= 0 }
            val ch = o.optString("ch", "")
            val addedAny = o.opt("added")
            val addedDate = if (addedAny is String) addedAny else null
            return Track(
                id = id,
                title = title,
                artist = artist,
                durSec = dur,
                url = "https://www.youtube.com/watch?v=$id",
                channel = ch,
                addedDate = addedDate
            )
        }

        private fun encodeTracks(tracks: List<Track>): JSONArray = JSONArray().apply {
            tracks.forEach { put(trackToJson(it)) }
        }

        private fun decodeTracks(arr: JSONArray?): List<Track> {
            if (arr == null) return emptyList()
            val out = mutableListOf<Track>()
            for (i in 0 until arr.length()) {
                val obj = arr.optJSONObject(i) ?: continue
                trackFromJson(obj)?.let(out::add)
            }
            return out
        }

        private fun encodeSimilar(c: SimilarCache): String = JSONObject().apply {
            put("v", c.version)
            put("seed", c.seed)
            put("kind", c.kind)
            if (c.videoId != null) put("vid", c.videoId)
            put("items", encodeTracks(c.items))
            put("pool", encodeTracks(c.pool))
            put("ts", c.updatedAtSec)
        }.toString()

        private fun decodeSimilar(raw: String?): SimilarCache {
            if (raw.isNullOrBlank()) return SimilarCache()
            return runCatching {
                val o = JSONObject(raw)
                SimilarCache(
                    version = o.optInt("v", 2),
                    seed = o.optString("seed", ""),
                    kind = o.optString("kind", "artist"),
                    videoId = o.optString("vid", "").ifEmpty { null },
                    items = decodeTracks(o.optJSONArray("items")),
                    pool = decodeTracks(o.optJSONArray("pool")),
                    updatedAtSec = o.optDouble("ts", 0.0).takeIf { it.isFinite() } ?: 0.0
                )
            }.getOrDefault(SimilarCache())
        }

        private fun encodeSession(s: PlaybackSession): String = JSONObject().apply {
            put("queue", encodeTracks(s.queue.take(500)))
            put("pos", s.qpos)
            put("t", s.positionSec)
            if (s.playSource != null) put("src", s.playSource)
        }.toString()

        private fun decodeSession(raw: String?): PlaybackSession {
            if (raw.isNullOrBlank()) return PlaybackSession()
            return runCatching {
                val o = JSONObject(raw)
                val q = decodeTracks(o.optJSONArray("queue")).take(500)
                val pos = o.optInt("pos", 0)
                val t = o.optDouble("t", 0.0).let { if (it.isFinite() && it >= 0.0) it else 0.0 }
                val src = o.optString("src", "").ifEmpty { null }
                PlaybackSession(queue = q, qpos = pos, positionSec = t, playSource = src)
            }.getOrDefault(PlaybackSession())
        }
    }
}
