package com.codysafe.guard

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.widget.Toast
import kotlin.concurrent.thread

/** 잠금 중에 금융 앱이 열리면 홈으로 보내고 경고 화면을 띄웁니다. 앱 ID만 보고 화면 내용은 읽지 않습니다. */
class GuardService : AccessibilityService() {
    private lateinit var store: Store
    private val handler = Handler(Looper.getMainLooper())
    private var foreground = ""
    private var lastBlock = 0L

    private val poll = object : Runnable {
        override fun run() {
            if (store.token.isNotEmpty()) {
                thread {
                    try {
                        Sync.checkLock(this@GuardService, store)
                        // 이미 금융 앱을 쓰는 중에 잠금이 걸려도 막습니다.
                        handler.post { blockIfNeeded() }
                    } catch (e: Exception) {
                        // 다음 주기에 다시 확인합니다.
                    }
                }
            }
            handler.postDelayed(this, POLL_MS)
        }
    }

    override fun onServiceConnected() {
        store = Store(this)
        handler.post(poll)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        foreground = event.packageName?.toString() ?: return
        blockIfNeeded()
    }

    private fun blockIfNeeded() {
        if (!store.locked || foreground !in store.lockApps) return
        val now = System.currentTimeMillis()
        if (now - lastBlock < DEBOUNCE_MS) return
        lastBlock = now
        performGlobalAction(GLOBAL_ACTION_HOME)
        // 경고 화면이 뜨지 못하는 기기에서도 왜 막혔는지 알 수 있게 합니다.
        Toast.makeText(this, "보이스피싱 의심으로 금융 앱을 잠갔습니다", Toast.LENGTH_LONG).show()
        Notifier.show(this, BLOCK_NOTICE_ID, "금융 앱을 막았습니다", "지금 돈을 보내지 마세요. 눌러서 112 신고와 해제 방법을 확인하세요.")
        startActivity(
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                .putExtra(MainActivity.EXTRA_LOCK, true),
        )
    }

    override fun onInterrupt() = Unit

    override fun onDestroy() {
        handler.removeCallbacks(poll)
        super.onDestroy()
    }

    private companion object {
        const val POLL_MS = 30_000L
        const val DEBOUNCE_MS = 1_500L
        const val BLOCK_NOTICE_ID = -2
    }
}
