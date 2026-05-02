import os, random, string
from webui import app
import core
from flask import session

def generate_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=16))

def main():
    data = core.load_data()
    if "token" not in data or not data["token"]:
        token = generate_token()
        data["token"] = token
        data["initialized"] = False
        core.save_data(data)
        print(f"🔑 初始访问令牌: {token}")
    else:
        print(f"🔑 当前令牌: {data['token']}")

    port = int(os.environ.get("PORT", data.get("port", 9996)))
    print(f"🌐 VZclaw 启动于 http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    main()