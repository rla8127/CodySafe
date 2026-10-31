package com.codysafe.guard

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import kotlin.concurrent.thread

/** 웹 MVP(css/style.css)의 색과 형태를 따릅니다. 화면 값은 모두 서버의 실제 데이터입니다. */
class MainActivity : Activity() {
    private lateinit var store: Store
    private lateinit var api: Api
    private lateinit var content: LinearLayout
    private lateinit var tabBar: LinearLayout
    private val handler = Handler(Looper.getMainLooper())
    private var tab = TAB_HOME
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
        window.statusBarColor = BG
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR

        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(16), dp(18), dp(28))
        }
        val scroll = ScrollView(this).apply {
            addView(content)
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
        }
        tabBar = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(Color.WHITE)
            elevation = dp(12).toFloat()
            setPadding(0, dp(6), 0, dp(6))
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(BG)
            addView(scroll)
            addView(tabBar)
        })
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
        tabBar.visibility = View.GONE
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
        brandRow()
        heading("AI 사기, 가족과 함께\n미리 막아요", 28f)
        val card = card()
        listOf(
            "앱이 통화를 직접 녹음하지 않고, 이미 저장된 파일만 읽습니다.",
            "폴더를 연결한 뒤에 생긴 파일만 서버로 보냅니다.",
            "음성은 분석 후 삭제하고, 일상 통화는 글자 기록도 남기지 않습니다.",
            "사기로 의심되는 통화의 글자 기록은 검토를 위해 보관합니다.",
            "보이스피싱이 강하게 의심되면 연결한 가족에게 요약을 보냅니다.",
        ).forEach { addText(card, "•  $it", 14.5f, false, INK2).setPadding(0, dp(5), 0, dp(5)) }
        val warn = card(WARN_SOFT)
        addText(warn, "통화 상대의 음성도 함께 전송됩니다. 테스트 버전이므로 동의한 사람의 통화나 테스트 파일로만 사용하세요.", 13.5f, false, WARN_TEXT)
        primary("동의하고 시작") {
            store.consented = true
            route()
        }
    }

    private fun setupScreen() {
        content.removeAllViews()
        brandRow()
        heading("기기 등록", 26f)
        muted("가족에게 보일 이름을 정해 주세요. 계정이나 비밀번호는 필요 없습니다.")
        val server = input("서버 주소 (예: http://10.0.2.2:8091)", store.server)
        val name = input("가족에게 보일 이름", "")
        primary("등록") {
            val url = server.text.toString()
            val who = name.text.toString().trim()
            if (url.isBlank() || who.isEmpty()) return@primary toast("서버 주소와 이름을 입력하세요")
            store.server = url
            background({ api.call("POST", "/v1/devices", JSONObject().put("name", who)) }) {
                store.token = it.getString("token")
                store.name = who
                route()
            }
        }
    }

    private fun offlineScreen(e: Exception) {
        tabBar.visibility = View.GONE
        brandRow()
        heading("서버에 연결할 수 없습니다", 22f)
        muted(e.message ?: "")
        muted("서버가 켜져 있는지 확인하세요. 연결되면 자동으로 돌아옵니다.")
        ghost("서버·기기 다시 등록") {
            store.token = ""
            route()
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
                val snapshot = "$tab|$recordings|$recommendations|$family|$alerts"
                runOnUiThread {
                    // 같은 내용을 다시 그리면 입력 중인 초대 코드가 지워지므로 건너뜁니다.
                    if (snapshot != lastRendered) {
                        lastRendered = snapshot
                        render(recordings, recommendations, family, alerts)
                    }
                }
            } catch (e: Exception) {
                runOnUiThread { if (lastRendered.isEmpty() && content.childCount == 0) offlineScreen(e) }
            }
        }
    }

    private fun render(recordings: JSONObject, recs: JSONObject, family: JSONObject, alerts: JSONObject) {
        content.removeAllViews()
        when (tab) {
            TAB_CHECK -> checkTab(recordings)
            TAB_FAMILY -> familyTab(family, alerts)
            else -> homeTab(recordings, recs, family, alerts)
        }
        renderTabs()
    }

    private fun renderTabs() {
        tabBar.visibility = View.VISIBLE
        tabBar.removeAllViews()
        tabItem(TAB_HOME, R.drawable.ic_home, "홈", false)
        tabItem(TAB_CHECK, R.drawable.ic_shield, "검사", true)
        tabItem(TAB_FAMILY, R.drawable.ic_family, "가족", false)
    }

    private fun tabItem(target: Int, icon: Int, label: String, center: Boolean) {
        val on = tab == target
        val color = if (on) PRI else MUTE
        val item = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            setOnClickListener { switchTab(target) }
        }
        val image = ImageView(this).apply { setImageResource(icon) }
        if (center) {
            image.background = gradient(GradientDrawable.Orientation.TL_BR, 99)
            image.setPadding(dp(10), dp(10), dp(10), dp(10))
            image.layoutParams = LinearLayout.LayoutParams(dp(46), dp(46))
            image.elevation = dp(4).toFloat()
        } else {
            image.setColorFilter(color)
            image.layoutParams = LinearLayout.LayoutParams(dp(24), dp(24))
        }
        item.addView(image)
        addText(item, label, 11f, true, color).setPadding(0, dp(3), 0, 0)
        tabBar.addView(item)
    }

    private fun switchTab(target: Int) {
        tab = target
        lastRendered = ""
        refresh()
    }

    private fun homeTab(recordings: JSONObject, recs: JSONObject, family: JSONObject, alerts: JSONObject) {
        brandRow()
        val hello = if (store.name.isEmpty()) "안녕하세요" else "안녕하세요, ${store.name}님"
        muted("$hello. 오늘도 안전한 하루 보내세요")

        val list = recordings.getJSONArray("items")
        val flagged = (0 until list.length()).count { isScam(list.getJSONObject(it)) }
        val reviews = (0 until list.length()).count { list.getJSONObject(it).getBoolean("needs_review") }
        val guardians = family.getJSONArray("guardians").length()

        val hero = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = gradient(GradientDrawable.Orientation.TL_BR, 24)
            setPadding(dp(20), dp(20), dp(20), dp(20))
            elevation = dp(6).toFloat()
            layoutParams = marginTop(10)
        }
        addText(hero, "분석한 통화", 13f, true, Color.WHITE)
        addText(hero, "${recs.getInt("analyzed")}건", 40f, true, Color.WHITE)
        addText(hero, "사기 의심 ${flagged}건 · 연결된 가족 ${guardians}명", 13.5f, false, Color.WHITE)
        val actions = LinearLayout(this).apply { setPadding(0, dp(14), 0, 0) }
        heroAction(actions, "통화 검사", true) { switchTab(TAB_CHECK) }
        heroAction(actions, "가족 보호", false) { switchTab(TAB_FAMILY) }
        hero.addView(actions)
        content.addView(hero)

        val unread = alerts.getJSONArray("items")
        for (i in 0 until unread.length()) {
            if (unread.getJSONObject(i).getInt("acked") == 0) alertCard(unread.getJSONObject(i))
        }
        if (reviews > 0) {
            val card = card(WARN_SOFT)
            addText(card, "검토가 필요한 통화 ${reviews}건", 15f, true, WARN_TEXT)
            addText(card, "판정을 확인해 주시면 탐지 개선에 쓰입니다.", 13.5f, false, WARN_TEXT)
            card.setOnClickListener { switchTab(TAB_CHECK) }
        }

        section("자주 노출된 사기 유형")
        val items = recs.getJSONArray("items")
        if (items.length() == 0) empty("아직 사기로 판정된 통화가 없습니다.")
        for (i in 0 until items.length()) {
            val r = items.getJSONObject(i)
            val card = card()
            chip(card, "${r.getInt("count")}회 노출", PRI_SOFT, PRI)
            addText(card, r.getString("name"), 16f, true, INK).setPadding(0, dp(8), 0, dp(4))
            addText(card, r.getString("advice"), 14f, false, INK2)
            addText(card, "추천 훈련 · ${r.getString("training")}", 13f, true, PRI).setPadding(0, dp(8), 0, 0)
        }

        section("최근 분석")
        if (list.length() == 0) empty("아직 분석한 통화가 없습니다.")
        for (i in 0 until minOf(list.length(), 3)) recordingCard(list.getJSONObject(i))
    }

    private fun heroAction(parent: LinearLayout, label: String, filled: Boolean, onClick: () -> Unit) {
        parent.addView(TextView(this).apply {
            text = label
            textSize = 13.5f
            gravity = Gravity.CENTER
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(if (filled) PRI else Color.WHITE)
            background = rounded(if (filled) Color.WHITE else Color.parseColor("#33FFFFFF"), 12)
            setPadding(0, dp(10), 0, dp(10))
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                if (filled) rightMargin = dp(8)
            }
            setOnClickListener { onClick() }
        })
    }

    private fun checkTab(recordings: JSONObject) {
        heading("통화 검사", 24f)
        muted("저장된 통화 녹음을 AI가 분석해 사기 여부를 알려 드립니다.")
        val folder = card()
        addText(folder, "녹음 폴더", 15f, true, INK)
        val name = Uri.parse(store.folder).lastPathSegment?.substringAfter(':')
        chip(folder, if (store.folder.isEmpty()) "연결 안 됨" else "연결됨 · $name", if (store.folder.isEmpty()) NEUTRAL else SAFE_SOFT, if (store.folder.isEmpty()) INK2 else SAFE_TEXT)
        addText(folder, "연결한 뒤에 새로 저장된 파일만 분석합니다.", 13f, false, SUB).setPadding(0, dp(8), 0, 0)
        ghost("폴더 선택", folder) { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), REQ_FOLDER) }
        ghost("지금 동기화", folder) {
            SyncWorker.runNow(this)
            toast("동기화를 요청했습니다")
        }
        primary("파일 직접 올려 검사") {
            startActivityForResult(
                Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"),
                REQ_FILE,
            )
        }

        section("분석 결과")
        val list = recordings.getJSONArray("items")
        if (list.length() == 0) empty("아직 올린 파일이 없습니다.")
        for (i in 0 until list.length()) recordingCard(list.getJSONObject(i))
    }

    private fun recordingCard(r: JSONObject) {
        val id = r.getString("id")
        val status = r.getString("status")
        val label = r.optString("review_label").ifEmptyNull() ?: r.optString("label").ifEmptyNull()
        val card = card()
        verdictChip(card, status, label)
        addText(card, callTitle(r.getString("filename")), 15.5f, true, INK).setPadding(0, dp(8), 0, dp(2))
        r.optString("summary").ifEmptyNull()?.let { addText(card, it, 14f, false, INK2) }
        if (status == "failed") addText(card, "처리에 실패했습니다. 다시 시도해 주세요.", 14f, false, DANGER)

        val evidence = r.getJSONArray("evidence")
        for (i in 0 until evidence.length()) addText(card, "“${evidence.getString(i)}”", 13f, false, SUB)
        val matches = r.getJSONArray("matches")
        if (matches.length() > 0) {
            val top = matches.getJSONObject(0)
            val box = nested(card, PRI_SOFT)
            addText(box, top.getString("name"), 14f, true, PRI)
            addText(box, top.getString("advice"), 13.5f, false, INK2)
        }

        val row = LinearLayout(this).apply { setPadding(0, dp(8), 0, 0) }
        if (status == "failed") small(row, "다시 시도", PRI) { act("POST", "/v1/recordings/$id/complete") }
        if (status == "done") {
            small(row, if (r.getBoolean("needs_review")) "판정 확인" else "판정 고치기", PRI) { reviewDialog(id) }
        }
        small(row, "삭제", SUB) {
            AlertDialog.Builder(this)
                .setMessage("이 기록을 서버에서 삭제할까요?")
                .setPositiveButton("삭제") { _, _ -> act("DELETE", "/v1/recordings/$id") }
                .setNegativeButton("취소", null)
                .show()
        }
        card.addView(row)
    }

    /** 색만으로 구분하지 않도록 문구를 함께 씁니다. 판단 어려움은 안전 색으로 표시하지 않습니다. */
    private fun verdictChip(parent: LinearLayout, status: String, label: String?) {
        when {
            status == "failed" -> chip(parent, "실패", DANGER_SOFT, DANGER)
            status != "done" -> chip(parent, STATUS[status] ?: status, PRI_SOFT, PRI)
            label == "voice_phishing" -> chip(parent, "보이스피싱 의심", DANGER_SOFT, DANGER)
            label == "other_scam" -> chip(parent, "다른 사기 의심", WARN_SOFT, WARN_TEXT)
            label == "normal" -> chip(parent, "사기 징후 없음", SAFE_SOFT, SAFE_TEXT)
            else -> chip(parent, "판단 어려움", NEUTRAL, INK2)
        }
    }

    private fun reviewDialog(id: String) {
        val values = arrayOf("voice_phishing", "other_scam", "normal")
        AlertDialog.Builder(this)
            .setTitle("이 통화는 실제로 무엇이었나요?")
            .setItems(arrayOf("보이스피싱", "다른 사기 (학습 데이터로 보관)", "사기 아님 (글자 기록 삭제)")) { _, which ->
                act("POST", "/v1/recordings/$id/review", JSONObject().put("label", values[which]))
            }
            .show()
    }

    private fun familyTab(family: JSONObject, alerts: JSONObject) {
        heading("가족 보호", 24f)
        muted("혼자 판단하기 어려울 때 가족과 함께 대응하세요.")

        section("받은 가족 경고")
        val items = alerts.getJSONArray("items")
        if (items.length() == 0) empty("받은 경고가 없습니다.")
        for (i in 0 until items.length()) alertCard(items.getJSONObject(i))

        section("나를 지켜보는 가족")
        val guardians = family.getJSONArray("guardians")
        if (guardians.length() == 0) empty("연결된 가족이 없습니다.")
        for (i in 0 until guardians.length()) personCard(guardians, i, "내 보이스피싱 의심 알림을 받습니다.", true)
        ghost("초대 코드 만들기") {
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
        if (wards.length() == 0) empty("가족에게 받은 초대 코드를 입력하세요.")
        for (i in 0 until wards.length()) personCard(wards, i, "이 가족의 경고를 받습니다.", false)
        val code = input("초대 코드", "")
        primary("연결") {
            background({ api.call("POST", "/v1/family/link", JSONObject().put("code", code.text.toString())) }) {
                toast(it.getString("protected_name") + "님과 연결했습니다")
                lastRendered = ""
                refresh()
            }
        }
    }

    private fun personCard(people: JSONArray, index: Int, note: String, removable: Boolean) {
        val person = people.getJSONObject(index)
        val card = card()
        addText(card, person.getString("name"), 15.5f, true, INK)
        addText(card, note, 13.5f, false, SUB)
        if (removable) {
            val row = LinearLayout(this).apply { setPadding(0, dp(6), 0, 0) }
            small(row, "연결 해제", SUB) { act("DELETE", "/v1/family/guardians/${person.getString("id")}") }
            card.addView(row)
        }
    }

    private fun alertCard(a: JSONObject) {
        val unread = a.getInt("acked") == 0
        val card = card(if (unread) DANGER_SOFT else Color.WHITE)
        chip(card, if (unread) "가족 경고" else "확인함", if (unread) Color.WHITE else NEUTRAL, if (unread) DANGER else INK2)
        addText(card, a.getString("title"), 15.5f, true, INK).setPadding(0, dp(8), 0, dp(2))
        addText(card, a.getString("body"), 14f, false, INK2)
        if (unread) {
            val row = LinearLayout(this).apply { setPadding(0, dp(6), 0, 0) }
            small(row, "확인함", DANGER) { act("POST", "/v1/alerts/${a.getInt("id")}/ack") }
            card.addView(row)
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
        toast("업로드 중입니다")
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

    private fun isScam(r: JSONObject): Boolean {
        val label = r.optString("review_label").ifEmptyNull() ?: r.optString("label")
        return label == "voice_phishing" || label == "other_scam"
    }

    /** 삼성 녹음 파일명의 전화번호를 화면에 드러내지 않고 통화 시각만 보여 줍니다. */
    private fun callTitle(filename: String): String {
        val m = Regex("_\\d{2}(\\d{2})(\\d{2})_(\\d{2})(\\d{2})\\d{2}\\.").find(filename)
            ?: return filename.substringBeforeLast('.')
        val (month, day, hour, minute) = m.destructured
        return "${month.toInt()}월 ${day.toInt()}일 $hour:$minute 통화"
    }

    private fun String.ifEmptyNull(): String? = if (isEmpty() || this == "null") null else this

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_SHORT).show()

    private fun marginTop(top: Int) = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
    ).apply { topMargin = dp(top) }

    private fun rounded(color: Int, radius: Int) = GradientDrawable().apply {
        setColor(color)
        cornerRadius = dp(radius).toFloat()
    }

    private fun gradient(orientation: GradientDrawable.Orientation, radius: Int) =
        GradientDrawable(orientation, intArrayOf(Color.parseColor("#3B6BFF"), Color.parseColor("#7B4DFF"))).apply {
            cornerRadius = dp(radius).toFloat()
        }

    private fun brandRow() {
        val row = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, 0, 0, dp(10))
        }
        row.addView(ImageView(this).apply {
            setImageResource(R.drawable.ic_logo)
            layoutParams = LinearLayout.LayoutParams(dp(30), dp(30)).apply { rightMargin = dp(8) }
        })
        addText(row, "CodySafe", 20f, true, INK)
        content.addView(row)
    }

    private fun heading(value: String, size: Float) = addText(content, value, size, true, INK)

    private fun section(value: String) = addText(content, value, 17f, true, INK).also { it.setPadding(dp(2), dp(24), 0, dp(2)) }

    private fun muted(value: String) = addText(content, value, 14f, false, SUB)

    private fun empty(value: String) = addText(card(), value, 14f, false, SUB)

    private fun addText(parent: ViewGroup, value: String, size: Float, bold: Boolean, color: Int): TextView =
        TextView(this).apply {
            text = value
            textSize = size
            setTextColor(color)
            setLineSpacing(0f, 1.25f)
            if (bold) setTypeface(typeface, Typeface.BOLD)
            setPadding(0, dp(2), 0, dp(2))
            parent.addView(this)
        }

    private fun chip(parent: LinearLayout, value: String, bg: Int, fg: Int) {
        val view = addText(parent, value, 12f, true, fg)
        view.background = rounded(bg, 99)
        view.setPadding(dp(10), dp(4), dp(10), dp(4))
        view.layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = dp(4) }
    }

    private fun action(label: String, bg: GradientDrawable, fg: Int, parent: LinearLayout, top: Int, onClick: () -> Unit) {
        parent.addView(TextView(this).apply {
            text = label
            textSize = 15.5f
            gravity = Gravity.CENTER
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(fg)
            background = bg
            setPadding(dp(16), dp(14), dp(16), dp(14))
            layoutParams = marginTop(top)
            setOnClickListener { onClick() }
        })
    }

    private fun primary(label: String, onClick: () -> Unit) =
        action(label, gradient(GradientDrawable.Orientation.LEFT_RIGHT, 16), Color.WHITE, content, 12, onClick)

    private fun ghost(label: String, parent: LinearLayout = content, onClick: () -> Unit) =
        action(label, rounded(PRI_SOFT, 16), PRI, parent, 10, onClick)

    private fun small(row: LinearLayout, label: String, color: Int, onClick: () -> Unit) {
        row.addView(TextView(this).apply {
            text = label
            textSize = 13.5f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(color)
            setPadding(0, dp(8), dp(18), dp(4))
            setOnClickListener { onClick() }
        })
    }

    private fun input(hint: String, value: String): EditText =
        EditText(this).apply {
            this.hint = hint
            setText(value)
            setSingleLine()
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            background = rounded(Color.WHITE, 14)
            setPadding(dp(14), dp(14), dp(14), dp(14))
            layoutParams = marginTop(10)
            content.addView(this)
        }

    private fun card(color: Int = Color.WHITE): LinearLayout =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(color, 20)
            elevation = dp(2).toFloat()
            setPadding(dp(18), dp(16), dp(18), dp(16))
            layoutParams = marginTop(12)
            content.addView(this)
        }

    private fun nested(parent: LinearLayout, color: Int): LinearLayout =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(color, 14)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            layoutParams = marginTop(10)
            parent.addView(this)
        }

    private companion object {
        const val POLL_MS = 5_000L
        const val REQ_FOLDER = 1
        const val REQ_FILE = 2
        const val TAB_HOME = 0
        const val TAB_CHECK = 1
        const val TAB_FAMILY = 2

        val BG = Color.parseColor("#F3F5FA")
        val INK = Color.parseColor("#0F172A")
        val INK2 = Color.parseColor("#334155")
        val SUB = Color.parseColor("#64748B")
        val MUTE = Color.parseColor("#94A3B8")
        val NEUTRAL = Color.parseColor("#EEF1F7")
        val PRI = Color.parseColor("#2F5BFF")
        val PRI_SOFT = Color.parseColor("#EBF0FF")
        val SAFE_SOFT = Color.parseColor("#E7F8EF")
        val SAFE_TEXT = Color.parseColor("#08875A")
        val WARN_SOFT = Color.parseColor("#FFF4E5")
        val WARN_TEXT = Color.parseColor("#C46A00")
        val DANGER = Color.parseColor("#D12E22")
        val DANGER_SOFT = Color.parseColor("#FEECEB")

        val STATUS = mapOf(
            "queued" to "대기 중",
            "transcribing" to "음성 변환 중",
            "analyzing" to "분석 중",
        )
    }
}
