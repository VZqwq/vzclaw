import os
import json
from datetime import datetime
from flask import Flask, request, session, redirect, url_for, Response, jsonify
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
        "port": data.get("port", 9996),
        "api_key": data.get("api_key", "")
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

    convs = core.get_conversations()
    last_conv = session.get("last_conv", "")
    if not convs:
        cid = core.create_conversation("新对话")
        last_conv = cid
        session["last_conv"] = cid
    elif last_conv not in convs:
        first = next(iter(convs))
        last_conv = first
        session["last_conv"] = first

    return plain_response(HTML_MAIN.format(
        title=_("chat_title", cfg["language"]),
        lang=cfg["language"],
        last_conv=last_conv
    ))

# ---------- API 端点 ----------
@app.route("/api/config", methods=["GET"])
def api_get_config():
    cfg = get_config()
    has_key = bool(cfg.get("api_key"))
    return jsonify({
        "language": cfg["language"],
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "has_key": has_key,
        "port": cfg["port"],
        "token_prefix": cfg["token"][:4] + "****" if cfg["token"] else "",
        "api_key": "••••••••" if has_key else ""
    })

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
    api_key = request.args.get("api_key", "") or get_config().get("api_key", "")
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

# ---------- HTML 模板 ----------
HTML_LOGIN = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{title}</title>
<style>
:root {{ --bg:#0a0a14; --text:#f0f0fa; --card:rgba(18,18,32,0.75); --border:rgba(255,255,255,0.12); --purple:#a855f7; }}
body {{ background:var(--bg); display:flex; align-items:center; justify-content:center; height:100vh; font-family:system-ui; margin:0; }}
.card {{
  background: var(--card); backdrop-filter: blur(30px); -webkit-backdrop-filter: blur(30px);
  border:1px solid var(--border); border-radius:28px; padding:48px 36px; width:380px; text-align:center;
  box-shadow: 0 20px 40px rgba(0,0,0,0.6);
}}
h1 {{ background:linear-gradient(135deg,#a855f7,#ec4899); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin:0 0 24px; font-size:2rem; }}
.token-icon {{ font-size:2.5rem; margin-bottom:12px; }}
input {{
  width:100%; padding:16px 20px; background:rgba(255,255,255,0.06); border:2px solid rgba(255,255,255,0.15);
  border-radius:16px; color:white; font-size:1rem; margin:16px 0; box-sizing:border-box;
  transition: border-color 0.2s, box-shadow 0.2s;
}}
input:focus {{ border-color: var(--purple); box-shadow: 0 0 0 3px rgba(168,85,247,0.3); outline:none; }}
button {{
  width:100%; padding:16px; background:linear-gradient(135deg,var(--purple),#6366f1);
  border:none; border-radius:50px; color:white; font-size:1.1rem; font-weight:600; cursor:pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}}
button:hover {{ transform: translateY(-2px); box-shadow: 0 8px 20px rgba(168,85,247,0.4); }}
.error {{ color:#f87171; margin-top:14px; font-size:0.9rem; }}
</style></head><body>
<div class="card">
<div class="token-icon">🔑</div>
<h1>{title}</h1>
<p style="color:#b9b9d4; margin-bottom:12px;">{prompt}</p>
<form method="POST">
<input type="password" name="token" placeholder="粘贴访问令牌" required>
<button type="submit">{button}</button>
</form>
<p class="error">{error}</p>
</div></body></html>"""

HTML_INIT = """<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{title}</title>
<style>
:root {{ --bg:#0a0a14; --text:#f0f0fa; --card:rgba(18,18,32,0.75); --border:rgba(255,255,255,0.12); }}
body {{ background:var(--bg); display:flex; align-items:center; justify-content:center; height:100vh; font-family:system-ui; margin:0; }}
.card {{ background:var(--card); backdrop-filter:blur(30px); border:1px solid var(--border); border-radius:28px; padding:36px; width:420px; box-shadow:0 20px 40px rgba(0,0,0,0.5); }}
h1 {{ background:linear-gradient(135deg,#a855f7,#ec4899); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin:0 0 24px; }}
label {{ color:var(--text); margin:14px 0 6px; display:block; font-weight:500; }}
select, input {{ width:100%; padding:14px; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.15); border-radius:14px; color:white; margin-bottom:12px; box-sizing:border-box; }}
button {{ background:linear-gradient(135deg,#a855f7,#6366f1); color:white; border:none; padding:12px 28px; border-radius:50px; cursor:pointer; float:right; font-weight:600; }}
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
const translations = {{
  Chinese: {{ step1Label:"选择语言", step2Label:"AI 提供商", step3Label:"API Key", step4Label:"选择模型", next:"下一步", complete:"完成", loading:"加载中...", custom:"自定义", tokenLabel:"访问令牌", tokenPlaceholder:"留空则保持当前令牌", fetchFail:"获取列表失败" }},
  English: {{ step1Label:"Choose Language", step2Label:"AI Provider", step3Label:"API Key", step4Label:"Select Model", next:"Next", complete:"Complete", loading:"Loading...", custom:"Custom", tokenLabel:"Access Token", tokenPlaceholder:"Leave blank to keep current token", fetchFail:"Failed to fetch models" }}
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
  let baseUrl = provider==='custom' ? document.getElementById('customUrl').value.trim() : {{'ytea':'api.ytea.top/v1','openai':'api.openai.com/v1','openrouter':'openrouter.ai/api/v1'}}[provider];
  let apiKey = document.getElementById('apiKey').value;
  const sel = document.getElementById('modelSelect');
  sel.innerHTML = '<option>'+translations[currentLang].loading+'</option>';
  let resp = await fetch('/api/fetch_models?base_url='+encodeURIComponent(baseUrl)+'&api_key='+encodeURIComponent(apiKey));
  let data = await resp.json();
  sel.innerHTML = '';
  if (data.models && data.models.length>0) {{
    data.models.forEach(m => {{ let opt = document.createElement('option'); opt.value=m; opt.text=m; sel.appendChild(opt); }});
  }} else {{
    let opt = document.createElement('option'); opt.text = translations[currentLang].fetchFail; sel.appendChild(opt);
  }}
}}
async function submitInit() {{
  let lang = document.getElementById('langSelect').value;
  let provider = document.getElementById('providerSelect').value;
  let baseUrl = provider==='custom' ? document.getElementById('customUrl').value.trim() : {{'ytea':'api.ytea.top/v1','openai':'api.openai.com/v1','openrouter':'openrouter.ai/api/v1'}}[provider];
  let apiKey = document.getElementById('apiKey').value;
  let model = document.getElementById('modelSelect').value;
  let token = document.getElementById('tokenInput').value;
  await fetch('/api/init', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{language:lang, base_url:baseUrl, api_key:apiKey, model:model, token:token}}) }});
  window.location.href = '/';
}}
window.onload = function() {{ document.getElementById('langSelect').value = currentLang; switchLanguage(); }};
</script>
</body></html>"""

HTML_MAIN = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes, viewport-fit=cover">
<title>{title}</title>
<style>
:root {{
  --bg: #0a0a14;
  --text: #f0f0fa;
  --text2: #b9b9d4;
  --surface: rgba(18,18,32,0.7);
  --border: rgba(255,255,255,0.1);
  --purple: #a855f7;
  --pink: #ec4899;
  --radius: 18px;
  font-family: system-ui, 'PingFang SC', sans-serif;
}}
* {{ box-sizing: border-box; margin:0; padding:0; }}
body {{ background:var(--bg); color:var(--text); height:100vh; display:flex; }}
/* 侧边栏 */
.sidebar {{
  width: 270px; background: var(--surface); backdrop-filter: blur(30px); -webkit-backdrop-filter: blur(30px);
  border-right: 1px solid var(--border); display:flex; flex-direction:column; padding:20px 14px;
  flex-shrink:0; z-index:10;
}}
.sidebar h3 {{
  font-size: 1.5rem; background: linear-gradient(135deg, var(--purple), var(--pink));
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin-bottom:20px; text-align:center;
}}
.conv-list {{ flex:1; overflow-y:auto; min-height:0; }}
.conv-item {{
  display:flex; align-items:center; justify-content:space-between; padding:12px 14px;
  border-radius:14px; cursor:pointer; margin-bottom:6px; color:var(--text2);
  transition: background 0.2s, color 0.2s;
}}
.conv-item:hover {{ background:rgba(255,255,255,0.08); }}
.conv-item.active {{ background:rgba(168,85,247,0.2); color:white; }}
.conv-name {{ flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.conv-actions {{ position:relative; visibility:hidden; }}
.conv-item:hover .conv-actions {{ visibility:visible; }}
.dots-btn {{ background:none; border:none; color:var(--text2); font-size:20px; cursor:pointer; padding:0 6px; }}
.dropdown {{
  display:none; position:absolute; right:0; top:100%; background:#2a2a3c; border:1px solid var(--border);
  border-radius:10px; padding:6px 0; min-width:110px; z-index:20;
}}
.dropdown.show {{ display:block; }}
.dropdown-item {{ padding:8px 14px; font-size:0.85rem; cursor:pointer; color:var(--text2); }}
.dropdown-item:hover {{ background:rgba(255,255,255,0.1); }}
.new-chat-btn {{
  margin-top:16px; padding:14px; background:linear-gradient(135deg, var(--purple), #6366f1);
  border:none; border-radius:50px; color:white; font-size:0.95rem; font-weight:600; cursor:pointer;
  transition: transform 0.2s, box-shadow 0.2s; flex-shrink:0;
}}
.new-chat-btn:hover {{ transform:translateY(-2px); box-shadow:0 8px 20px rgba(168,85,247,0.4); }}
/* 主区域 */
.main {{
  flex:1; display:flex; flex-direction:column; min-width:0;
}}
.header {{
  padding:14px 24px; border-bottom:1px solid var(--border); display:flex;
  justify-content:space-between; align-items:center; background:rgba(18,18,32,0.4);
  backdrop-filter:blur(20px); flex-shrink:0;
}}
.header h2 {{ font-size:1.3rem; }}
/* 聊天区域：占据剩余空间，可滚动 */
.chat-area {{
  flex:1; overflow-y:auto; padding:24px; display:flex; flex-direction:column; gap:14px;
  background: rgba(10,10,20,0.4); backdrop-filter:blur(10px);
}}
.msg {{ max-width:72%; padding:12px 18px; border-radius:20px; line-height:1.6; word-break:break-word; }}
.msg.user {{ align-self:flex-end; background:rgba(168,85,247,0.25); border:1px solid rgba(168,85,247,0.4); }}
.msg.ai {{ align-self:flex-start; background:rgba(255,255,255,0.06); border:1px solid var(--border); }}
.empty-hint {{
  align-self:center; margin:auto; color:var(--text2); opacity:0.6; font-size:0.95rem;
  text-align:center;
}}
/* 输入区域固定在底部 */
.input-area {{
  padding:14px 24px; border-top:1px solid var(--border); display:flex; gap:10px;
  background:rgba(18,18,32,0.6); backdrop-filter:blur(20px); flex-shrink:0;
}}
.input-area input {{
  flex:1; padding:14px 20px; background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.15);
  border-radius:50px; color:white; outline:none; font-size:1rem;
  transition: border-color 0.2s;
}}
.input-area input:focus {{ border-color:var(--purple); }}
.btn {{
  padding:10px 22px; background:rgba(255,255,255,0.06); border:1px solid var(--border);
  border-radius:50px; color:var(--text2); cursor:pointer; font-size:0.9rem; transition:0.2s;
}}
.btn-primary {{ background:linear-gradient(135deg, var(--purple), #6366f1); color:white; border:none; }}
/* 模态框 */
.modal {{
  display:none; position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:100;
  justify-content:center; align-items:center; backdrop-filter:blur(6px);
}}
.modal.active {{ display:flex; }}
.modal-card {{
  background: var(--surface); backdrop-filter:blur(30px); border:1px solid var(--border);
  border-radius:24px; padding:28px; width:90%; max-width:420px; box-shadow:0 20px 40px rgba(0,0,0,0.6);
}}
.modal-card h3 {{ margin-bottom:18px; }}
.modal-card input, .modal-card select {{
  width:100%; padding:14px; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.15);
  border-radius:14px; color:white; margin-bottom:14px; box-sizing:border-box;
}}
.actions {{ display:flex; justify-content:flex-end; gap:10px; margin-top:10px; }}
/* 手机 */
@media (max-width: 768px) {{
  body {{ flex-direction:column; }}
  .sidebar {{
    width:100%; max-height:35vh; border-right:none; border-bottom:1px solid var(--border);
    padding:12px;
  }}
  .main {{ height:65vh; }} /* 限定高度让输入框可见 */
  .header {{ padding:10px 16px; }}
  .header h2 {{ font-size:1rem; }}
  .chat-area {{ padding:14px; }}
  .msg {{ max-width:85%; }}
  .input-area {{ padding:10px 16px; }}
  .input-area input {{ padding:12px 16px; font-size:0.9rem; }}
}}
</style>
</head>
<body>
<div class="sidebar">
  <h3>VZclaw</h3>
  <div class="conv-list" id="convList"></div>
  <button class="new-chat-btn" onclick="newConversation()">＋ 新对话</button>
</div>
<div class="main">
  <div class="header">
    <h2 id="convTitle">选择对话</h2>
    <button class="btn" onclick="openSettings()">设置</button>
  </div>
  <div class="chat-area" id="chatArea">
    <div class="empty-hint">✨ 点击左侧对话开始聊天</div>
  </div>
  <div class="input-area">
    <input type="text" id="msgInput" placeholder="输入消息..." onkeydown="if(event.key==='Enter') sendMessage()">
    <button class="btn btn-primary" onclick="sendMessage()">发送</button>
  </div>
</div>

<!-- 设置弹窗 -->
<div class="modal" id="settingsModal">
  <div class="modal-card">
    <h3>设置</h3>
    <label>Base URL</label>
    <input type="text" id="setBaseUrl">
    <label>API Key</label>
    <input type="password" id="setApiKey" placeholder="留空则保持不变">
    <label>模型</label>
    <select id="setModel"></select>
    <label>语言</label>
    <select id="setLanguage"><option value="Chinese">中文</option><option value="English">English</option></select>
    <label>访问令牌</label>
    <input type="text" id="setToken">
    <div class="actions">
      <button class="btn" onclick="closeSettings()">取消</button>
      <button class="btn btn-primary" onclick="saveSettings()">保存</button>
    </div>
  </div>
</div>

<!-- 操作确认弹窗 -->
<div class="modal" id="confirmModal">
  <div class="modal-card">
    <h3>确认操作</h3>
    <p id="confirmText"></p>
    <div class="actions">
      <button class="btn" onclick="respondConfirm(false)">拒绝</button>
      <button class="btn btn-primary" onclick="respondConfirm(true)">允许</button>
    </div>
  </div>
</div>

<!-- 重命名弹窗 -->
<div class="modal" id="renameModal">
  <div class="modal-card">
    <h3>重命名对话</h3>
    <input type="text" id="renameInput" placeholder="输入新名称">
    <div class="actions">
      <button class="btn" onclick="closeRename()">取消</button>
      <button class="btn btn-primary" onclick="confirmRename()">确定</button>
    </div>
  </div>
</div>

<!-- 删除确认弹窗 -->
<div class="modal" id="deleteModal">
  <div class="modal-card">
    <h3>删除对话</h3>
    <p>确定要删除这个对话吗？此操作不可撤销。</p>
    <div class="actions">
      <button class="btn" onclick="closeDelete()">取消</button>
      <button class="btn btn-primary" style="background:#ef4444;" onclick="confirmDelete()">删除</button>
    </div>
  </div>
</div>

<script>
const LAST_CONV = "{last_conv}";
let currentConvId = null;
let pendingConfirm = null;
let renameCid = null;
let deleteCid = null;

async function loadConversations() {{
  let res = await fetch('/api/conversations');
  let convs = await res.json();
  let list = document.getElementById('convList');
  list.innerHTML = '';

  if (convs.length === 0) {{
    await newConversation(true);
    return;
  }}

  convs.forEach(c => {{
    let item = document.createElement('div');
    item.className = 'conv-item' + (c.id === currentConvId ? ' active' : '');
    item.innerHTML = `<span class="conv-name" onclick="switchConversation('${{c.id}}')">${{c.name}}</span>
      <div class="conv-actions">
        <button class="dots-btn" onclick="toggleDropdown(event, '${{c.id}}')">⋯</button>
        <div class="dropdown" id="dropdown-${{c.id}}">
          <div class="dropdown-item" onclick="openRename('${{c.id}}')">重命名</div>
          <div class="dropdown-item" onclick="openDelete('${{c.id}}')">删除</div>
        </div>
      </div>`;
    list.appendChild(item);
  }});

  if (!currentConvId) {{
    let target = convs.find(c => c.id === LAST_CONV) || convs[0];
    if (target) {{
      switchConversation(target.id);
    }}
  }}
}}

function toggleDropdown(e, cid) {{
  e.stopPropagation();
  let dropdown = document.getElementById('dropdown-' + cid);
  document.querySelectorAll('.dropdown').forEach(d => d.classList.remove('show'));
  dropdown.classList.toggle('show');
}}
document.addEventListener('click', () => {{ document.querySelectorAll('.dropdown').forEach(d => d.classList.remove('show')); }});

async function switchConversation(cid) {{
  currentConvId = cid;
  document.getElementById('convTitle').innerText = (await getConvName(cid)) || '对话';
  loadHistory();
  loadConversations();
}}
async function getConvName(cid) {{
  let res = await fetch('/api/conversations'); let convs = await res.json();
  let c = convs.find(c => c.id === cid); return c ? c.name : null;
}}
async function newConversation(silent) {{
  let res = await fetch('/api/conversations', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{name:'新对话'}}) }});
  let data = await res.json(); currentConvId = data.id;
  if (!silent) {{ loadConversations(); switchConversation(data.id); }} else {{ loadConversations(); }}
}}

// 重命名
function openRename(cid) {{ renameCid = cid; document.getElementById('renameInput').value = ''; document.getElementById('renameModal').classList.add('active'); }}
function closeRename() {{ document.getElementById('renameModal').classList.remove('active'); renameCid = null; }}
async function confirmRename() {{
  let name = document.getElementById('renameInput').value.trim();
  if (name && renameCid) {{
    await fetch('/api/conversations/'+renameCid, {{ method:'PUT', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{name:name}}) }});
    loadConversations(); if (currentConvId === renameCid) document.getElementById('convTitle').innerText = name;
  }}
  closeRename();
}}

// 删除
function openDelete(cid) {{ deleteCid = cid; document.getElementById('deleteModal').classList.add('active'); }}
function closeDelete() {{ document.getElementById('deleteModal').classList.remove('active'); deleteCid = null; }}
async function confirmDelete() {{
  if (deleteCid) {{
    await fetch('/api/conversations/'+deleteCid, {{ method:'DELETE' }});
    if (currentConvId === deleteCid) {{
      currentConvId = null; document.getElementById('chatArea').innerHTML = ''; document.getElementById('convTitle').innerText = '选择对话';
    }}
    loadConversations();
  }}
  closeDelete();
}}

async function loadHistory() {{
  if (!currentConvId) return;
  let res = await fetch('/api/history/'+currentConvId); let data = await res.json();
  let area = document.getElementById('chatArea'); area.innerHTML = '';
  data.history.forEach(m => {{
    let div = document.createElement('div'); div.className = 'msg ' + m.role; div.innerText = m.content; area.appendChild(div);
  }});
  area.scrollTop = area.scrollHeight;
}}

async function sendMessage() {{
  if (!currentConvId) {{ alert('请先创建或选择对话'); return; }}
  let input = document.getElementById('msgInput'); let msg = input.value.trim(); if (!msg) return;
  input.value = '';
  let div = document.createElement('div'); div.className = 'msg user'; div.innerText = msg;
  document.getElementById('chatArea').appendChild(div);
  let think = document.createElement('div'); think.className = 'msg ai'; think.innerText = '思考中...';
  document.getElementById('chatArea').appendChild(think);
  document.getElementById('chatArea').scrollTop = document.getElementById('chatArea').scrollHeight;
  let res = await fetch('/api/chat', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{convId:currentConvId, message:msg}}) }});
  think.remove();
  let data = await res.json();
  if (data.error) {{ let errDiv = document.createElement('div'); errDiv.className = 'msg ai'; errDiv.innerText = '错误: ' + data.error; document.getElementById('chatArea').appendChild(errDiv); return; }}
  if (data.reply) {{ let aiDiv = document.createElement('div'); aiDiv.className = 'msg ai'; aiDiv.innerText = data.reply; document.getElementById('chatArea').appendChild(aiDiv); }}
  if (data.auto_exec) {{ let autoDiv = document.createElement('div'); autoDiv.className = 'msg ai'; autoDiv.innerText = '📂 ' + data.auto_exec; document.getElementById('chatArea').appendChild(autoDiv); }}
  if (data.requests && data.requests.length > 0) {{
    let req = data.requests[0]; pendingConfirm = req;
    document.getElementById('confirmText').innerText = req.action + ': ' + req.arg;
    document.getElementById('confirmModal').classList.add('active');
  }}
  document.getElementById('chatArea').scrollTop = document.getElementById('chatArea').scrollHeight;
}}

async function respondConfirm(allow) {{
  document.getElementById('confirmModal').classList.remove('active');
  if (!pendingConfirm || !currentConvId) return;
  let res = await fetch('/api/execute', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{ convId:currentConvId, action:pendingConfirm.action, arg:pendingConfirm.arg, content:pendingConfirm.content||'', confirm:allow }}) }});
  pendingConfirm = null;
  let data = await res.json();
  if (data.reply) {{ let div = document.createElement('div'); div.className = 'msg ai'; div.innerText = data.reply; document.getElementById('chatArea').appendChild(div); document.getElementById('chatArea').scrollTop = document.getElementById('chatArea').scrollHeight; }}
}}

async function openSettings() {{
  let resp = await fetch('/api/config'); let cfg = await resp.json();
  document.getElementById('setBaseUrl').value = cfg.base_url || '';
  document.getElementById('setLanguage').value = cfg.language || 'Chinese';
  document.getElementById('setApiKey').value = cfg.api_key || '';
  document.getElementById('setToken').value = cfg.token_prefix || '';
  let modelResp = await fetch('/api/fetch_models?base_url=' + encodeURIComponent(cfg.base_url));
  let modelData = await modelResp.json();
  let sel = document.getElementById('setModel'); sel.innerHTML = '';
  if (modelData.models) {{
    modelData.models.forEach(m => {{ let opt = document.createElement('option'); opt.value=m; opt.text=m; sel.appendChild(opt); }});
    sel.value = cfg.model;
  }}
  document.getElementById('settingsModal').classList.add('active');
}}
function closeSettings() {{ document.getElementById('settingsModal').classList.remove('active'); }}
async function saveSettings() {{
  let config = {{
    base_url: document.getElementById('setBaseUrl').value,
    language: document.getElementById('setLanguage').value,
    model: document.getElementById('setModel').value,
    token: document.getElementById('setToken').value
  }};
  let apiKey = document.getElementById('setApiKey').value;
  if (apiKey) config.api_key = apiKey;
  await fetch('/api/config', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(config) }});
  closeSettings(); location.reload();
}}

window.onload = () => {{ loadConversations(); }};
</script>
</body>
</html>
"""