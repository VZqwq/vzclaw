import json, os, re, platform, subprocess, urllib.request, urllib.error

DATA_FILE = "aidata.json"

# ---------- 工具函数 ----------
def run_command(cmd):
    try:
        shell = platform.system() != "Windows"
        proc = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=30)
        return proc.stdout, proc.stderr, proc.returncode
    except Exception as e:
        return "", str(e), -1

def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read(), None
    except Exception as e:
        return None, str(e)

def write_file(path, content):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True, None
    except Exception as e:
        return False, str(e)

def list_directory(path):
    try:
        return "\n".join(os.listdir(path)), None
    except Exception as e:
        return None, str(e)

def extract_requests(text):
    reqs = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r"\[REQUEST:(run|read|list|write)\]\s*(.*)", line)
        if m:
            action = m.group(1)
            arg = m.group(2).strip()
            content = ""
            if action == "write":
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    i += 1
                if i < len(lines):
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith("```"):
                        content += lines[i] + "\n"
                        i += 1
                    content = content.rstrip("\n")
                reqs.append(("write", arg, content))
                i += 1
                continue
            else:
                reqs.append((action, arg, None))
        i += 1
    return reqs

def clean_reply(reply):
    lines = reply.split("\n")
    cleaned = []
    skip = False
    for line in lines:
        if re.match(r"\[REQUEST:(run|read|list|write)\]", line.strip()):
            if "write" in line.strip():
                skip = True
            continue
        if skip and line.strip().startswith("```"):
            skip = False
            continue
        if not skip:
            cleaned.append(line)
    return "\n".join(cleaned).strip()

# ---------- API ----------
def api_get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")

def fetch_model_list(base_url, api_key):
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        body = api_get(f"https://{base_url}/models", headers)
        return [m["id"] for m in json.loads(body).get("data", [])]
    except:
        return None

def chat_completion(api_key, messages, base_url, model):
    url = f"https://{base_url}/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    data = json.dumps({"model": model, "messages": messages}).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
    except:
        return None

# ---------- 持久化 & 对话管理 ----------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_conversations():
    data = load_data()
    return data.get("conversations", {})

def save_conversation(conv_id, conv_data):
    data = load_data()
    data.setdefault("conversations", {})[conv_id] = conv_data
    save_data(data)

def delete_conversation(conv_id):
    data = load_data()
    data.get("conversations", {}).pop(conv_id, None)
    save_data(data)

def create_conversation(name="新对话"):
    import uuid
    cid = str(uuid.uuid4())[:8]
    conv = {
        "name": name,
        "messages": []
    }
    save_conversation(cid, conv)
    return cid

def build_system_prompt(language):
    os_type = platform.system()
    lang_guide = {
        "Chinese": "你必须使用中文回复。",
        "English": "You must reply in English."
    }.get(language, "Reply in English.")
    tools = (
        "你可以通过以下格式请求操作：\n"
        "[REQUEST:run] 命令\n"
        "[REQUEST:read] 文件路径\n"
        "[REQUEST:list] 目录路径\n"
        "[REQUEST:write] 文件路径\n"
        "   后续用 ``` 包裹内容。保持简洁，可以适当使用emoji。"
    )
    return f"{lang_guide}\n{tools}\n系统：{os_type}"