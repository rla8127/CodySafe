package com.codysafe.guard

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.net.Uri
import androidx.documentfile.provider.DocumentFile
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

const val SERVER = "http://54.116.173.130:8091"

/** 기기 설정. 토큰만 저장하며 AWS 자격 증명은 앱에 두지 않습니다. */
class Store(context: Context) {
    private val p: SharedPreferences = context.getSharedPreferences("guard", Context.MODE_PRIVATE)

    var token: String
        get() = p.getString("token", "") ?: ""
        set(v) = p.edit().putString("token", v).apply()
    var folder: String
        get() = p.getString("folder", "") ?: ""
        set(v) = p.edit().putString("folder", v).apply()
    var folderSince: Long
        get() = p.getLong("folderSince", 0)
        set(v) = p.edit().putLong("folderSince", v).apply()
    var lastAlert: Int
        get() = p.getInt("lastAlert", 0)
        set(v) = p.edit().putInt("lastAlert", v).apply()

    var lockUntil: Long
        get() = p.getLong("lockUntil", 0)
        set(v) = p.edit().putLong("lockUntil", v).apply()
    var lockApps: Set<String>
        get() = p.getStringSet("lockApps", emptySet())!!
        set(v) = p.edit().putStringSet("lockApps", v).apply()
    val locked: Boolean
        get() = System.currentTimeMillis() < lockUntil

    fun isUploaded(key: String) = p.getStringSet("uploaded", emptySet())!!.contains(key)
    fun markUploaded(key: String) {
        val next = HashSet(p.getStringSet("uploaded", emptySet())!!)
        next.add(key)
        p.edit().putStringSet("uploaded", next).apply()
    }
}

class Api(private val store: Store) {
    fun call(method: String, path: String, body: JSONObject? = null): JSONObject {
        val conn = URL(SERVER + path).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = 15_000
            conn.readTimeout = 30_000
            if (store.token.isNotEmpty()) conn.setRequestProperty("Authorization", "Bearer ${store.token}")
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            val code = conn.responseCode
            val stream = if (code < 400) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() } ?: ""
            if (code >= 400) throw ApiError(code, text)
            return if (text.isEmpty()) JSONObject() else JSONObject(text)
        } finally {
            conn.disconnect()
        }
    }

    /** S3 presigned URL에는 Authorization 헤더를 보내면 안 됩니다. */
    private fun put(context: Context, url: String, uri: Uri, size: Long) {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "PUT"
            conn.doOutput = true
            conn.connectTimeout = 15_000
            conn.readTimeout = 120_000
            conn.setRequestProperty("Content-Type", CONTENT_TYPE)
            if (size > 0) conn.setFixedLengthStreamingMode(size) else conn.setChunkedStreamingMode(64 * 1024)
            val input = context.contentResolver.openInputStream(uri) ?: throw IOException("파일을 열 수 없습니다")
            input.use { src -> conn.outputStream.use { dst -> src.copyTo(dst) } }
            if (conn.responseCode >= 300) throw ApiError(conn.responseCode, "upload failed")
        } finally {
            conn.disconnect()
        }
    }

    fun upload(context: Context, uri: Uri, name: String, size: Long, key: String) {
        val created = call(
            "POST", "/v1/recordings",
            JSONObject().put("filename", name).put("client_key", key).put("content_type", CONTENT_TYPE),
        )
        if (created.optBoolean("already_uploaded")) return
        put(context, created.getString("upload_url"), uri, size)
        call("POST", "/v1/recordings/${created.getString("id")}/complete")
    }

    private companion object {
        const val CONTENT_TYPE = "application/octet-stream"
    }
}

class ApiError(val code: Int, message: String) : IOException("HTTP $code: $message")

object Sync {
    private val EXTENSIONS = setOf("m4a", "mp3", "mp4", "wav", "flac", "ogg", "amr", "webm", "txt")
    private const val SETTLE_MS = 15_000L
    private const val LOCK_NOTICE_ID = -1

    /** 폴더 연결 이후 생긴 파일만 올립니다. 과거 녹음이 한꺼번에 나가지 않게 하려는 기준입니다. */
    @Synchronized
    fun uploadNewFiles(context: Context, store: Store): Int {
        if (store.folder.isEmpty()) return 0
        val tree = DocumentFile.fromTreeUri(context, Uri.parse(store.folder)) ?: return 0
        val api = Api(store)
        var count = 0
        for (file in tree.listFiles()) {
            val name = file.name ?: continue
            val modified = file.lastModified()
            if (!file.isFile || name.substringAfterLast('.', "").lowercase() !in EXTENSIONS) continue
            if (modified < store.folderSince || System.currentTimeMillis() - modified < SETTLE_MS) continue
            val key = "$name|${file.length()}|$modified"
            if (store.isUploaded(key)) continue
            try {
                api.upload(context, file.uri, name, file.length(), key)
                count++
            } catch (e: ApiError) {
                // 서버가 받지 않는 형식 하나 때문에 나머지 파일까지 재시도에 묶이지 않게 건너뜁니다.
                if (e.code != 415) throw e
            }
            store.markUploaded(key)
        }
        return count
    }

    /** 서버에 못 닿으면 저장된 시각까지 잠금을 유지합니다. */
    fun checkLock(context: Context, store: Store) {
        val state = Api(store).call("GET", "/v1/lock")
        val wasLocked = store.locked
        val apps = state.getJSONArray("apps")
        store.lockApps = (0 until apps.length()).map { apps.getString(it) }.toSet()
        store.lockUntil = System.currentTimeMillis() + state.getLong("remaining") * 1000
        if (!wasLocked && store.locked) {
            Notifier.show(context, LOCK_NOTICE_ID, "금융 앱을 잠갔습니다", "보이스피싱이 의심됩니다. 지금 돈을 보내지 마세요.")
        }
    }

    fun checkAlerts(context: Context, store: Store) {
        val items = Api(store).call("GET", "/v1/alerts?after=${store.lastAlert}").getJSONArray("items")
        var last = store.lastAlert
        for (i in items.length() - 1 downTo 0) {
            val alert = items.getJSONObject(i)
            Notifier.show(context, alert.getInt("id"), alert.getString("title"), alert.getString("body"))
            last = maxOf(last, alert.getInt("id"))
        }
        store.lastAlert = last
    }
}

object Notifier {
    private const val CHANNEL = "family_alert"

    fun show(context: Context, id: Int, title: String, body: String) {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "가족 사기 경고", NotificationManager.IMPORTANCE_HIGH))
        val open = PendingIntent.getActivity(
            context, 0, Intent(context, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
        )
        manager.notify(
            id,
            Notification.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_shield)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(Notification.BigTextStyle().bigText(body))
                .setContentIntent(open)
                .setAutoCancel(true)
                .build(),
        )
    }
}
