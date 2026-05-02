import os
import json
from datetime import datetime
from flask import Flask, request, session, redirect, url_for, Response
import core

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "vzclaw_secret_change_me")

with open("language.json", "r", encoding="utf-8") as f:
    STRINGS = json.load(f)

def _(key, lang="Chinese", **kwargs):
    return STRINGS.get(lang, STRINGS["English"]).get(key, key).format(**kwargs)

# ---------- 配置 ----------
def get_config():
    data = core.load_data()
    return {
        "language": data.get("language", "Chinese"),
        "token": data.get("token", ""),
        "initialized": data.get("initialized", False),
        "base_url": data.get("base_url", "api.ytea.top/v1"),
        "model": data.get("model", "gpt-4o"),
        "port": data.get("port", 9996)
    }

def set_config(key, value):
    data = core.load_data()
    data[key] = value
    core.save_data(data)

# ---------- 登录验证 ----------
@app.before_request
def check_login():
    if request.endpoint in ('login', 'static'):
        return
    if not session.get("logged_in"):
        cfg = get_config()
        if not cfg["token"]:
            return redirect(url_for("init_page"))
        return redirect(url_for("login"))

def plain_response(html):
    return Response(html, mimetype='text/html')

# ---------- 页面路由 ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    cfg = get_config()
    error = ""
    if request.method == "POST":
        if request.form.get("token") == cfg["token"]:
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = _("invalid_token", cfg["language"])
    return plain_response(HTML_LOGIN.format(
        title=_("login_title", cfg["language"]),
        prompt=_("login_prompt", cfg["language"]),
        button=_("login_button", cfg["language"]),
        error=error
    ))

@app.route("/init")
def init_page():
    cfg = get_config()
    if cfg["initialized"]:
        return redirect(url_for("index"))
    # 传递当前语言，页面会据此切换显示，也能动态切换
    return plain_response(HTML_INIT.format(
        lang=cfg["language"],
        title=_("init_title", cfg["language"]),
        step1_label=_("init_step1", cfg["language"]),
        step2_label=_("init_step2", cfg["language"]),
        step3_label=_("init_step3", cfg["language"]),
        step4_label=_("init_step4", cfg["language"]),
        custom_url_label=_("custom_url", cfg["language"]),
        token_label=_("token", cfg["language"]),
        token_placeholder=_("setting_token_prompt", cfg["language"]),
        next_btn=_("next", cfg["language"]),
        complete_btn=_("complete", cfg["language"]),
        loading=_("loading", cfg["language"]),
        fetch_fail=_("fetch_fail", cfg["language"])
    ))

@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    cfg = get_config()
    if not cfg["initialized"]:
        return redirect(url_for("init_page"))
    return plain_response(HTML_MAIN.format(
        title=_("chat_title", cfg["language"]),
        lang=cfg["language"]
    ))

# ---------- API 端点 (保持不变) ----------
@app.route("/api/config", methods=["GET"])
def api_get_config():
    cfg = get_config()
    return jsonify({"language": cfg["language"], "base_url": cfg["base_url"],
                    "model": cfg["model"], "has_key": bool(cfg.get("api_key")),
                    "port": cfg["port"], "token": cfg["token"][:4] + "****" if cfg["token"] else ""})

@app.route("/api/config", methods=["POST"])
def api_set_config():
    data = request.json
    for key in ["language", "base_url", "model", "port", "token"]:
        if key in data:
            set_config(key, data[key])
    if "api_key" in data and data["api_key"]:
        set_config("api_key", data["api_key"])
    return jsonify({"status": "ok"})

@app.route("/api/init", methods=["POST"])
def api_init():
    data = request.json
    set_config("language", data.get("language", "Chinese"))
    set_config("base_url", data.get("base_url"))
    set_config("model", data.get("model"))
    set_config("api_key", data.get("api_key"))
    if "token" in data and data["token"]:
        set_config("token", data["token"])
    set_config("initialized", True)
    session["logged_in"] = True
    return jsonify({"status": "ok"})

@app.route("/api/fetch_models")
def api_fetch_models():
    base_url = request.args.get("base_url", "")
    api_key = request.args.get("api_key", "")
    models = core.fetch_model_list(base_url, api_key)
    return jsonify({"models": models or []})

@app.route("/api/conversations")
def api_conversations():
    convs = core.get_conversations()
    result = []
    for cid, data in convs.items():
        result.append({"id": cid, "name": data.get("name", "未命名")})
    return jsonify(result)

@app.route("/api/conversations", methods=["POST"])
def api_create_conversation():
    name = request.json.get("name", "新对话")
    cid = core.create_conversation(name)
    return jsonify({"id": cid, "name": name})

@app.route("/api/conversations/<cid>", methods=["PUT"])
def api_rename_conversation(cid):
    name = request.json.get("name")
    conv = core.get_conversations().get(cid, {})
    conv["name"] = name
    core.save_conversation(cid, conv)
    return jsonify({"status": "ok"})

@app.route("/api/conversations/<cid>", methods=["DELETE"])
def api_delete_conversation(cid):
    core.delete_conversation(cid)
    return jsonify({"status": "ok"})

@app.route("/api/history/<cid>")
def api_history(cid):
    conv = core.get_conversations().get(cid, {})
    msgs = conv.get("messages", [])
    history = []
    for m in msgs:
        if m["role"] in ("user", "assistant"):
            history.append({
                "role": m["role"],
                "content": core.clean_reply(m["content"]) if m["role"] == "assistant" else m["content"]
            })
    return jsonify({"history": history})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json
    cid = data.get("convId")
    user_msg = data.get("message", "").strip()
    if not cid or not user_msg:
        return jsonify({"error": "missing params"}), 400

    conv = core.get_conversations().get(cid, {"name": "新对话", "messages": []})
    messages = conv.get("messages", [])

    cfg = get_config()
    lang = cfg["language"]
    if not messages or messages[0]["role"] != "system":
        sys_msg = core.build_system_prompt(lang)
        messages.insert(0, {"role": "system", "content": sys_msg})

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    messages.append({"role": "user", "content": f"[{now}] {user_msg}"})

    reply = core.chat_completion(cfg["api_key"], messages, cfg["base_url"], cfg["model"])
    if reply is None:
        messages.pop()
        core.save_conversation(cid, {"name": conv["name"], "messages": messages})
        return jsonify({"error": "api_error"}), 500

    messages.append({"role": "assistant", "content": reply})
    core.save_conversation(cid, {"name": conv["name"], "messages": messages})

    reqs = core.extract_requests(reply)
    result = {"reply": core.clean_reply(reply), "requests": [], "auto_exec": None}

    for action, arg, content in reqs:
        if action in ("read", "list"):
            if action == "read":
                data_res, err = core.read_file(arg)
                if err is None:
                    result["auto_exec"] = f"已读取文件: {arg}"
                    messages.append({"role": "system", "content": f"File content:\n{data_res}"})
                else:
                    messages.append({"role": "system", "content": f"Read failed: {err}"})
            else:
                data_res, err = core.list_directory(arg)
                if err is None:
                    result["auto_exec"] = f"已列出目录: {arg}"
                    messages.append({"role": "system", "content": f"Directory:\n{data_res}"})
                else:
                    messages.append({"role": "system", "content": f"List failed: {err}"})
            core.save_conversation(cid, {"name": conv["name"], "messages": messages})
        else:
            result["requests"].append({"action": action, "arg": arg, "content": content})
    return jsonify(result)

@app.route("/api/execute", methods=["POST"])
def api_execute():
    data = request.json
    cid = data.get("convId")
    action = data.get("action")
    arg = data.get("arg")
    content = data.get("content", "")
    confirm = data.get("confirm", False)

    conv = core.get_conversations().get(cid, {"name": "新对话", "messages": []})
    messages = conv.get("messages", [])

    if confirm:
        if action == "run":
            out, err, code = core.run_command(arg)
            result = f"Command succeeded.\n{out}" if code == 0 and not err else f"Command failed ({code})\n{out}\n{err}"
        elif action == "write":
            ok, err = core.write_file(arg, content)
            result = "File written." if ok else f"Write failed: {err}"
        messages.append({"role": "system", "content": result})
    else:
        messages.append({"role": "system", "content": f"User denied: [{action}] {arg}"})
    core.save_conversation(cid, {"name": conv["name"], "messages": messages})

    cfg = get_config()
    reply = core.chat_completion(cfg["api_key"], messages, cfg["base_url"], cfg["model"])
    if reply:
        messages.append({"role": "assistant", "content": reply})
        core.save_conversation(cid, {"name": conv["name"], "messages": messages})
        return jsonify({"reply": core.clean_reply(reply)})
    return jsonify({"error": "api_fail"}), 500

# ---------- HTML 模板（已彻底修正，无 Jinja2 干扰） ----------
HTML_LOGIN = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{title}</title>
<style>
:root {{ --bg:#0a0a14; --text:#f0f0fa; --card:rgba(18,18,32,0.9); --border:rgba(255,255,255,0.1); }}
body {{ background:var(--bg); display:flex; align-items:center; justify-content:center; height:100vh; font-family:system-ui; margin:0; }}
.card {{ background:var(--card); border:1px solid var(--border); border-radius:24px; padding:40px; width:360px; text-align:center; }}
h1 {{ background:linear-gradient(135deg,#a855f7,#ec4899); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin:0 0 20px; }}
input {{ width:100%; padding:14px; background:rgba(255,255,255,0.05); border:1px solid var(--border); border-radius:14px; color:white; margin:12px 0; box-sizing:border-box; }}
button {{ background:linear-gradient(135deg,#a855f7,#6366f1); color:white; border:none; padding:14px 30px; border-radius:50px; cursor:pointer; font-size:16px; }}
.error {{ color:#f87171; margin-top:10px; }}
</style></head><body>
<div class="card">
<h1>{title}</h1>
<form method="POST">
<p style="color:#b9b9d4;">{prompt}</p>
<input type="password" name="token" required><br>
<button type="submit">{button}</button>
</form>
<p class="error">{error}</p>
</div></body></html>"""

HTML_INIT = """<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="UTF-8"><title>{title}</title>
<style>
:root {{ --bg:#0a0a14; --text:#f0f0fa; --card:rgba(18,18,32,0.9); --border:rgba(255,255,255,0.1); }}
body {{ background:var(--bg); display:flex; align-items:center; justify-content:center; height:100vh; font-family:system-ui; margin:0; }}
.card {{ background:var(--card); border:1px solid var(--border); border-radius:24px; padding:30px; width:420px; }}
h1 {{ background:linear-gradient(135deg,#a855f7,#ec4899); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin:0 0 20px; }}
label {{ color:var(--text); margin:10px 0 5px; display:block; }}
select, input {{ width:100%; padding:12px; background:rgba(255,255,255,0.05); border:1px solid var(--border); border-radius:14px; color:white; margin-bottom:10px; box-sizing:border-box; }}
button {{ background:linear-gradient(135deg,#a855f7,#6366f1); color:white; border:none; padding:12px 24px; border-radius:50px; cursor:pointer; float:right; }}
.step {{ display:none; }}
.step.active {{ display:block; }}
</style></head><body>
<div class="card">
<h1>{title}</h1>
<form id="initForm">
<div class="step active" id="step1">
  <label id="step1Label">{step1_label}</label>
  <select id="langSelect" onchange="switchLanguage()">
    <option value="Chinese" selected>中文</option>
    <option value="English">English</option>
  </select>
  <button type="button" id="nextBtn1" onclick="nextStep(2)">{next_btn}</button>
</div>
<div class="step" id="step2">
  <label id="step2Label">{step2_label}</label>
  <select id="providerSelect">
    <option value="ytea">ytea (api.ytea.top/v1)</option>
    <option value="openai">openai (api.openai.com/v1)</option>
    <option value="openrouter">openrouter (openrouter.ai/api/v1)</option>
    <option value="custom" id="customOption">{custom_url_label}</option>
  </select>
  <div id="customUrlDiv" style="display:none"><input type="text" id="customUrl" placeholder="api.example.com/v1"></div>
  <button type="button" id="nextBtn2" onclick="nextStep(3)">{next_btn}</button>
</div>
<div class="step" id="step3">
  <label id="step3Label">{step3_label}</label>
  <input type="password" id="apiKey" required>
  <label id="tokenLabel">{token_label}</label>
  <input type="text" id="tokenInput" placeholder="{token_placeholder}">
  <button type="button" id="nextBtn3" onclick="nextStep(4)">{next_btn}</button>
</div>
<div class="step" id="step4">
  <label id="step4Label">{step4_label}</label>
  <select id="modelSelect"><option>{loading}</option></select>
  <button type="button" id="completeBtn" onclick="submitInit()">{complete_btn}</button>
</div>
</form></div>
<script>
// 当前语言数据，用于动态切换
const translations = {{
  Chinese: {{
    step1Label: "选择语言",
    step2Label: "AI 提供商",
    step3Label: "API Key",
    step4Label: "选择模型",
    next: "下一步",
    complete: "完成",
    loading: "加载中...",
    custom: "自定义",
    tokenLabel: "访问令牌",
    tokenPlaceholder: "留空则保持当前令牌",
    fetchFail: "获取列表失败"
  }},
  English: {{
    step1Label: "Choose Language",
    step2Label: "AI Provider",
    step3Label: "API Key",
    step4Label: "Select Model",
    next: "Next",
    complete: "Complete",
    loading: "Loading...",
    custom: "Custom",
    tokenLabel: "Access Token",
    tokenPlaceholder: "Leave blank to keep current token",
    fetchFail: "Failed to fetch models"
  }}
}};

let currentLang = '{lang}';

function switchLanguage() {{
  currentLang = document.getElementById('langSelect').value;
  const t = translations[currentLang];
  document.getElementById('step1Label').innerText = t.step1Label;
  document.getElementById('step2Label').innerText = t.step2Label;
  document.getElementById('step3Label').innerText = t.step3Label;
  document.getElementById('step4Label').innerText = t.step4Label;
  document.getElementById('customOption').innerText = t.custom;
  document.getElementById('tokenLabel').innerText = t.tokenLabel;
  document.getElementById('tokenInput').placeholder = t.tokenPlaceholder;
  document.querySelectorAll('[id^=nextBtn]').forEach(btn => btn.innerText = t.next);
  document.getElementById('completeBtn').innerText = t.complete;
  // 若当前在第四步，重新加载模型列表（语言可能影响API错误提示，但这里只需刷新模型列表）
  if (currentStep === 4) loadModels();
}}

let currentStep = 1;
function nextStep(n) {{
  document.getElementById('step'+currentStep).classList.remove('active');
  currentStep = n;
  document.getElementById('step'+currentStep).classList.add('active');
  if (n===4) loadModels();
}}
document.getElementById('providerSelect').addEventListener('change', function() {{
  document.getElementById('customUrlDiv').style.display = this.value==='custom' ? 'block' : 'none';
}});

async function loadModels() {{
  let provider = document.getElementById('providerSelect').value;
  let baseUrl;
  if (provider==='custom') {{
    baseUrl = document.getElementById('customUrl').value.trim();
  }} else {{
    const map = {{'ytea':'api.ytea.top/v1','openai':'api.openai.com/v1','openrouter':'openrouter.ai/api/v1'}};
    baseUrl = map[provider];
  }}
  let apiKey = document.getElementById('apiKey').value;
  const sel = document.getElementById('modelSelect');
  sel.innerHTML = '<option>'+translations[currentLang].loading+'</option>';
  let resp = await fetch('/api/fetch_models?base_url='+encodeURIComponent(baseUrl)+'&api_key='+encodeURIComponent(apiKey));
  let data = await resp.json();
  sel.innerHTML = '';
  if (data.models && data.models.length>0) {{
    data.models.forEach(m => {{
      let opt = document.createElement('option'); opt.value=m; opt.text=m; sel.appendChild(opt);
    }});
  }} else {{
    let opt = document.createElement('option');
    opt.text = translations[currentLang].fetchFail;
    sel.appendChild(opt);
  }}
}}

async function submitInit() {{
  let lang = document.getElementById('langSelect').value;
  let provider = document.getElementById('providerSelect').value;
  let baseUrl;
  if (provider==='custom') {{
    baseUrl = document.getElementById('customUrl').value.trim();
  }} else {{
    const map = {{'ytea':'api.ytea.top/v1','openai':'api.openai.com/v1','openrouter':'openrouter.ai/api/v1'}};
    baseUrl = map[provider];
  }}
  let apiKey = document.getElementById('apiKey').value;
  let model = document.getElementById('modelSelect').value;
  let token = document.getElementById('tokenInput').value;
  await fetch('/api/init', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{language:lang, base_url:baseUrl, api_key:apiKey, model:model, token:token}})
  }});
  window.location.href = '/';
}}

// 初始加载时根据 currentLang 设置页面语言
window.onload = function() {{
  document.getElementById('langSelect').value = currentLang;
  switchLanguage();
}};
</script>
</body></html>"""

# 主界面 HTML_MAIN 较长，此处为节省篇幅不再重复，请直接复制之前答案中修正过不再含 {% raw %} 的完整 HTML_MAIN 字符串，
# 并确保其中的样式仍使用双花括号（如 :root {{ }}），因为我们是直接返回字符串，不会有 Jinja2 解析。
# 需要注意：HTML_MAIN 也需要将固定的中文/英文文本改为通过 format 传入或使用前端多语言，但主界面已有独立的多语言 json，可维持当前设计。