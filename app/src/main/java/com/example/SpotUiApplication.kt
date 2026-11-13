package com.example

import android.app.Application
import com.example.data.local.PreferencesRepository
import com.example.data.local.SpotUiDatabase
import com.example.data.remote.YouTubeClient
import com.example.data.repository.SpotUiRepository

class SpotUiApplication : Application() {
    lateinit var repository: SpotUiRepository
        private set

    override fun onCreate() {
        super.onCreate()
        val db = SpotUiDatabase.build(this)
        val prefs = PreferencesRepository(this)
        val yt = YouTubeClient()
        repository = SpotUiRepository(db, prefs, yt)
    }
}
