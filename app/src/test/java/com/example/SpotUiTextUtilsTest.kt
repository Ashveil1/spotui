package com.example

import com.example.data.model.PlayCount
import com.example.data.model.Playlist
import com.example.data.model.ShuffleMode
import com.example.data.model.SortMode
import com.example.data.model.Track
import com.example.data.util.SpotUiTextUtils
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

class SpotUiTextUtilsTest {

    @Test
    fun cleanTitle_stripsOfficialVideoTags() {
        assertEquals("Midnight City", SpotUiTextUtils.cleanTitle("Midnight City (Official Music Video)"))
        assertEquals("Time", SpotUiTextUtils.cleanTitle("Time [Official Audio] - HQ Audio"))
        assertEquals("Unknown title", SpotUiTextUtils.cleanTitle("   "))
    }

    @Test
    fun splitArtist_handlesTopicAndDashPrefix() {
        val (a1, t1) = SpotUiTextUtils.splitArtist("Nights", "Frank Ocean - Topic")
        assertEquals("Frank Ocean", a1)
        assertEquals("Nights", t1)

        val (a2, t2) = SpotUiTextUtils.splitArtist("Daft Punk - One More Time", "DaftPunkVEVO")
        assertEquals("Daft Punk", a2)
        assertEquals("One More Time", t2)
    }

    @Test
    fun isRealSong_filtersMixesAndLongCompilations() {
        assertTrue(SpotUiTextUtils.isRealSong(Track("1", "Dreams", "Fleetwood Mac", durSec = 254)))
        assertFalse(SpotUiTextUtils.isRealSong(Track("2", "Best of 80s Mix", "Various", durSec = 200)))
        assertFalse(SpotUiTextUtils.isRealSong(Track("3", "Extended Ambient", "Artist", durSec = 900)))
    }

    @Test
    fun parseLrc_parsesTimestampsInOrder() {
        val lrc = """
            [00:12.50]Second line
            [00:05.00]First line
            [01:02.00]Third line
        """.trimIndent()
        val parsed = SpotUiTextUtils.parseLrc(lrc)
        assertEquals(3, parsed.size)
        assertEquals(5.0, parsed[0].timeSec, 0.01)
        assertEquals("First line", parsed[0].text)
        assertEquals(12.5, parsed[1].timeSec, 0.01)
        assertEquals(62.0, parsed[2].timeSec, 0.01)
    }

    @Test
    fun smartShuffle_respectsDiscoveryOrderingAndSpreadsArtists() {
        val tracks = listOf(
            Track("a", "Song A", "Artist 1"),
            Track("b", "Song B", "Artist 2"),
            Track("c", "Song C", "Artist 1"),
            Track("d", "Song D", "Artist 3")
        )
        val plays = mapOf(
            "a" to PlayCount("a", "Song A", "Artist 1", 10),
            "b" to PlayCount("b", "Song B", "Artist 2", 0),
            "c" to PlayCount("c", "Song C", "Artist 1", 8),
            "d" to PlayCount("d", "Song D", "Artist 3", 1)
        )
        val shuffled = SpotUiTextUtils.smartShuffle(
            tracks = tracks,
            previousArtist = "Artist 1",
            mode = ShuffleMode.DISCOVERY,
            plays = plays,
            rng = Random(42)
        )
        assertEquals(4, shuffled.size)
        assertEquals(setOf("a", "b", "c", "d"), shuffled.map { it.id }.toSet())
        assertTrue(shuffled.first().artist != "Artist 1")
    }

    @Test
    fun sortTracks_and_dailyMixes_workCorrectly() {
        val t1 = Track("1", "Zebra", "Beta", durSec = 120)
        val t2 = Track("2", "Alpha", "Alpha", durSec = 300)
        val t3 = Track("3", "Middle", "Alpha", durSec = 210)
        val sortedTitle = SpotUiTextUtils.sortTracks(listOf(t1, t2, t3), SortMode.TITLE)
        assertEquals(listOf("2", "3", "1"), sortedTitle.map { it.id })

        val mixes = SpotUiTextUtils.dailyMixes(
            liked = listOf(t1, t2, t3),
            history = emptyList(),
            similarItems = emptyList(),
            playlists = listOf(Playlist(1, "Pl", listOf(t1, t2, t3))),
            plays = emptyMap(),
            blockedIds = emptySet()
        )
        assertTrue(mixes.isNotEmpty())
        assertEquals("Daily Mix 1", mixes.first().name)
    }

    @Test
    fun artFamilyIndex_isDeterministic() {
        val idx1 = SpotUiTextUtils.artFamilyIndex("dQw4w9WgXcQ")
        val idx2 = SpotUiTextUtils.artFamilyIndex("dQw4w9WgXcQ")
        assertEquals(idx1, idx2)
        assertTrue(idx1 in 0 until SpotUiTextUtils.COVER_FAMILIES.size)
    }
}
