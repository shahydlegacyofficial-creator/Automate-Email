package com.travelessence.emailstudio

import android.app.Application
import com.travelessence.emailstudio.campaign.CampaignController

class App : Application() {
    lateinit var state: AppState
        private set
    lateinit var campaign: CampaignController
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this
        state = AppState(this)
        campaign = CampaignController(this, state)
    }

    companion object {
        lateinit var instance: App
            private set
    }
}
