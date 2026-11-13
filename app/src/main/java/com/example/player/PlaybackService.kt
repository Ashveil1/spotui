package com.example.player

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.MediaMetadata
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Binder
import android.os.IBinder
import com.example.MainActivity
import com.example.R
import com.example.data.model.Track

class PlaybackService : Service() {

    inner class LocalBinder : Binder() {
        fun getService(): PlaybackService = this@PlaybackService
    }

    private val binder = LocalBinder()
    private lateinit var mediaSession: MediaSession
    private lateinit var notificationManager: NotificationManager

    var onActionToggle: (() -> Unit)? = null
    var onActionNext: (() -> Unit)? = null
    var onActionPrev: (() -> Unit)? = null
    var onActionSeek: ((Double) -> Unit)? = null

    private var currentTrack: Track? = null
    private var isPlaying: Boolean = false
    private var positionMs: Long = 0L
    private var durationMs: Long = 0L

    override fun onCreate() {
        super.onCreate()
        notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        ensureChannel()
        mediaSession = MediaSession(this, "SpotUIMediaSession").apply {
            setCallback(object : MediaSession.Callback() {
                override fun onPlay() { onActionToggle?.invoke() }
                override fun onPause() { onActionToggle?.invoke() }
                override fun onSkipToNext() { onActionNext?.invoke() }
                override fun onSkipToPrevious() { onActionPrev?.invoke() }
                override fun onSeekTo(pos: Long) { onActionSeek?.invoke(pos / 1000.0) }
            })
            isActive = true
        }
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_TOGGLE -> onActionToggle?.invoke()
            ACTION_NEXT -> onActionNext?.invoke()
            ACTION_PREV -> onActionPrev?.invoke()
            ACTION_STOP -> {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    fun updatePlaybackNotification(
        track: Track?,
        playing: Boolean,
        posSec: Double,
        durSec: Double
    ) {
        currentTrack = track
        isPlaying = playing
        positionMs = (posSec * 1000).toLong().coerceAtLeast(0L)
        durationMs = (durSec * 1000).toLong().coerceAtLeast(0L)

        if (track == null) return

        val stateCode = if (playing) PlaybackState.STATE_PLAYING else PlaybackState.STATE_PAUSED
        val pbState = PlaybackState.Builder()
            .setActions(
                PlaybackState.ACTION_PLAY or
                    PlaybackState.ACTION_PAUSE or
                    PlaybackState.ACTION_PLAY_PAUSE or
                    PlaybackState.ACTION_SKIP_TO_NEXT or
                    PlaybackState.ACTION_SKIP_TO_PREVIOUS or
                    PlaybackState.ACTION_SEEK_TO
            )
            .setState(stateCode, positionMs, 1.0f)
            .build()
        mediaSession.setPlaybackState(pbState)

        val meta = MediaMetadata.Builder()
            .putString(MediaMetadata.METADATA_KEY_TITLE, track.title)
            .putString(MediaMetadata.METADATA_KEY_ARTIST, track.artist)
            .putLong(MediaMetadata.METADATA_KEY_DURATION, durationMs)
            .build()
        mediaSession.setMetadata(meta)

        val notif = buildNotification(track, playing)
        runCatching {
            startForeground(NOTIF_ID, notif)
        }.onFailure {
            runCatching { notificationManager.notify(NOTIF_ID, notif) }
        }
    }

    private fun buildNotification(track: Track, playing: Boolean): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val prevPending = servicePendingIntent(1, ACTION_PREV)
        val togglePending = servicePendingIntent(2, ACTION_TOGGLE)
        val nextPending = servicePendingIntent(3, ACTION_NEXT)

        val toggleIcon = if (playing) android.R.drawable.ic_media_pause else android.R.drawable.ic_media_play
        val toggleLabel = if (playing) "Pause" else "Play"

        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle(track.title)
            .setContentText(track.artist)
            .setSmallIcon(R.drawable.ic_music_note_notif)
            .setContentIntent(openIntent)
            .setOngoing(playing)
            .addAction(Notification.Action.Builder(android.R.drawable.ic_media_previous, "Previous", prevPending).build())
            .addAction(Notification.Action.Builder(toggleIcon, toggleLabel, togglePending).build())
            .addAction(Notification.Action.Builder(android.R.drawable.ic_media_next, "Next", nextPending).build())
            .setStyle(
                Notification.MediaStyle()
                    .setMediaSession(mediaSession.sessionToken)
                    .setShowActionsInCompactView(0, 1, 2)
            )
            .build()
    }

    private fun servicePendingIntent(reqCode: Int, action: String): PendingIntent {
        val intent = Intent(this, PlaybackService::class.java).setAction(action)
        return PendingIntent.getService(
            this,
            reqCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    private fun ensureChannel() {
        val ch = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notif_channel_name),
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = getString(R.string.notif_channel_desc)
            setShowBadge(false)
        }
        notificationManager.createNotificationChannel(ch)
    }

    override fun onDestroy() {
        mediaSession.isActive = false
        mediaSession.release()
        super.onDestroy()
    }

    companion object {
        const val CHANNEL_ID = "spotui_playback"
        const val NOTIF_ID = 1001
        const val ACTION_TOGGLE = "com.example.spotui.TOGGLE"
        const val ACTION_NEXT = "com.example.spotui.NEXT"
        const val ACTION_PREV = "com.example.spotui.PREV"
        const val ACTION_STOP = "com.example.spotui.STOP"
    }
}
