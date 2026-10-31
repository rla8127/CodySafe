package com.codysafe.guard

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.webkit.JavascriptInterface
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import kotlin.concurrent.thread

/** 화면은 서버의 /app/ 웹 UI이고, 앱은 폴더 접근과 백그라운드 동기화, 알림만 담당합니다. */
class MainActivity : Activity() {
    private lateinit var store: Store
    private lateinit var web: WebView
    private var filePick: ValueCallback<Array<Uri>>? = null
    private val handler = Handler(Looper.getMainLooper())

    private val pollAlerts = object : Runnable {
        override fun run() {
            if (store.token.isNotEmpty()) {
                thread {
                    try {
                        Sync.checkAlerts(this@MainActivity, store)
                    } catch (e: Exception) {
                        // 다음 주기에 다시 확인합니다.
                    }
                }
            }
            handler.postDelayed(this, POLL_MS)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.allowFileAccess = false
        // 서버의 UI를 고치면 앱을 다시 빌드하지 않아도 바로 반영되게 합니다.
        web.settings.cacheMode = WebSettings.LOAD_NO_CACHE
        web.addJavascriptInterface(Bridge(), "CodySafeNative")
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (request.url.host == Uri.parse(SERVER).host) return false
                // tel: 같은 외부 링크는 앱 안에서 열지 않습니다.
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, request.url))
                } catch (e: ActivityNotFoundException) {
                    // 처리할 앱이 없으면 무시합니다.
                }
                return true
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) retryDialog()
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                view: WebView,
                callback: ValueCallback<Array<Uri>>,
                params: FileChooserParams,
            ): Boolean {
                filePick?.onReceiveValue(null)
                filePick = callback
                startActivityForResult(
                    Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"),
                    REQ_FILE,
                )
                return true
            }
        }
        setContentView(web)
        if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        load()
    }

    private fun load() = web.loadUrl("$SERVER/app/")

    private fun retryDialog() {
        AlertDialog.Builder(this)
            .setTitle("서버에 연결할 수 없습니다")
            .setMessage("인터넷 연결을 확인한 뒤 다시 시도해 주세요.")
            .setCancelable(false)
            .setPositiveButton("다시 시도") { _, _ -> load() }
            .show()
    }

    override fun onResume() {
        super.onResume()
        handler.post(pollAlerts)
    }

    override fun onPause() {
        handler.removeCallbacks(pollAlerts)
        super.onPause()
    }

    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = if (resultCode == RESULT_OK) data?.data else null
        when (requestCode) {
            REQ_FILE -> {
                filePick?.onReceiveValue(uri?.let { arrayOf(it) })
                filePick = null
            }
            REQ_FOLDER -> if (uri != null) {
                contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
                store.folder = uri.toString()
                store.folderSince = System.currentTimeMillis()
                web.evaluateJavascript("render()", null)
            }
        }
    }

    /** 웹 UI에 공개하는 기능은 이것뿐입니다. 토큰을 읽는 메서드는 두지 않습니다. */
    private inner class Bridge {
        @JavascriptInterface
        fun setToken(token: String) {
            store.token = token
            if (token.isNotEmpty()) SyncWorker.schedule(this@MainActivity)
        }

        @JavascriptInterface
        fun folderLabel(): String =
            if (store.folder.isEmpty()) "" else Uri.parse(store.folder).lastPathSegment?.substringAfter(':') ?: ""

        @JavascriptInterface
        fun pickFolder() {
            runOnUiThread { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), REQ_FOLDER) }
        }

        @JavascriptInterface
        fun syncNow() {
            SyncWorker.runNow(this@MainActivity)
        }
    }

    private companion object {
        const val POLL_MS = 5_000L
        const val REQ_FILE = 1
        const val REQ_FOLDER = 2
    }
}
