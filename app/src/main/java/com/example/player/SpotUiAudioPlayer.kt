package com.example.player

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.PlaybackParams
import android.media.audiofx.Equalizer
import android.media.audiofx.LoudnessEnhancer
import android.os.PowerManager
import com.example.data.model.EqPreset
import com.example.data.model.Track
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class AudioPlayerState(
    val isIdle: Boolean = true,
    val isPaused: Boolean = false,
    val isLoading: Boolean = false,
    val positionSec: Double = 0.0,
    val durationSec: Double = 0.0,
    val volume: Int = 70,
    val speed: Float = 1.0f,
    val eqPreset: EqPreset = EqPreset.OFF,
    val volumeLeveling: Boolean = false,
    val repeatOne: Boolean = false
)

class SpotUiAudioPlayer(
    private val context: Context,
    private val onTrackCompleted: () -> Unit,
    private val onPlaybackError: (String) -> Unit
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private var mediaPlayer: MediaPlayer? = null
    private var equalizer: Equalizer? = null
    private var loudnessEnhancer: LoudnessEnhancer? = null
    private var progressJob: Job? = null
    private var pendingSeekSec: Double? = null
    private var runtimeGainScalar: Float = 1.0f
    private var currentStreamToken: Long = 0L

    private val _state = MutableStateFlow(AudioPlayerState())
    val state: StateFlow<AudioPlayerState> = _state.asStateFlow()

    private val focusRequest: AudioFocusRequest =
        AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .build()
            )
            .setOnAudioFocusChangeListener { change ->
                when (change) {
                    AudioManager.AUDIOFOCUS_LOSS,
                    AudioManager.AUDIOFOCUS_LOSS_TRANSIENT -> pause()
                    AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> applyVolumeNow(0.3f)
                    AudioManager.AUDIOFOCUS_GAIN -> applyVolumeNow(runtimeGainScalar)
                }
            }
            .build()

    fun loadStream(streamUrl: String, track: Track, token: Long, initialSeekSec: Double = 0.0) {
        currentStreamToken = token
        pendingSeekSec = initialSeekSec.takeIf { it > 0.5 }
        releasePlayer()
        _state.update {
            it.copy(
                isIdle = false,
                isPaused = false,
                isLoading = true,
                positionSec = initialSeekSec.coerceAtLeast(0.0),
                durationSec = (track.durSec ?: 0).toDouble()
            )
        }

        val mp = MediaPlayer().apply {
            setWakeMode(context, PowerManager.PARTIAL_WAKE_LOCK)
            setAudioAttributes(
                AudioAttributes.Builder()
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .build()
            )
            setOnPreparedListener { player ->
                if (token != currentStreamToken) {
                    runCatching { player.release() }
                    return@setOnPreparedListener
                }
                audioManager.requestAudioFocus(focusRequest)
                setupAudioEffects(player.audioSessionId)
                applySpeedNow(player, _state.value.speed)
                applyVolumeNow(runtimeGainScalar)
                player.isLooping = _state.value.repeatOne
                val seekTarget = pendingSeekSec
                pendingSeekSec = null
                if (seekTarget != null && seekTarget > 0.0) {
                    player.seekTo((seekTarget * 1000).toInt())
                }
                player.start()
                val durSec = (player.duration.takeIf { it > 0 }?.div(1000.0)) ?: (track.durSec ?: 0).toDouble()
                _state.update {
                    it.copy(
                        isIdle = false,
                        isPaused = false,
                        isLoading = false,
                        durationSec = durSec
                    )
                }
                startProgressLoop()
            }
            setOnCompletionListener {
                if (token != currentStreamToken) return@setOnCompletionListener
                if (_state.value.repeatOne) {
                    seekTo(0.0)
                    runCatching { start() }
                } else {
                    _state.update { it.copy(isIdle = true, isPaused = false, positionSec = it.durationSec) }
                    onTrackCompleted()
                }
            }
            setOnErrorListener { _, what, extra ->
                if (token != currentStreamToken) return@setOnErrorListener true
                _state.update { it.copy(isIdle = true, isPaused = false, isLoading = false) }
                onPlaybackError("Playback error ($what/$extra)")
                true
            }
        }
        mediaPlayer = mp
        runCatching {
            mp.setDataSource(streamUrl)
            mp.prepareAsync()
        }.onFailure { err ->
            _state.update { it.copy(isIdle = true, isPaused = false, isLoading = false) }
            onPlaybackError(err.message ?: "Stream failed to open")
        }
    }

    fun togglePlayPause() {
        val mp = mediaPlayer ?: return
        runCatching {
            if (mp.isPlaying) {
                mp.pause()
                _state.update { it.copy(isPaused = true) }
            } else {
                audioManager.requestAudioFocus(focusRequest)
                mp.start()
                _state.update { it.copy(isPaused = false, isIdle = false) }
            }
        }
    }

    fun play() {
        val mp = mediaPlayer ?: return
        runCatching {
            if (!mp.isPlaying) {
                audioManager.requestAudioFocus(focusRequest)
                mp.start()
                _state.update { it.copy(isPaused = false, isIdle = false) }
            }
        }
    }

    fun pause() {
        val mp = mediaPlayer ?: return
        runCatching {
            if (mp.isPlaying) {
                mp.pause()
            }
            _state.update { it.copy(isPaused = true) }
        }
    }

    fun seekTo(seconds: Double) {
        val mp = mediaPlayer ?: return
        val dur = _state.value.durationSec
        val target = if (dur > 0) seconds.coerceIn(0.0, dur) else seconds.coerceAtLeast(0.0)
        runCatching {
            mp.seekTo((target * 1000).toInt())
            _state.update { it.copy(positionSec = target) }
        }
    }

    fun seekRelative(deltaSec: Double) {
        seekTo(_state.value.positionSec + deltaSec)
    }

    fun setVolume(volume0To100: Int) {
        val clamped = volume0To100.coerceIn(0, 100)
        _state.update { it.copy(volume = clamped) }
        applyVolumeNow(runtimeGainScalar)
    }

    fun setFadeMultiplier(scalar: Float) {
        runtimeGainScalar = scalar.coerceIn(0f, 1f)
        applyVolumeNow(runtimeGainScalar)
    }

    fun setSpeed(speed: Float) {
        _state.update { it.copy(speed = speed) }
        mediaPlayer?.let { applySpeedNow(it, speed) }
    }

    fun setEqPreset(preset: EqPreset) {
        _state.update { it.copy(eqPreset = preset) }
        applyEqualizerPreset(preset)
    }

    fun setVolumeLeveling(enabled: Boolean) {
        _state.update { it.copy(volumeLeveling = enabled) }
        runCatching {
            loudnessEnhancer?.enabled = enabled
            if (enabled) loudnessEnhancer?.setTargetGain(350)
        }
    }

    fun setRepeatOne(repeatOne: Boolean) {
        _state.update { it.copy(repeatOne = repeatOne) }
        runCatching { mediaPlayer?.isLooping = repeatOne }
    }

    fun setLoading(loading: Boolean) {
        _state.update { it.copy(isLoading = loading) }
    }

    fun stopAndReset() {
        currentStreamToken++
        releasePlayer()
        _state.update { it.copy(isIdle = true, isPaused = false, isLoading = false, positionSec = 0.0) }
    }

    private fun applyVolumeNow(multiplier: Float) {
        val vol = (_state.value.volume / 100f) * multiplier
        runCatching { mediaPlayer?.setVolume(vol, vol) }
    }

    private fun applySpeedNow(mp: MediaPlayer, speed: Float) {
        runCatching {
            val wasPlaying = mp.isPlaying
            val params = PlaybackParams().setSpeed(speed)
            mp.playbackParams = params
            if (!wasPlaying && _state.value.isPaused) {
                mp.pause()
            }
        }
    }

    private fun setupAudioEffects(audioSessionId: Int) {
        releaseEffects()
        runCatching {
            equalizer = Equalizer(0, audioSessionId).apply {
                enabled = true
            }
            applyEqualizerPreset(_state.value.eqPreset)
        }
        runCatching {
            loudnessEnhancer = LoudnessEnhancer(audioSessionId).apply {
                setTargetGain(350)
                enabled = _state.value.volumeLeveling
            }
        }
    }

    private fun applyEqualizerPreset(preset: EqPreset) {
        val eq = equalizer ?: return
        runCatching {
            val numBands = eq.numberOfBands.toInt()
            if (numBands <= 0) return
            val range = eq.bandLevelRange
            val minLv = range[0].toInt()
            val maxLv = range[1].toInt()
            val boost = ((maxLv - minLv) * 0.35).toInt()
            for (b in 0 until numBands) {
                val freqHz = eq.getCenterFreq(b.toShort()) / 1000
                val level = when (preset) {
                    EqPreset.OFF -> 0
                    EqPreset.BASS -> if (freqHz < 250) boost else if (freqHz < 500) boost / 2 else 0
                    EqPreset.VOCAL -> if (freqHz in 800..4000) boost else -boost / 4
                    EqPreset.TREBLE -> if (freqHz > 3500) boost else if (freqHz > 1800) boost / 2 else 0
                }.coerceIn(minLv, maxLv).toShort()
                eq.setBandLevel(b.toShort(), level)
            }
        }
    }

    private fun startProgressLoop() {
        progressJob?.cancel()
        progressJob = scope.launch {
            while (isActive) {
                val mp = mediaPlayer
                if (mp != null && !_state.value.isIdle && !_state.value.isLoading) {
                    runCatching {
                        val posSec = mp.currentPosition / 1000.0
                        val durMs = mp.duration
                        val durSec = if (durMs > 0) durMs / 1000.0 else _state.value.durationSec
                        _state.update {
                            it.copy(
                                positionSec = posSec,
                                durationSec = durSec,
                                isPaused = !mp.isPlaying
                            )
                        }
                    }
                }
                delay(350L)
            }
        }
    }

    private fun releaseEffects() {
        runCatching { equalizer?.release() }
        equalizer = null
        runCatching { loudnessEnhancer?.release() }
        loudnessEnhancer = null
    }

    fun releasePlayer() {
        progressJob?.cancel()
        progressJob = null
        releaseEffects()
        runCatching { mediaPlayer?.stop() }
        runCatching { mediaPlayer?.release() }
        mediaPlayer = null
    }
}
