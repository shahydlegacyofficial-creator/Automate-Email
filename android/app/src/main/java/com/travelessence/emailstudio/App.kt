package com.travelessence.emailstudio

import android.app.Activity
import android.app.Application
import android.os.Bundle
import com.travelessence.emailstudio.agent.AgentServer
import com.travelessence.emailstudio.campaign.CampaignController
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

class App : Application() {
    lateinit var state: AppState
        private set
    lateinit var campaign: CampaignController
        private set
    lateinit var agent: AgentServer
        private set

    /** True while one of our screens is visible (Android only allows starting a campaign then). */
    @Volatile var visible = false
        private set
    private var started = 0

    override fun onCreate() {
        super.onCreate()
        instance = this
        state = AppState(this)
        campaign = CampaignController(this, state)
        agent = AgentServer(this, state, campaign)
        registerActivityLifecycleCallbacks(object : ActivityLifecycleCallbacks {
            override fun onActivityStarted(activity: Activity) { started++; visible = true }
            override fun onActivityStopped(activity: Activity) { started--; visible = started > 0 }
            override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {}
            override fun onActivityResumed(activity: Activity) {}
            override fun onActivityPaused(activity: Activity) {}
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) {}
            override fun onActivityDestroyed(activity: Activity) {}
        })
        state.scope.launch {
            state.settings.map { Triple(it.aiEnabled, it.aiPort, it.aiLan) }.distinctUntilChanged().collect { agent.apply() }
        }
    }

    companion object {
        lateinit var instance: App
            private set
    }
}
