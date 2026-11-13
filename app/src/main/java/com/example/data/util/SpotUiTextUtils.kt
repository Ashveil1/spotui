package com.example.data.util

import androidx.compose.ui.graphics.Color
import com.example.data.model.DailyMix
import com.example.data.model.HourBucket
import com.example.data.model.PlayCount
import com.example.data.model.Playlist
import com.example.data.model.ShuffleMode
import com.example.data.model.SortMode
import com.example.data.model.StatsDay
import com.example.data.model.StatsSummaryData
import com.example.data.model.SyncedLine
import com.example.data.model.TopSongRow
import com.example.data.model.Track
import java.security.MessageDigest
import java.text.Normalizer
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import kotlin.random.Random

object SpotUiTextUtils {

    val VALID_ID_REGEX = Regex("^[A-Za-z0-9_-]+$")
    val SPEEDS = listOf(0.75f, 1.0f, 1.25f, 1.5f, 2.0f)

    // Exact 8 color families x 4 shades from spotui.py FAMS
    val COVER_FAMILIES: List<List<Color>> = listOf(
        listOf(Color(29, 185, 84), Color(18, 138, 63), Color(12, 92, 42), Color(7, 53, 28)),      // green
        listOf(Color(155, 89, 182), Color(108, 52, 131), Color(74, 35, 90), Color(40, 17, 58)),   // purple
        listOf(Color(230, 126, 34), Color(185, 119, 14), Color(142, 91, 8), Color(93, 63, 8)),    // orange
        listOf(Color(52, 152, 219), Color(40, 116, 166), Color(26, 82, 118), Color(18, 48, 89)),  // blue
        listOf(Color(231, 76, 60), Color(176, 58, 46), Color(123, 45, 38), Color(78, 27, 23)),    // red
        listOf(Color(26, 188, 156), Color(20, 143, 119), Color(14, 102, 85), Color(9, 74, 56)),   // teal
        listOf(Color(240, 98, 146), Color(190, 63, 105), Color(140, 44, 77), Color(92, 26, 47)),  // magenta
        listOf(Color(93, 109, 222), Color(65, 77, 157), Color(47, 56, 113), Color(28, 33, 70))    // indigo
    )

    fun artFamilyIndex(seed: String): Int {
        val digest = MessageDigest.getInstance("MD5").digest(seed.toByteArray(Charsets.UTF_8))
        val firstByte = digest[0].toInt() and 0xFF
        return firstByte % COVER_FAMILIES.size
    }

    fun coverShades(seed: String): List<Color> = COVER_FAMILIES[artFamilyIndex(seed)]

    private val JUNK_WORDS = Regex(
        """official|video|audio|lyric|visuali[sz]er|\bhq\b|\bhd\b|4k|\bmv\b|fmv|color\s*coded|performance|karaoke|instrumental|remaster|full\s+album|sub\s*esp|hardstyle|nightcore|explicit""",
        RegexOption.IGNORE_CASE
    )
    private val SPLIT_RE = Regex("""\s+[-–—]\s+""")
    private val MIX_WORDS = listOf(
        "playlist", "mix", "top hits", "best of", "full album",
        "greatest hits", "non stop", "nonstop", "compilation",
        "collection", "all songs", "videos"
    )

    private fun stripJunkParen(s: String): Pair<String, Boolean> {
        val out = StringBuilder()
        var i = 0
        var changed = false
        while (i < s.length) {
            val c = s[i]
            if (c == '(' || c == '[') {
                var depth = 1
                var j = i + 1
                while (j < s.length && depth > 0) {
                    val c2 = s[j]
                    if (c2 == '(' || c2 == '[') depth++
                    else if (c2 == ')' || c2 == ']') depth--
                    j++
                }
                val inner = if (j > i + 1) s.substring(i + 1, j - 1) else ""
                if (depth == 0 && inner.length <= 40 && JUNK_WORDS.containsMatchIn(inner)) {
                    i = j
                    changed = true
                    continue
                }
                out.append(s.substring(i, j))
                i = j
            } else {
                out.append(c)
                i++
            }
        }
        return out.toString() to changed
    }

    fun cleanTitle(raw: String?): String {
        var s = (raw ?: "").replace(Regex("""【[^】]*】"""), " ")
        repeat(4) {
            val (next, changed) = stripJunkParen(s)
            s = next
            if (!changed) return@repeat
        }
        s = s.replace(Regex("""\s*[-–—]\s*(official\s+)?(music\s+)?(video|audio|lyrics?)\s*$""", RegexOption.IGNORE_CASE), "")
        s = s.replace(Regex("""\s+(HQ|HD|4K)\s+(Audio|Video|Lyrics|MV)\s*$""", RegexOption.IGNORE_CASE), "")
        s = s.replace(Regex("""\s{2,}"""), " ").trim(' ', '-', '–', '—', '|')
        return s.ifEmpty { "Unknown title" }
    }

    private fun normAlnum(s: String?): String =
        (s ?: "").lowercase(Locale.ROOT).replace(Regex("[^a-z0-9]"), "")

    fun prettyArtist(uploader: String?): String {
        var up = (uploader ?: "").trim()
        up = up.replace(Regex("""^official\s+""", RegexOption.IGNORE_CASE), "")
        up = up.replace(
            Regex("""\s*[-–—]?\s*(official)?\s*(music\s*)?(video|vevo|topic|records|tv)\s*$""", RegexOption.IGNORE_CASE),
            ""
        ).trim()
        val vevoMatch = Regex("""^(.+?)VEVO$""", RegexOption.IGNORE_CASE).matchEntire(up)
        if (vevoMatch != null) {
            up = vevoMatch.groupValues[1]
        }
        val spaced = up.replace(Regex("""(?<=[a-z])(?=[A-Z])"""), " ").trim()
        return spaced.ifEmpty { up }
    }

    fun splitArtist(title: String, uploader: String?): Pair<String, String> {
        val up = (uploader ?: "").trim()
        if (up.endsWith(" - Topic")) {
            val parts = SPLIT_RE.split(title, 2)
            if (parts.size == 2) {
                return parts[0].trim() to parts[1].trim()
            }
            return up.removeSuffix(" - Topic").trim() to title
        }
        val art = prettyArtist(up)
        val parts = SPLIT_RE.split(title, 2)
        if (parts.size == 2) {
            val a = parts[0].trim()
            val t = parts[1].trim()
            val na = normAlnum(a)
            val nart = normAlnum(art)
            if (art.isNotEmpty() && nart.isNotEmpty() && (na == nart || nart.startsWith(na))) {
                return a.ifEmpty { art } to t
            }
        }
        return art.ifEmpty { "Unknown artist" } to title
    }

    fun isRealSong(t: Track): Boolean {
        val dur = t.durSec ?: 0
        if (dur > 600) return false
        val low = t.title.lowercase(Locale.ROOT)
        return MIX_WORDS.none { it in low }
    }

    fun normArtist(name: String?): String =
        Normalizer.normalize(name ?: "", Normalizer.Form.NFKC).lowercase(Locale.ROOT).trim()

    fun todayDateStr(): String =
        SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())

    fun currentYearMonth(): String =
        SimpleDateFormat("yyyy-MM", Locale.US).format(Date())

    fun fmtTime(sec: Int?): String {
        if (sec == null || sec < 0) return "–:––"
        return "%d:%02d".format(Locale.US, sec / 60, sec % 60)
    }

    fun fmtTimeDouble(sec: Double?): String {
        if (sec == null || !sec.isFinite() || sec < 0) return "–:––"
        val s = sec.toInt()
        return "%d:%02d".format(Locale.US, s / 60, s % 60)
    }

    fun fmtAgo(epochSec: Double?, nowSec: Double = System.currentTimeMillis() / 1000.0): String {
        if (epochSec == null || !epochSec.isFinite() || epochSec <= 0.0) return ""
        val d = nowSec - epochSec
        if (d < 0) return ""
        if (d < 3600) return "${maxOf(1, (d / 60).toInt())}m"
        if (d < 86400) return "${(d / 3600).toInt()}h"
        if (d < 7 * 86400) return "${(d / 86400).toInt()}d"
        return "${(d / (7 * 86400)).toInt()}w"
    }

    fun fmtAdded(addedDate: String?, playedAtSec: Double?): String {
        if (playedAtSec != null && playedAtSec.isFinite() && playedAtSec > 0) {
            val calToday = Calendar.getInstance().apply {
                set(Calendar.HOUR_OF_DAY, 0)
                set(Calendar.MINUTE, 0)
                set(Calendar.SECOND, 0)
                set(Calendar.MILLISECOND, 0)
            }
            val today0 = calToday.timeInMillis / 1000.0
            val diffDays = kotlin.math.floor((playedAtSec - today0) / 86400.0).toInt()
            return when {
                diffDays == 0 -> "Today"
                diffDays == -1 -> "Yesterday"
                diffDays in -6..-2 -> SimpleDateFormat("EEE", Locale.US).format(Date((playedAtSec * 1000).toLong()))
                else -> SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date((playedAtSec * 1000).toLong()))
            }
        }
        return addedDate?.takeIf { it.isNotBlank() } ?: "—"
    }

    fun fmtRemaining(tracks: List<Track>): String {
        val tot = tracks.sumOf { it.durSec ?: 0 }
        if (tot <= 0) return ""
        val m = tot / 60
        return if (m >= 60) "${m / 60} hr ${m % 60} min left" else "$m min left"
    }

    fun fmtListen(mins: Int): String =
        if (mins >= 60) "${mins / 60} hr ${mins % 60} min" else "$mins min"

    fun fmtEnds(tracks: List<Track>, elapsedSec: Int = 0, nowMs: Long = System.currentTimeMillis()): String {
        val tot = tracks.sumOf { it.durSec ?: 0 } - elapsedSec
        if (tot <= 60) return ""
        val endMs = nowMs + tot * 1000L
        return "ends " + SimpleDateFormat("HH:mm", Locale.US).format(Date(endMs))
    }

    fun fmtTotal(tracks: List<Track>): String {
        val n = tracks.size
        val tot = tracks.sumOf { it.durSec ?: 0 }
        if (tot <= 0) return "$n song${if (n == 1) "" else "s"}"
        val m = tot / 60
        return if (m >= 60) "$n songs, about ${m / 60} hr ${m % 60} min" else "$n songs, about $m min"
    }

    fun parseLrc(text: String?): List<SyncedLine> {
        if (text.isNullOrBlank()) return emptyList()
        val lineRe = Regex("""\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)""")
        val out = mutableListOf<SyncedLine>()
        for (raw in text.lines()) {
            val m = lineRe.matchEntire(raw.trimEnd()) ?: continue
            val min = m.groupValues[1].toIntOrNull() ?: continue
            val sec = m.groupValues[2].toDoubleOrNull() ?: continue
            out.add(SyncedLine(min * 60.0 + sec, m.groupValues[3]))
        }
        return out.sortedBy { it.timeSec }
    }

    fun parseDurationText(text: String?): Int? {
        if (text.isNullOrBlank()) return null
        val parts = text.trim().split(":").mapNotNull { it.toIntOrNull() }
        return when (parts.size) {
            2 -> parts[0] * 60 + parts[1]
            3 -> parts[0] * 3600 + parts[1] * 60 + parts[2]
            else -> null
        }
    }

    fun smartShuffle(
        tracks: List<Track>,
        previousArtist: String = "",
        recentIds: Set<String> = emptySet(),
        mode: ShuffleMode = ShuffleMode.SPREAD,
        plays: Map<String, PlayCount> = emptyMap(),
        rng: Random = Random.Default
    ): List<Track> {
        val buckets = linkedMapOf<String, MutableList<Track>>()
        for (t in tracks) {
            val a = normArtist(t.artist)
            buckets.getOrPut(a) { mutableListOf() }.add(t)
        }
        fun countOf(t: Track): Int = plays[t.id]?.count ?: 0
        for (group in buckets.values) {
            group.shuffle(rng)
            when (mode) {
                ShuffleMode.DISCOVERY -> group.sortWith(compareBy({ it.id in recentIds }, { countOf(it) }))
                ShuffleMode.MOOD -> group.sortWith(compareBy({ it.id in recentIds }, { -countOf(it) }))
                ShuffleMode.SPREAD -> group.sortBy { it.id in recentIds }
            }
        }
        val out = mutableListOf<Track>()
        var previous = normArtist(previousArtist)
        while (buckets.isNotEmpty()) {
            val choices = buckets.keys.filter { it != previous }.ifEmpty { buckets.keys.toList() }
            val chosenArtist = if (mode == ShuffleMode.DISCOVERY || mode == ShuffleMode.MOOD) {
                val sign = if (mode == ShuffleMode.DISCOVERY) 1.0 else -1.0
                choices.minBy { a ->
                    val grp = buckets.getValue(a)
                    sign * grp.sumOf { countOf(it) } / grp.size.toDouble() + rng.nextDouble() * 0.5
                }
            } else {
                val largest = choices.maxOf { buckets.getValue(it).size }
                choices.filter { buckets.getValue(it).size == largest }.random(rng)
            }
            val grp = buckets.getValue(chosenArtist)
            out.add(grp.removeAt(0))
            if (grp.isEmpty()) buckets.remove(chosenArtist)
            previous = chosenArtist
        }
        return out
    }

    fun sortTracks(
        tracks: List<Track>,
        mode: SortMode,
        plays: Map<String, PlayCount> = emptyMap()
    ): List<Track> {
        fun fold(s: String): String =
            Normalizer.normalize(s, Normalizer.Form.NFKC).lowercase(Locale.ROOT)
        return when (mode) {
            SortMode.DEFAULT -> tracks.toList()
            SortMode.PLAYS -> tracks.sortedByDescending { plays[it.id]?.count ?: 0 }
            SortMode.TITLE -> tracks.sortedWith(compareBy({ fold(it.title) }, { fold(it.artist) }))
            SortMode.ARTIST -> tracks.sortedWith(compareBy({ fold(it.artist) }, { fold(it.title) }))
            SortMode.ADDED -> tracks.sortedByDescending {
                it.playedAtSec ?: run {
                    if (it.addedDate != null) {
                        runCatching { SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(it.addedDate)?.time?.div(1000.0) }.getOrNull() ?: 0.0
                    } else 0.0
                }
            }
            SortMode.DURATION -> tracks.sortedByDescending { it.durSec ?: 0 }
        }
    }

    fun dailyMixes(
        liked: List<Track>,
        history: List<Track>,
        similarItems: List<Track>,
        playlists: List<Playlist>,
        plays: Map<String, PlayCount>,
        blockedIds: Set<String>,
        maxMixes: Int = 3
    ): List<DailyMix> {
        val pool = mutableListOf<Track>()
        val seen = blockedIds.toMutableSet()
        val sources = listOf(liked, history, similarItems) + playlists.map { it.tracks }
        for (src in sources) {
            for (t in src) {
                if (t.id !in seen && t.title.isNotBlank()) {
                    seen.add(t.id)
                    pool.add(t)
                }
            }
        }
        val byArtist = linkedMapOf<String, MutableList<Track>>()
        for (t in pool) {
            val a = normArtist(t.artist)
            if (a.isNotEmpty()) {
                byArtist.getOrPut(a) { mutableListOf() }.add(t)
            }
        }
        fun score(a: String): Int {
            val played = plays.values.filter { normArtist(it.artist) == a }.sumOf { it.count }
            return played * 2 + (byArtist[a]?.size ?: 0)
        }
        val sortedArtists = byArtist.keys.sortedWith(compareBy({ -score(it) }, { it }))
        val ranked = sortedArtists.filter { (byArtist[it]?.size ?: 0) >= 2 }.take(maxMixes)
        return ranked.mapIndexed { idx, a ->
            val tracks = byArtist.getValue(a).toMutableList()
            val extra = sortedArtists.filter { it != a && it !in ranked.take(idx) }.take(3)
            for (x in extra) {
                tracks.addAll(byArtist.getValue(x).take(3))
            }
            DailyMix(
                index = idx,
                name = "Daily Mix ${idx + 1}",
                artist = byArtist.getValue(a).first().artist,
                withArtists = extra.take(2).map { byArtist.getValue(it).first().artist },
                tracks = tracks
            )
        }
    }

    fun computeStats(
        liked: List<Track>,
        history: List<Track>,
        playlists: List<Playlist>,
        plays: Map<String, PlayCount>,
        firstPlayEpochSec: Double?
    ): StatsSummaryData {
        val nowSec = System.currentTimeMillis() / 1000.0
        val cutoff7d = nowSec - 7 * 86400.0

        val durMap = mutableMapOf<String, Int>()
        for (pool in listOf(liked, history) + playlists.map { it.tracks }) {
            for (t in pool) {
                val d = t.durSec
                if (d != null && d > 0) durMap.putIfAbsent(t.id, d)
            }
        }
        val totalSec = plays.entries.sumOf { (k, p) -> p.count.toLong() * (durMap[k] ?: 0) }
        val totalMinsText = if (totalSec < 60) "" else fmtListen((totalSec / 60).toInt())

        val calToday = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 0)
            set(Calendar.MINUTE, 0)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        val today0 = calToday.timeInMillis / 1000.0

        val dayCounts = IntArray(7)
        val daySec = DoubleArray(7)
        val hourBuckets = IntArray(4)
        val weekdayCounts = IntArray(7) // Mon=0..Sun=6
        var validWeekdayTotal = 0
        val daysSet = mutableSetOf<Int>()
        val lastPlayed = mutableMapOf<String, Double>()
        val repeatCounts = mutableMapOf<String, Int>()
        val repeatMeta = mutableMapOf<String, Track>()
        val weekArtistCounts = mutableMapOf<String, Int>()
        val weekArtistLast = mutableMapOf<String, Double>()
        var weekTotal = 0

        for (h in history) {
            val ts = h.playedAtSec ?: continue
            if (!ts.isFinite() || ts <= 0) continue

            val dayIdx = kotlin.math.floor((ts - today0) / 86400.0).toInt()
            daysSet.add(dayIdx)
            if (dayIdx in -6..0) {
                dayCounts[6 + dayIdx]++
                val d = h.durSec ?: 0
                if (d > 0) daySec[6 + dayIdx] += d.toDouble()
            }

            val cal = Calendar.getInstance().apply { timeInMillis = (ts * 1000).toLong() }
            val hr = cal.get(Calendar.HOUR_OF_DAY)
            val hb = when (hr) {
                in 5..11 -> 0
                in 12..16 -> 1
                in 17..21 -> 2
                else -> 3
            }
            hourBuckets[hb]++

            val dow = (cal.get(Calendar.DAY_OF_WEEK) + 5) % 7 // Mon=0..Sun=6
            weekdayCounts[dow]++
            validWeekdayTotal++

            if ((lastPlayed[h.id] ?: 0.0) < ts) lastPlayed[h.id] = ts

            if (ts >= cutoff7d) {
                weekTotal++
                repeatCounts[h.id] = (repeatCounts[h.id] ?: 0) + 1
                repeatMeta.putIfAbsent(h.id, h)
                val a = h.artist.trim()
                if (a.isNotEmpty()) {
                    weekArtistCounts[a] = (weekArtistCounts[a] ?: 0) + 1
                    weekArtistLast[a] = maxOf(weekArtistLast[a] ?: 0.0, ts)
                }
            }
        }

        val streak = run {
            var d = when {
                0 in daysSet -> 0
                -1 in daysSet -> -1
                else -> return@run 0
            }
            var n = 0
            while (d in daysSet) {
                n++
                d--
            }
            n
        }

        val dayLabels = listOf("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
        val weekDays = (0..6).map { i ->
            val cal = Calendar.getInstance().apply {
                timeInMillis = ((today0 - (6 - i) * 86400.0) * 1000).toLong()
            }
            val dow = (cal.get(Calendar.DAY_OF_WEEK) + 5) % 7
            StatsDay(dayLabels[dow], dayCounts[i], (daySec[i] / 60.0).toInt())
        }

        val biggestWeekday = if (validWeekdayTotal >= 10) {
            val order = (0..6).sortedByDescending { weekdayCounts[it] }
            if (weekdayCounts[order[0]] > 0 && weekdayCounts[order[0]] != weekdayCounts[order[1]]) {
                val names = listOf("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays")
                names[order[0]] to weekdayCounts[order[0]]
            } else null
        } else null

        val weekTopArtist = if (weekArtistCounts.isNotEmpty()) {
            val best = weekArtistCounts.keys.maxWith(compareBy({ weekArtistCounts.getValue(it) }, { weekArtistLast[it] ?: 0.0 }))
            best to weekArtistCounts.getValue(best)
        } else null

        val onRepeat = repeatCounts.entries
            .filter { it.value >= 2 }
            .sortedWith(compareBy({ -it.value }, { repeatMeta.getValue(it.key).title }))
            .take(6)
            .map { repeatMeta.getValue(it.key) to it.value }

        val totalPlays = plays.values.sumOf { it.count }
        val artistTotals = mutableMapOf<String, Int>()
        for (p in plays.values) {
            artistTotals[p.artist] = (artistTotals[p.artist] ?: 0) + p.count
        }
        val topArtists = artistTotals.entries
            .sortedWith(compareBy({ -it.value }, { it.key }))
            .take(6)
            .map { it.key to it.value }

        val topSongs = plays.values
            .sortedWith(compareBy({ -it.count }, { it.title }))
            .take(6)
            .map { p ->
                TopSongRow(p.trackId, p.title, p.artist, p.count, lastPlayed[p.trackId])
            }

        return StatsSummaryData(
            totalPlays = totalPlays,
            uniqueSongs = plays.size,
            totalMinutesText = totalMinsText,
            playsThisWeek = weekTotal,
            firstPlayEpochSec = firstPlayEpochSec,
            streakDays = streak,
            todayMinutes = weekDays.lastOrNull()?.minutes ?: 0,
            weekDays = weekDays,
            hourBuckets = listOf(
                HourBucket("Morning", hourBuckets[0]),
                HourBucket("Afternoon", hourBuckets[1]),
                HourBucket("Evening", hourBuckets[2]),
                HourBucket("Night", hourBuckets[3])
            ),
            biggestWeekday = biggestWeekday,
            weekTopArtist = weekTopArtist,
            onRepeat = onRepeat,
            topArtists = topArtists,
            topSongs = topSongs
        )
    }

    fun buildTracklistShareText(name: String, tracks: List<Track>): String {
        val sb = StringBuilder(name)
        tracks.forEachIndexed { idx, t ->
            sb.append("\n${idx + 1}. ${t.title} - ${t.artist}")
            if (t.durSec != null && t.durSec > 0) {
                sb.append(" (${fmtTime(t.durSec)})")
            }
        }
        return sb.toString()
    }

    fun buildStatsShareText(stats: StatsSummaryData): String {
        val lines = mutableListOf("My SpotUI stats")
        lines.add("${stats.totalPlays} plays \u00b7 ${stats.uniqueSongs} different songs")
        if (stats.totalMinutesText.isNotEmpty()) {
            lines.add("About ${stats.totalMinutesText} listened")
        }
        stats.topArtists.firstOrNull()?.let { (a, n) ->
            lines.add("Top artist: $a ($n plays)")
        }
        stats.topSongs.firstOrNull()?.let { s ->
            lines.add("Top song: ${s.title} - ${s.artist} (${s.count} plays)")
        }
        if (stats.streakDays > 0) lines.add("${stats.streakDays}-day streak")
        if (stats.playsThisWeek > 0) lines.add("${stats.playsThisWeek} plays this week")
        return lines.joinToString("\n")
    }
}
