package com.example.data.local

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.room.Transaction
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "liked_tracks")
data class LikedTrackEntity(
    @PrimaryKey val id: String,
    val title: String,
    val artist: String,
    val durSec: Int?,
    val url: String,
    val channel: String,
    val addedDate: String,
    val sortOrder: Long
)

@Entity(tableName = "playlists")
data class PlaylistEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val name: String,
    val pinned: Boolean = false,
    val enhanced: Boolean = false,
    val sortOrder: Long = System.currentTimeMillis()
)

@Entity(
    tableName = "playlist_tracks",
    foreignKeys = [
        ForeignKey(
            entity = PlaylistEntity::class,
            parentColumns = ["id"],
            childColumns = ["playlistId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index("playlistId")]
)
data class PlaylistTrackEntity(
    @PrimaryKey(autoGenerate = true) val rowId: Long = 0,
    val playlistId: Long,
    val trackId: String,
    val title: String,
    val artist: String,
    val durSec: Int?,
    val url: String,
    val channel: String,
    val addedDate: String?,
    val isEnhanced: Boolean = false,
    val position: Int
)

@Entity(tableName = "history_entries")
data class HistoryEntryEntity(
    @PrimaryKey val id: String,
    val title: String,
    val artist: String,
    val durSec: Int?,
    val url: String,
    val channel: String,
    val playedAtSec: Double
)

@Entity(tableName = "play_counts")
data class PlayCountEntity(
    @PrimaryKey val trackId: String,
    val title: String,
    val artist: String,
    val count: Int
)

@Entity(tableName = "recent_searches")
data class RecentSearchEntity(
    @PrimaryKey val query: String,
    val searchedAtMs: Long
)

@Entity(tableName = "blocked_tracks")
data class BlockedTrackEntity(
    @PrimaryKey val trackId: String
)

@Entity(tableName = "followed_channels")
data class FollowedChannelEntity(
    @PrimaryKey val channelId: String,
    val name: String,
    val followedAtMs: Long
)

@Entity(tableName = "lyrics_cache")
data class LyricsCacheEntity(
    @PrimaryKey val trackId: String,
    val plainText: String?,
    val syncedJson: String?,
    val fetchedAtEpochSec: Long
)

@Dao
interface LikedDao {
    @Query("SELECT * FROM liked_tracks ORDER BY sortOrder DESC")
    fun observeAll(): Flow<List<LikedTrackEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: LikedTrackEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(items: List<LikedTrackEntity>)

    @Query("DELETE FROM liked_tracks WHERE id = :id")
    suspend fun deleteById(id: String)
}

@Dao
interface PlaylistDao {
    @Query("SELECT * FROM playlists ORDER BY pinned DESC, sortOrder ASC")
    fun observePlaylists(): Flow<List<PlaylistEntity>>

    @Query("SELECT * FROM playlist_tracks ORDER BY playlistId ASC, position ASC")
    fun observeAllPlaylistTracks(): Flow<List<PlaylistTrackEntity>>

    @Query("SELECT * FROM playlist_tracks WHERE playlistId = :playlistId ORDER BY position ASC")
    suspend fun getTracksForPlaylist(playlistId: Long): List<PlaylistTrackEntity>

    @Insert
    suspend fun insertPlaylist(playlist: PlaylistEntity): Long

    @Update
    suspend fun updatePlaylist(playlist: PlaylistEntity)

    @Query("UPDATE playlists SET name = :name WHERE id = :id")
    suspend fun updatePlaylistName(id: Long, name: String)

    @Query("UPDATE playlists SET pinned = :pinned WHERE id = :id")
    suspend fun updatePlaylistPinned(id: Long, pinned: Boolean)

    @Query("UPDATE playlists SET enhanced = :enhanced WHERE id = :id")
    suspend fun updatePlaylistEnhanced(id: Long, enhanced: Boolean)

    @Query("DELETE FROM playlists WHERE id = :playlistId")
    suspend fun deletePlaylist(playlistId: Long)

    @Insert
    suspend fun insertPlaylistTracks(tracks: List<PlaylistTrackEntity>)

    @Query("DELETE FROM playlist_tracks WHERE playlistId = :playlistId")
    suspend fun clearPlaylistTracks(playlistId: Long)

    @Transaction
    suspend fun replacePlaylistTracks(playlistId: Long, tracks: List<PlaylistTrackEntity>) {
        clearPlaylistTracks(playlistId)
        insertPlaylistTracks(tracks)
    }
}

@Dao
interface HistoryDao {
    @Query("SELECT * FROM history_entries ORDER BY playedAtSec DESC LIMIT 30")
    fun observeRecent(): Flow<List<HistoryEntryEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entry: HistoryEntryEntity)

    @Query("DELETE FROM history_entries WHERE id NOT IN (SELECT id FROM history_entries ORDER BY playedAtSec DESC LIMIT 30)")
    suspend fun trimTo30()

    @Query("DELETE FROM history_entries")
    suspend fun clearAll()
}

@Dao
interface PlayCountDao {
    @Query("SELECT * FROM play_counts")
    fun observeAll(): Flow<List<PlayCountEntity>>

    @Query("SELECT * FROM play_counts WHERE trackId = :id LIMIT 1")
    suspend fun getById(id: String): PlayCountEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: PlayCountEntity)

    @Query("DELETE FROM play_counts")
    suspend fun clearAll()
}

@Dao
interface RecentSearchDao {
    @Query("SELECT * FROM recent_searches ORDER BY searchedAtMs DESC LIMIT 8")
    fun observeAll(): Flow<List<RecentSearchEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: RecentSearchEntity)

    @Query("DELETE FROM recent_searches WHERE `query` = :query")
    suspend fun delete(query: String)

    @Query("DELETE FROM recent_searches WHERE `query` NOT IN (SELECT `query` FROM recent_searches ORDER BY searchedAtMs DESC LIMIT 8)")
    suspend fun trimTo8()
}

@Dao
interface BlockedDao {
    @Query("SELECT * FROM blocked_tracks")
    fun observeAll(): Flow<List<BlockedTrackEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun block(item: BlockedTrackEntity)

    @Query("DELETE FROM blocked_tracks WHERE trackId = :trackId")
    suspend fun unblock(trackId: String)
}

@Dao
interface LyricsDao {
    @Query("SELECT * FROM lyrics_cache")
    fun observeAll(): Flow<List<LyricsCacheEntity>>

    @Query("SELECT * FROM lyrics_cache WHERE trackId = :trackId LIMIT 1")
    suspend fun get(trackId: String): LyricsCacheEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: LyricsCacheEntity)

    @Query("DELETE FROM lyrics_cache WHERE trackId NOT IN (SELECT trackId FROM lyrics_cache ORDER BY fetchedAtEpochSec DESC LIMIT 400)")
    suspend fun trimTo400()
}

@Dao
interface FollowedChannelDao {
    @Query("SELECT * FROM followed_channels ORDER BY followedAtMs DESC")
    fun observeAll(): Flow<List<FollowedChannelEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: FollowedChannelEntity)

    @Query("DELETE FROM followed_channels WHERE channelId = :channelId")
    suspend fun deleteById(channelId: String)
}

@Database(
    entities = [
        LikedTrackEntity::class,
        PlaylistEntity::class,
        PlaylistTrackEntity::class,
        HistoryEntryEntity::class,
        PlayCountEntity::class,
        RecentSearchEntity::class,
        BlockedTrackEntity::class,
        LyricsCacheEntity::class,
        FollowedChannelEntity::class
    ],
    version = 2,
    exportSchema = false
)
abstract class SpotUiDatabase : RoomDatabase() {
    abstract fun likedDao(): LikedDao
    abstract fun playlistDao(): PlaylistDao
    abstract fun historyDao(): HistoryDao
    abstract fun playCountDao(): PlayCountDao
    abstract fun recentSearchDao(): RecentSearchDao
    abstract fun blockedDao(): BlockedDao
    abstract fun lyricsDao(): LyricsDao
    abstract fun followedChannelDao(): FollowedChannelDao

    companion object {
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS `followed_channels` (" +
                        "`channelId` TEXT NOT NULL, " +
                        "`name` TEXT NOT NULL, " +
                        "`followedAtMs` INTEGER NOT NULL, " +
                        "PRIMARY KEY(`channelId`))"
                )
            }
        }

        fun build(context: Context): SpotUiDatabase =
            Room.databaseBuilder(context, SpotUiDatabase::class.java, "spotui_library.db")
                .addMigrations(MIGRATION_1_2)
                .build()
    }
}
