package com.codysafe.guard

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder

/** 앱을 닫아도 녹음 폴더를 15초마다 확인합니다. 주기 작업은 최소 간격이 15분이라 따로 둡니다. */
class FolderWatchService : Service() {
    private lateinit var store: Store
    private lateinit var worker: HandlerThread
    private lateinit var handler: Handler

    private val tick = object : Runnable {
        override fun run() {
            if (store.token.isEmpty() || store.folder.isEmpty()) {
                stopSelf()
                return
            }
            attempt { Sync.uploadNewFiles(this@FolderWatchService, store) }
            attempt { Sync.checkAlerts(this@FolderWatchService, store) }
            attempt { Sync.checkLock(this@FolderWatchService, store) }
            handler.postDelayed(this, POLL_MS)
        }
    }

    /** 네트워크 오류 하나로 감시가 멈추지 않게 하고 다음 주기에 다시 시도합니다. */
    private inline fun attempt(block: () -> Unit) {
        try {
            block()
        } catch (e: Exception) {
            // 다음 주기에 다시 시도합니다.
        }
    }

    override fun onCreate() {
        super.onCreate()
        store = Store(this)
        startForeground(NOTICE_ID, notice())
        worker = HandlerThread("folder-watch").apply { start() }
        handler = Handler(worker.looper)
        handler.post(tick)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int) = START_STICKY

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        handler.removeCallbacks(tick)
        worker.quitSafely()
        super.onDestroy()
    }

    private fun notice(): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "녹음 폴더 감시", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        return Notification.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_shield)
            .setContentTitle("CodySafe 보호 중")
            .setContentText("새 통화 녹음을 확인하고 있습니다.")
            .setContentIntent(open)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val CHANNEL = "folder_watch"
        private const val NOTICE_ID = -3
        private const val POLL_MS = 15_000L

        fun start(context: Context) {
            val store = Store(context)
            if (store.token.isEmpty() || store.folder.isEmpty()) return
            context.startForegroundService(Intent(context, FolderWatchService::class.java))
        }
    }
}

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) FolderWatchService.start(context)
    }
}
