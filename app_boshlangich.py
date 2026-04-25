from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

def bot_javob(savol):
    savol = savol.lower()

    if "salom" in savol:
        return "Va alaykum salom! Qanday yordam beray?"
    elif "isming" in savol:
        return "Men Baxtiyor yaratgan AI yordamchi botman."
    elif "python" in savol:
        return "Python — dasturlash tili. Unda bot, web-app, fayl generator va ilovalar qilish mumkin."
    elif "nima qila olasan" in savol:
        return "Men savollarga javob bera olaman, matn bilan ishlayman, keyinchalik fayl va ovozli xabarni ham qabul qila olaman."
    else:
        return "Bu savolga hozircha oddiy javob bera olaman. Keyin meni haqiqiy AI bilan ulash mumkin."

html = """
<!DOCTYPE html>
<html>
<head>
    <title>Baxtiyor AI</title>
    <style>
        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #212121;
            color: white;
        }

        .app {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }

        .header {
            padding: 18px;
            text-align: center;
            border-bottom: 1px solid #333;
            font-size: 22px;
            font-weight: bold;
        }

        .chat {
            flex: 1;
            padding: 25px;
            overflow-y: auto;
        }

        .msg {
            max-width: 70%;
            padding: 14px 18px;
            margin: 10px 0;
            border-radius: 18px;
            line-height: 1.4;
        }

        .user {
            background: #2f80ed;
            margin-left: auto;
            border-bottom-right-radius: 4px;
        }

        .bot {
            background: #333;
            margin-right: auto;
            border-bottom-left-radius: 4px;
        }

        .input-area {
            display: flex;
            gap: 10px;
            padding: 18px;
            border-top: 1px solid #333;
            background: #1b1b1b;
        }

        input[type="text"] {
            flex: 1;
            padding: 15px;
            border-radius: 25px;
            border: none;
            outline: none;
            background: #2b2b2b;
            color: white;
            font-size: 16px;
        }

        button, label {
            border: none;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            background: #3a3a3a;
            color: white;
            font-size: 20px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .send {
            background: #10a37f;
        }

        #file {
            display: none;
        }
    </style>
</head>
<body>
<div class="app">
    <div class="header">Baxtiyor AI</div>

    <div class="chat" id="chat">
        <div class="msg bot">Salom! Men sizning AI yordamchingizman. Savol yozing.</div>
    </div>

    <div class="input-area">
        <label for="file">📎</label>
        <input type="file" id="file">

        <button onclick="voice()">🎙️</button>

        <input type="text" id="text" placeholder="Xabar yozing..." onkeydown="if(event.key==='Enter') send()">

        <button class="send" onclick="send()">➤</button>
    </div>
</div>

<script>
function addMessage(text, type) {
    let chat = document.getElementById("chat");
    let msg = document.createElement("div");
    msg.className = "msg " + type;
    msg.innerText = text;
    chat.appendChild(msg);
    chat.scrollTop = chat.scrollHeight;
}

function send() {
    let input = document.getElementById("text");
    let text = input.value.trim();

    if (text === "") return;

    addMessage(text, "user");
    input.value = "";

    fetch("/chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message: text})
    })
    .then(res => res.json())
    .then(data => {
        addMessage(data.reply, "bot");
    });
}

document.getElementById("file").addEventListener("change", function() {
    if (this.files.length > 0) {
        addMessage("Fayl tanlandi: " + this.files[0].name, "user");
        addMessage("Hozircha faylni faqat nomi bilan qabul qilyapman. Keyin ichini ham o‘qiydigan qilamiz.", "bot");
    }
});

function voice() {
    if (!('webkitSpeechRecognition' in window)) {
        alert("Brauzeringiz ovoz tanishni qo‘llamaydi.");
        return;
    }

    let recognition = new webkitSpeechRecognition();
    recognition.lang = "uz-UZ";
    recognition.start();

    recognition.onresult = function(event) {
        document.getElementById("text").value = event.results[0][0].transcript;
    }
}
</script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(html)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "")
    reply = bot_javob(message)
    return jsonify({"reply": reply})

app.run(host="0.0.0.0", port=5000, debug=True)
