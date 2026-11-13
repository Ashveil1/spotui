package com.example.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.LocalFireDepartment
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.R
import com.example.data.model.NavDest
import com.example.data.model.Track
import com.example.data.util.SpotUiTextUtils
import com.example.ui.theme.LocalSpotColors
import com.example.ui.viewmodel.SpotUiState
import com.example.ui.viewmodel.SpotUiViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun StatsScreen(
    state: SpotUiState,
    viewModel: SpotUiViewModel,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val stats = state.stats
    val sinceLabel = remember(stats.firstPlayEpochSec) {
        stats.firstPlayEpochSec?.let {
            "since " + SimpleDateFormat("MMM d, yyyy", Locale.US).format(Date((it * 1000).toLong()))
        } ?: "No plays recorded yet"
    }

    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("stats_screen"),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        // Header
        item {
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = stringResource(R.string.stats_title),
                        style = MaterialTheme.typography.headlineSmall,
                        color = spot.textPrimary,
                        fontWeight = FontWeight.Bold
                    )
                    Text(sinceLabel, style = MaterialTheme.typography.bodySmall, color = spot.textDim)
                }
                OutlinedButton(
                    onClick = { viewModel.copyStatsSummary() },
                    modifier = Modifier.testTag("stats_copy_btn")
                ) {
                    Icon(Icons.Rounded.ContentCopy, null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Share stats")
                }
            }
        }

        // Key Metric Cards
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    StatCard("Total plays", "${stats.totalPlays}", Modifier.weight(1f))
                    StatCard("Unique songs", "${stats.uniqueSongs}", Modifier.weight(1f))
                }
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    StatCard("Listened", stats.totalMinutesText.ifEmpty { "0 min" }, Modifier.weight(1f))
                    StatCard("This week", "${stats.playsThisWeek} plays", Modifier.weight(1f))
                }
                if (stats.streakDays > 0 || stats.biggestWeekday != null || stats.weekTopArtist != null) {
                    Surface(
                        color = spot.hover,
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth().border(1.dp, spot.divider, RoundedCornerShape(12.dp))
                    ) {
                        Column(
                            modifier = Modifier.padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            if (stats.streakDays > 0) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Rounded.LocalFireDepartment, null, tint = spot.accent, modifier = Modifier.size(18.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text(
                                        text = "${stats.streakDays}-day listening streak \u00b7 ${stats.todayMinutes} min today",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = spot.textPrimary
                                    )
                                }
                            }
                            stats.biggestWeekday?.let { (day, cnt) ->
                                Text("Biggest day: $day ($cnt plays)", style = MaterialTheme.typography.bodySmall, color = spot.textDim)
                            }
                            stats.weekTopArtist?.let { (art, cnt) ->
                                Text(
                                    text = "Top artist this week: $art ($cnt plays)",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = spot.accent,
                                    modifier = Modifier.clickable { viewModel.navigateTo(NavDest.Artist(art)) }
                                )
                            }
                        }
                    }
                }
            }
        }

        // Last 7 Days Bar Chart
        item {
            val maxPlays = (stats.weekDays.maxOfOrNull { it.plays } ?: 1).coerceAtLeast(1)
            Surface(
                color = spot.hover,
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth().border(1.dp, spot.divider, RoundedCornerShape(14.dp))
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("LAST 7 DAYS", style = MaterialTheme.typography.labelMedium, color = spot.textDim, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(14.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth().height(128.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.Bottom
                    ) {
                        stats.weekDays.forEach { d ->
                            val frac = (d.plays / maxPlays.toFloat()).coerceIn(0f, 1f)
                            Column(
                                modifier = Modifier.weight(1f),
                                horizontalAlignment = Alignment.CenterHorizontally,
                                verticalArrangement = Arrangement.Bottom
                            ) {
                                Text(
                                    text = if (d.plays > 0) "${d.plays}" else "",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = spot.textDim
                                )
                                Spacer(Modifier.height(4.dp))
                                Box(
                                    modifier = Modifier
                                        .width(20.dp)
                                        .height(74.dp),
                                    contentAlignment = Alignment.BottomCenter
                                ) {
                                    Box(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .fillMaxHeight(if (d.plays == 0) 0.05f else frac.coerceAtLeast(0.12f))
                                            .clip(RoundedCornerShape(topStart = 5.dp, topEnd = 5.dp))
                                            .background(if (d.plays == 0) spot.divider else spot.accent)
                                    )
                                }
                                Spacer(Modifier.height(6.dp))
                                Text(d.label, style = MaterialTheme.typography.labelSmall, color = spot.textPrimary)
                                Text(
                                    text = if (d.minutes > 0) "${d.minutes}m" else "",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = spot.textFaint
                                )
                            }
                        }
                    }
                }
            }
        }

        // Time of Day Breakdown
        item {
            val maxHour = (stats.hourBuckets.maxOfOrNull { it.count } ?: 1).coerceAtLeast(1)
            Surface(
                color = spot.hover,
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth().border(1.dp, spot.divider, RoundedCornerShape(14.dp))
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text("TIME OF DAY", style = MaterialTheme.typography.labelMedium, color = spot.textDim, fontWeight = FontWeight.Bold)
                    stats.hourBuckets.forEach { b ->
                        HorizontalBarRow(
                            label = b.label,
                            count = b.count,
                            maxCount = maxHour,
                            onClick = null
                        )
                    }
                }
            }
        }

        // On Repeat This Week
        if (stats.onRepeat.isNotEmpty()) {
            item {
                val repeatTracks = stats.onRepeat.map { it.first }
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("ON REPEAT THIS WEEK", style = MaterialTheme.typography.labelMedium, color = spot.textDim, fontWeight = FontWeight.Bold)
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        stats.onRepeat.forEachIndexed { idx, (track, count) ->
                            Surface(
                                color = spot.hover,
                                shape = RoundedCornerShape(10.dp),
                                modifier = Modifier
                                    .border(1.dp, spot.divider, RoundedCornerShape(10.dp))
                                    .clickable { viewModel.play(repeatTracks, idx, "On repeat", startRadioAfter = true) }
                            ) {
                                Text(
                                    text = "${track.title} \u00b7 ${count}x",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = spot.textPrimary,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)
                                )
                            }
                        }
                    }
                }
            }
        }

        // Top Artists
        if (stats.topArtists.isNotEmpty()) {
            item {
                val maxA = stats.topArtists.first().second.coerceAtLeast(1)
                Surface(
                    color = spot.hover,
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.fillMaxWidth().border(1.dp, spot.divider, RoundedCornerShape(14.dp))
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        Text("TOP ARTISTS", style = MaterialTheme.typography.labelMedium, color = spot.textDim, fontWeight = FontWeight.Bold)
                        stats.topArtists.forEach { (artist, cnt) ->
                            HorizontalBarRow(
                                label = artist,
                                count = cnt,
                                maxCount = maxA,
                                onClick = { viewModel.navigateTo(NavDest.Artist(artist)) }
                            )
                        }
                    }
                }
            }
        }

        // Top Songs
        if (stats.topSongs.isNotEmpty()) {
            item {
                val maxS = stats.topSongs.first().count.coerceAtLeast(1)
                Surface(
                    color = spot.hover,
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.fillMaxWidth().border(1.dp, spot.divider, RoundedCornerShape(14.dp))
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        Text("TOP SONGS", style = MaterialTheme.typography.labelMedium, color = spot.textDim, fontWeight = FontWeight.Bold)
                        stats.topSongs.forEach { row ->
                            val ago = SpotUiTextUtils.fmtAgo(row.lastPlayedSec)
                            val label = "${row.title} \u2014 ${row.artist}" + if (ago.isNotEmpty()) " ($ago)" else ""
                            HorizontalBarRow(
                                label = label,
                                count = row.count,
                                maxCount = maxS,
                                onClick = {
                                    val found = (state.library.liked + state.library.history + state.library.playlists.flatMap { it.tracks })
                                        .firstOrNull { it.id == row.trackId }
                                        ?: Track(id = row.trackId, title = row.title, artist = row.artist)
                                    viewModel.play(listOf(found), 0, "Top songs", startRadioAfter = true)
                                }
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun StatCard(label: String, value: String, modifier: Modifier = Modifier) {
    val spot = LocalSpotColors.current
    Surface(
        color = spot.hover,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier.border(1.dp, spot.divider, RoundedCornerShape(12.dp))
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text(label, style = MaterialTheme.typography.labelSmall, color = spot.textDim)
            Spacer(Modifier.height(4.dp))
            Text(value, style = MaterialTheme.typography.titleLarge, color = spot.textPrimary, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun HorizontalBarRow(
    label: String,
    count: Int,
    maxCount: Int,
    onClick: (() -> Unit)?
) {
    val spot = LocalSpotColors.current
    val frac = (count / maxCount.toFloat()).coerceIn(0f, 1f)
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(vertical = 2.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = label,
                style = MaterialTheme.typography.bodySmall,
                color = spot.textPrimary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f)
            )
            Spacer(Modifier.width(8.dp))
            Text("$count", style = MaterialTheme.typography.labelSmall, color = spot.textDim)
        }
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(7.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(spot.raised)
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth(if (count == 0) 0.02f else frac.coerceAtLeast(0.05f))
                    .fillMaxHeight()
                    .clip(RoundedCornerShape(4.dp))
                    .background(if (count == 0) spot.divider else spot.accent)
            )
        }
    }
}
