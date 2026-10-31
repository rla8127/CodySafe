package com.codysafe.guard

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONObject
import kotlin.concurrent.thread

/** 테스트 속도를 우선해 XML 리소스 없이 코드로 화면을 그립니다. */
class MainActivity : Activity() {
    private lateinit var store: Store
    private lateinit var api: Api
    private lateinit var content: LinearLayout
    private val handler = Handler(Looper.getMainLooper())
    private var showFamily = false
    private var lastRendered = ""

    private val poll = object : Runnable {
        override fun run() {
            if (store.token.isNotEmpty()) refresh()
            handler.postDelayed(this, POLL_MS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        api = Api(store)
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(32), dp(16), dp(32))
        }
        setContentView(ScrollView(this).apply { addView(content) })
        if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        route()
    }

    override fun onResume() {
        super.onResume()
        handler.post(poll)
    }

    override fun onPause() {
        handler.removeCallbacks(poll)
        super.onPause()
    }

    private fun route() {
        lastRendered = ""
        when {
            !store.consented -> consentScreen()
            store.token.isEmpty() -> setupScreen()
            else -> {
                SyncWorker.schedule(this)
                refresh()
            }
        }
    }

    // ---------- 첫 실행 ----------
    private fun consentScreen() {
        content.removeAllViews()
        title("CodySafe 가족보호")
        text(
            "이 앱은 선택한 폴더의 녹음 파일을 서버로 보내 사기 여부를 분석합니다.\n\n" +
                "• 앱이 통화를 직접 녹음하지는 않습니다. 이미 저장된 파일만 읽습니다.\n" +
                "• 폴더를 연결한 뒤에 생긴 파일만 보냅니다.\n" +
                "• 음성은 분석 후 삭제합니다. 일상 통화는 원문도 남기지 않습니다.\n" +
                "• 사기로 의심되는 통화의 글자 기록은 검토를 위해 보관합니다.\n" +
                "• 보이스피싱이 강하게 의심되면 연결한 가족에게 요약을 보냅니다.\n\n" +
                "통화 상대의 음성도 함께 전송됩니다. 현재는 테스트 버전이므로 동의한 사람의 통화나 테스트 파일로만 사용하세요.",
        )
        button("동의하고 시작") {
            store.consented = true
            route()
        }
    }

    private fun setupScreen() {
        content.removeAllViews()
        title("기기 등록")
        val server = input("서버 주소 (예: http://10.0.2.2:8091)", store.server)
        val name = input("가족에게 보일 이름", "")
        button("등록") {
            val url = server.text.toString()
            val who = name.text.toString().trim()
            if (url.isBlank() || who.isEmpty()) return@button toast("서버 주소와 이름을 입력하세요")
            store.server = url
            background(
                { api.call("POST", "/v1/devices", JSONObject().put("name", who)) },
            ) {
                store.token = it.getString("token")
                route()
            }
        }
    }

    // ---------- 메인 ----------
    private fun refresh() {
        thread {
            try {
                val recordings = api.call("GET", "/v1/recordings")
                val recommendations = api.call("GET", "/v1/recommendations")
                val family = api.call("GET", "/v1/family")
                val alerts = api.call("GET", "/v1/alerts")
                Sync.checkAlerts(this, store)
                val snapshot = "$showFamily|$recordings|$recommendations|$family|$alerts"
                runOnUiThread {
                    // 같은 내용을 다시 그리면 입력 중인 초대 코드가 지워지므로 건너뜁니다.
                    if (snapshot != lastRendered) {
                        lastRendered = snapshot
                        mainScreen(recordings, recommendations, family, alerts)
                    }
                }
            } catch (e: Exception) {
                runOnUiThread { if (content.childCount == 0) offlineScreen(e) }
            }
        }
    }

    private fun offlineScreen(e: Exception) {
        title("서버에 연결할 수 없습니다")
        text(e.message ?: "")
        button("서버·기기 다시 등록") {
            store.token = ""
            route()
        }
    }

    private fun mainScreen(recordings: JSONObject, recs: JSONObject, family: JSONObject, alerts: JSONObject) {
        content.removeAllViews()
        title("CodySafe 가족보호")
        val tabs = LinearLayout(this)
        listOf("내 통화" to false, "가족" to true).forEach { (label, target) ->
            tabs.addView(
                Button(this).apply {
                    text = if (target == showFamily) "● $label" else label
                    setOnClickListener {
                        showFamily = target
                        lastRendered = ""
                        refresh()
                    }
                },
            )
        }
        content.addView(tabs)
        if (showFamily) familyTab(family, alerts) else callsTab(recordings, recs)
    }

    private fun callsTab(recordings: JSONObject, recs: JSONObject) {
        val linked = if (store.folder.isEmpty()) "연결된 폴더 없음" else "폴더 연결됨: " + Uri.parse(store.folder).lastPathSegment
        text(linked)
        button("녹음 폴더 선택") {
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), REQ_FOLDER)
        }
        button("지금 동기화") {
            SyncWorker.runNow(this)
            toast("동기화를 요청했습니다")
        }
        button("테스트 파일 1개 올리기") {
            startActivityForResult(
                Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"),
                REQ_FILE,
            )
        }

        section("자주 노출된 사기 유형 (분석 ${recs.getInt("analyzed")}건)")
        val items = recs.getJSONArray("items")
        if (items.length() == 0) text("아직 사기로 판정된 통화가 없습니다.")
        for (i in 0 until items.length()) {
            val r = items.getJSONObject(i)
            card("${r.getString("name")} · ${r.getInt("count")}회", "${r.getString("advice")}\n\n추천 훈련: ${r.getString("training")}", Color.parseColor("#EEF2FF"))
        }

        section("분석 결과")
        val list = recordings.getJSONArray("items")
        if (list.length() == 0) text("아직 올린 파일이 없습니다.")
        for (i in 0 until list.length()) recordingCard(list.getJSONObject(i))
    }

    private fun recordingCard(r: JSONObject) {
        val id = r.getString("id")
        val status = r.getString("status")
        val label = r.optString("review_label").ifEmptyNull() ?: r.optString("label").ifEmptyNull()
        val head = r.getString("filename") + " · " + if (status == "done") LABELS[label] ?: "판정 불가" else STATUS[status] ?: status
        val body = StringBuilder()
        r.optString("summary").ifEmptyNull()?.let { body.append(it) }
        if (status == "failed") body.append("처리에 실패했습니다.")
        val evidence = r.getJSONArray("evidence")
        for (i in 0 until evidence.length()) body.append("\n• ").append(evidence.getString(i))
        val matches = r.getJSONArray("matches")
        if (matches.length() > 0) {
            val top = matches.getJSONObject(0)
            body.append("\n\n유형: ").append(top.getString("name")).append("\n").append(top.getString("advice"))
        }
        val color = when (label) {
            "voice_phishing" -> "#FEE2E2"
            "other_scam" -> "#FFEDD5"
            else -> "#F3F4F6"
        }
        val card = card(head, body.toString(), Color.parseColor(color))
        if (status == "failed") {
            card.addView(Button(this).apply {
                text = "다시 시도"
                setOnClickListener { act("POST", "/v1/recordings/$id/complete") }
            })
        }
        if (status == "done") {
            card.addView(Button(this).apply {
                text = if (r.getBoolean("needs_review")) "검토 필요: 판정 확인" else "판정 고치기"
                setOnClickListener { reviewDialog(id) }
            })
        }
        card.addView(Button(this).apply {
            text = "기록 삭제"
            setOnClickListener {
                AlertDialog.Builder(this@MainActivity)
                    .setMessage("이 기록을 서버에서 삭제할까요?")
                    .setPositiveButton("삭제") { _, _ -> act("DELETE", "/v1/recordings/$id") }
                    .setNegativeButton("취소", null)
                    .show()
            }
        })
    }

    private fun reviewDialog(id: String) {
        val values = arrayOf("voice_phishing", "other_scam", "normal")
        AlertDialog.Builder(this)
            .setTitle("이 통화는 실제로 무엇이었나요?")
            .setItems(arrayOf("보이스피싱", "다른 사기 (학습 데이터로 보관)", "사기 아님 (기록 원문 삭제)")) { _, which ->
                act("POST", "/v1/recordings/$id/review", JSONObject().put("label", values[which]))
            }
            .show()
    }

    private fun familyTab(family: JSONObject, alerts: JSONObject) {
        section("받은 가족 경고")
        val items = alerts.getJSONArray("items")
        if (items.length() == 0) text("받은 경고가 없습니다.")
        for (i in 0 until items.length()) {
            val a = items.getJSONObject(i)
            val card = card(a.getString("title"), a.getString("body"), Color.parseColor(if (a.getInt("acked") == 1) "#F3F4F6" else "#FEE2E2"))
            if (a.getInt("acked") == 0) {
                card.addView(Button(this).apply {
                    text = "확인함"
                    setOnClickListener { act("POST", "/v1/alerts/${a.getInt("id")}/ack") }
                })
            }
        }

        section("나를 지켜보는 가족")
        val guardians = family.getJSONArray("guardians")
        if (guardians.length() == 0) text("연결된 가족이 없습니다.")
        for (i in 0 until guardians.length()) {
            val g = guardians.getJSONObject(i)
            val card = card(g.getString("name"), "내 보이스피싱 의심 알림을 받습니다.", Color.parseColor("#F3F4F6"))
            card.addView(Button(this).apply {
                text = "연결 해제"
                setOnClickListener { act("DELETE", "/v1/family/guardians/${g.getString("id")}") }
            })
        }
        button("초대 코드 만들기") {
            background({ api.call("POST", "/v1/family/invite") }) {
                AlertDialog.Builder(this)
                    .setTitle(it.getString("code"))
                    .setMessage("10분 안에 가족 폰에 입력하세요. 이 코드를 받은 사람은 내 보이스피싱 의심 알림을 받습니다.")
                    .setPositiveButton("닫기", null)
                    .show()
            }
        }

        section("내가 지키는 가족")
        val wards = family.getJSONArray("protected")
        for (i in 0 until wards.length()) text("• " + wards.getJSONObject(i).getString("name"))
        val code = input("가족에게 받은 초대 코드", "")
        button("연결") {
            background(
                { api.call("POST", "/v1/family/link", JSONObject().put("code", code.text.toString())) },
            ) {
                toast(it.getString("protected_name") + "님과 연결했습니다")
                lastRendered = ""
                refresh()
            }
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (resultCode != RESULT_OK || uri == null) return
        when (requestCode) {
            REQ_FOLDER -> {
                contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
                store.folder = uri.toString()
                store.folderSince = System.currentTimeMillis()
                lastRendered = ""
                refresh()
            }
            REQ_FILE -> uploadOne(uri)
        }
    }

    private fun uploadOne(uri: Uri) {
        var name = "upload"
        var size = -1L
        contentResolver.query(uri, null, null, null, null)?.use { c ->
            if (c.moveToFirst()) {
                name = c.getString(c.getColumnIndexOrThrow(OpenableColumns.DISPLAY_NAME))
                size = c.getLong(c.getColumnIndexOrThrow(OpenableColumns.SIZE))
            }
        }
        toast("업로드 중: $name")
        background(
            {
                // 같은 파일로 여러 번 시험할 수 있게 시각을 키에 넣습니다.
                api.upload(this, uri, name, size, "manual|$name|${System.currentTimeMillis()}")
                JSONObject()
            },
        ) {
            toast("업로드 완료. 분석 중입니다")
            refresh()
        }
    }

    // ---------- 공통 ----------
    private fun act(method: String, path: String, body: JSONObject? = null) {
        background({ api.call(method, path, body) }) {
            lastRendered = ""
            refresh()
        }
    }

    private fun background(work: () -> JSONObject, done: (JSONObject) -> Unit) {
        thread {
            try {
                val result = work()
                runOnUiThread { done(result) }
            } catch (e: Exception) {
                runOnUiThread { toast("실패: ${e.message}") }
            }
        }
    }

    private fun String.ifEmptyNull(): String? = if (isEmpty() || this == "null") null else this

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_SHORT).show()

    private fun title(value: String) = addText(content, value, 24f, true)

    private fun section(value: String) = addText(content, value, 18f, true).also { it.setPadding(0, dp(20), 0, dp(6)) }

    private fun text(value: String) = addText(content, value, 15f, false)

    private fun addText(parent: ViewGroup, value: String, size: Float, bold: Boolean): TextView =
        TextView(this).apply {
            text = value
            textSize = size
            setTextColor(Color.parseColor("#111827"))
            if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(0, dp(4), 0, dp(4))
            parent.addView(this)
        }

    private fun button(label: String, onClick: () -> Unit) {
        content.addView(Button(this).apply {
            text = label
            setOnClickListener { onClick() }
        })
    }

    private fun input(hint: String, value: String): EditText =
        EditText(this).apply {
            this.hint = hint
            setText(value)
            setSingleLine()
            content.addView(this)
        }

    private fun card(head: String, body: String, color: Int): LinearLayout {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(color)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = dp(8) }
        }
        addText(card, head, 15f, true)
        if (body.isNotEmpty()) addText(card, body, 14f, false)
        content.addView(card)
        return card
    }

    private companion object {
        const val POLL_MS = 5_000L
        const val REQ_FOLDER = 1
        const val REQ_FILE = 2
        val LABELS = mapOf(
            "voice_phishing" to "보이스피싱 의심",
            "other_scam" to "다른 사기 의심",
            "normal" to "사기 아님",
            "uncertain" to "판단 어려움",
        )
        val STATUS = mapOf(
            "queued" to "대기 중",
            "transcribing" to "음성 변환 중",
            "analyzing" to "분석 중",
            "failed" to "실패",
        )
    }
}
