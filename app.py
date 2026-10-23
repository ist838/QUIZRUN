
import os
import time
import random
import string
import html
from threading import RLock

from flask import Flask, request, render_template_string
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

rooms = {}
lock = RLock()

MODES = ["우주선", "우주 아이템전", "땅따먹기", "사막 위 자동차", "일반"]
TYPES = ["OX", "객관식", "번호 선택형"]
ITEMS = ["흡수", "우주 쓰레기", "총", "공기", "물",
         "초거대 블랙홀", "소형 블랙홀", "중형 블랙홀", "보급품"]

STYLE = """
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Noto+Sans+KR:wght@400;600;800&display=swap');
:root{--bg:#080914;--panel:#121428;--line:#303253;--purple:#a855f7;--blue:#38bdf8}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(ellipse at 10% 0%,#29104b,transparent 40%),radial-gradient(ellipse at 95% 25%,#092849,transparent 35%),var(--bg);color:#f5f5ff;font-family:'Noto Sans KR',sans-serif}
nav{display:flex;justify-content:space-between;align-items:center;padding:20px max(18px,calc((100% - 950px)/2));border-bottom:1px solid #ffffff18}
nav a{color:#c4b5fd;text-decoration:none;margin-left:15px}
.brand{font:800 22px Orbitron;color:white}
main{max-width:950px;margin:35px auto;padding:0 18px}
.hero{text-align:center;padding:55px 0}
h1{font-size:clamp(32px,6vw,55px);line-height:1.25}
h1 span{background:linear-gradient(90deg,#c084fc,#38bdf8);color:transparent;background-clip:text}
h2{margin-top:28px}p,.muted{color:#a7a8c9;line-height:1.7}
.panel,.tile{background:linear-gradient(145deg,#15172e,#0c0d1c);border:1px solid var(--line);border-radius:18px;padding:25px;margin:15px 0}
.btn,button{display:inline-block;border:1px solid #41436b;border-radius:11px;padding:12px 17px;background:#1a1c36;color:white;text-decoration:none;font:600 14px inherit;cursor:pointer}
.primary{background:linear-gradient(100deg,#7c3aed,#2563eb);border:0}
.full{width:100%;margin-top:12px}
input,select,textarea{display:block;width:100%;margin-top:7px;padding:12px;background:#090a18;border:1px solid #343657;border-radius:9px;color:white;font:inherit}
label{display:block;margin:13px 0;font-size:13px;color:#dadaf3}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.modes{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:30px}
.tile{text-align:center;padding:18px 8px;margin:0}
small{color:#a7a8c9}.hidden{display:none!important}
.code{font:800 40px Orbitron;color:#67e8f9;letter-spacing:7px;text-align:center;margin:20px}
.answers{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.answers button{text-align:left;min-height:55px}
.notice{color:#c4b5fd;min-height:20px}
li{padding:10px;border-bottom:1px solid #ffffff14}
.question-editor{border:1px solid #38395e;border-radius:12px;padding:16px;margin:12px 0}
@media(max-width:650px){.modes{grid-template-columns:repeat(2,1fr)}.grid,.answers{grid-template-columns:1fr}nav{padding:16px;flex-wrap:wrap}main{margin-top:20px}}
"""

BASE = """
<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} · QuizRun</title>
<style>""" + STYLE + """</style>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
</head><body>
<nav><a class="brand" href="/">✦ QuizRun</a>
<div><a href="/teach">교사 페이지</a><a href="/play">게임 참가</a></div></nav>
<main>{{ content|safe }}</main>
<footer style="text-align:center;color:#777895;padding:25px">QUIZRUN · PLAY • LEARN • WIN</footer>
{{ scripts|safe }}
</body></html>
"""

def page(title, content, scripts=""):
    return render_template_string(BASE, title=title, content=content, scripts=scripts)

def new_code():
    while True:
        code = "".join(random.choices(string.digits, k=6))
        if code not in rooms:
            return code

def public_room(room):
    return {
        "code": room["code"], "name": room["name"],
        "grade": room["grade"], "subject": room["subject"],
        "mode": room["mode"], "play_type": room["play_type"],
        "seconds": room["seconds"], "status": room["status"],
        "questions": room["questions"],
        "question_index": room["question_index"],
        "current": room["current"],
        "players": [
            {"id": pid, "name": p["name"], "score": p["score"],
             "team": p["team"], "answered": p["answered"]}
            for pid, p in room["players"].items()
        ]
    }

def broadcast(code):
    if code in rooms:
        socketio.emit("room_update", public_room(rooms[code]), to=code)

def is_teacher(room):
    return request.sid == room["teacher"]

@app.get("/")
def home():
    content = """
    <section class="hero">
      <p>✦ THE UNIVERSE OF QUIZZES</p>
      <h1>정답을 맞히고,<br><span>우주를 정복해!</span></h1>
      <p>실시간 퀴즈 · 우주 아이템전 · 땅따먹기</p>
      <p><a class="btn primary" href="/teach">＋ 교사: 방 만들기</a>
      <a class="btn" href="/play">학생: 참가하기 ↗</a></p>
      <div class="modes">
        <div class="tile">🚀<p>우주선</p></div>
        <div class="tile">🌌<p>우주 아이템전</p></div>
        <div class="tile">🗺️<p>땅따먹기</p></div>
        <div class="tile">🏎️<p>사막 자동차</p></div>
        <div class="tile">🎯<p>일반 퀴즈</p></div>
      </div>
    </section>"""
    return page("홈", content)

@app.get("/teach")
def teach():
    content = """
    <section class="panel">
      <p>TEACHER CONTROL</p><h1>게임방 만들기</h1>
      <label>방 이름<input id="name" value="우리 반 퀴즈" maxlength="80"></label>
      <div class="grid">
        <label>학년<select id="grade">
          <option>학년 제한 없음</option><option>초등학교 1~2학년</option>
          <option>초등학교 3~4학년</option><option>초등학교 5~6학년</option>
          <option>중학교</option><option>고등학교</option>
        </select></label>
        <label>과목<select id="subject">
          <option>기타</option><option>국어</option><option>수학</option>
          <option>영어</option><option>과학</option><option>사회</option><option>정보</option>
        </select></label>
      </div>
      <label>게임 종류<select id="mode">
        <option>우주선</option><option>우주 아이템전</option>
        <option>땅따먹기</option><option>사막 위 자동차</option><option>일반</option>
      </select></label>
      <label id="teamwrap" class="hidden">땅따먹기 방식<select id="play_type">
        <option>개인전</option><option>팀전</option>
      </select></label>
      <label>문제당 제한 시간<select id="seconds">
        <option value="10">10초</option><option value="20" selected>20초</option>
        <option value="30">30초</option><option value="60">60초</option>
      </select></label>
      <button class="btn primary full" id="create">방 생성</button>
      <p id="status" class="notice"></p>
      <div id="created" class="hidden">
        <h2>방 생성 완료!</h2><div class="code" id="code"></div>
        <div id="qr" style="background:white;padding:10px;width:max-content;margin:auto"></div>
        <p id="link" style="text-align:center"></p>
        <button id="copy">초대 링크 복사</button>
        <a id="open" class="btn primary">교사 대기실 열기</a>
      </div>
    </section>
    <section class="panel">
      <h2>📝 퀴즈 직접 만들기</h2>
      <p>방을 만든 뒤 문제를 여러 개 추가할 수 있어요. OX, 객관식, 번호 선택형을 지원해요.</p>
      <p>문제 편집은 방을 만든 교사만 할 수 있어요.</p>
    </section>"""
    scripts = """
    <script>
    const s=io(), mode=document.getElementById('mode');
    mode.onchange=()=>document.getElementById('teamwrap').classList.toggle('hidden',mode.value!=='땅따먹기');
    document.getElementById('create').onclick=()=>s.emit('create_room',{
      name:document.getElementById('name').value,
      grade:document.getElementById('grade').value,
      subject:document.getElementById('subject').value,
      mode:mode.value,play_type:document.getElementById('play_type').value,
      seconds:Number(document.getElementById('seconds').value)});
    s.on('room_created',d=>{
      const url=location.origin+'/play?code='+d.code;
      document.getElementById('created').classList.remove('hidden');
      document.getElementById('code').textContent=d.code;
      document.getElementById('link').textContent=url;
      document.getElementById('open').href='/room/'+d.code;
      document.getElementById('open').onclick=()=>sessionStorage.setItem('teacher_'+d.code,'1');
      document.getElementById('qr').innerHTML='';
      new QRCode(document.getElementById('qr'),{text:url,width:180,height:180});
      document.getElementById('status').textContent='방이 만들어졌어요!';
    });
    document.getElementById('copy').onclick=async()=>{
      await navigator.clipboard.writeText(document.getElementById('link').textContent);
      document.getElementById('copy').textContent='복사 완료!';
    };
    s.on('connect_error',()=>document.getElementById('status').textContent='서버 연결에 실패했어요.');
    </script>"""
    return page("교사", content, scripts)

@app.get("/play")
def play():
    content = """
    <section class="panel" style="max-width:500px;margin:auto">
      <h1>게임 참가하기</h1><p>선생님에게 받은 방 번호와 닉네임을 입력하세요.</p>
      <label>6자리 방 번호<input id="code" maxlength="6" inputmode="numeric"></label>
      <label>닉네임<input id="name" maxlength="24" placeholder="별빛학생"></label>
      <button class="btn primary full" id="join">참가하기 →</button><p id="status" class="notice"></p>
    </section>"""
    scripts = """
    <script>
    const s=io(),params=new URLSearchParams(location.search);
    document.getElementById('code').value=params.get('code')||'';
    document.getElementById('join').onclick=()=>{
      const code=document.getElementById('code').value.trim();
      const name=document.getElementById('name').value.trim();
      if(!/^\\d{6}$/.test(code)||!name){document.getElementById('status').textContent='방 번호 6자리와 닉네임을 입력해 주세요.';return}
      s.emit('join_game',{code,name});
    };
    s.on('joined_game',d=>location.href='/room/'+d.code);
    s.on('join_error',d=>document.getElementById('status').textContent=d.message);
    </script>"""
    return page("학생 입장", content, scripts)

@app.get("/room/<code>")
def room_page(code):
    if code not in rooms:
        return page("방 없음", '<section class="panel"><h1>방을 찾을 수 없어요.</h1><a href="/play">다시 입장하기</a></section>'), 404
    content = """
    <section class="panel">
      <p>LIVE ARENA · ROOM <b id="code"></b></p><h1 id="roomname">QuizRun</h1>
      <p>게임: <b id="mode"></b> · <span id="grade"></span> · <span id="subject"></span></p>
      <p>상태: <b id="state">연결 중</b> · 참가자: <b id="count">0</b>명</p>
      <div id="teacher" class="hidden">
        <h2>교사용 컨트롤</h2>
        <button class="btn primary" id="start">게임 시작</button>
        <h2>문제 만들기</h2>
        <label>문제 유형<select id="type">
          <option>OX</option><option>객관식</option><option>번호 선택형</option>
        </select></label>
        <label>문제 내용<input id="question" placeholder="예: 지구는 태양 주위를 돈다."></label>
        <div id="optionarea"></div>
        <label>정답<select id="correct"></select></label>
        <button class="btn" id="addoption">＋ 선택지 추가</button>
        <button class="btn primary" id="addquestion">문제 추가</button>
        <p id="teachstatus" class="notice"></p>
        <h2>등록된 문제</h2><ol id="questionlist"></ol>
        <button class="btn primary" id="publish">첫 문제 출제 / 다음 문제</button>
      </div>
      <div id="student" class="hidden">
        <h2 id="questiontext">선생님을 기다려 주세요.</h2>
        <div id="answers" class="answers"></div><p id="answerstatus" class="notice"></p>
        <div id="items" class="hidden">
          <h2>🌌 우주 아이템</h2>
          <div class="grid">
            <label>아이템<select id="item">""" + "".join(f"<option>{x}</option>" for x in ITEMS) + """</select></label>
            <label>상대<select id="target"></select></label>
            <label>비율<select id="percent"><option>5</option><option>15</option><option>25</option><option>50</option></select></label>
            <label>물 포인트<select id="amount"><option>50</option><option>100</option><option>500</option><option>1000</option></select></label>
          </div><button id="useitem">아이템 사용</button>
        </div>
      </div>
      <h2>🏆 실시간 순위</h2><ol id="board"></ol><p id="notice" class="notice"></p>
    </section>"""
    scripts = """
    <script>
    const s=io(),code=location.pathname.split('/').pop();
    let teacher=sessionStorage.getItem('teacher_'+code)==='1',room=null,opts=['O','X'],answered=false;
    document.getElementById('code').textContent=code;
    document.getElementById(teacher?'teacher':'student').classList.remove('hidden');
    function optionUI(){
      const type=document.getElementById('type').value;
      if(type==='OX')opts=['O','X'];
      else if(opts.length<2)opts=['선택지 1','선택지 2'];
      renderOpts();
    }
    function renderOpts(){
      const area=document.getElementById('optionarea'),sel=document.getElementById('correct');
      area.innerHTML='';sel.innerHTML='';
      opts.forEach((v,i)=>{
        let l=document.createElement('label');l.textContent='선택지 '+(i+1);
        let inp=document.createElement('input');inp.value=v;inp.maxLength=160;
        inp.oninput=()=>{opts[i]=inp.value;let old=sel.value;sel.options[i].text=(i+1)+'. '+opts[i]};
        l.appendChild(inp);area.appendChild(l);
        let o=document.createElement('option');o.value=i;o.textContent=(i+1)+'. '+v;sel.appendChild(o);
      });
    }
    if(teacher){
      optionUI();
      document.getElementById('type').onchange=()=>optionUI();
      document.getElementById('addoption').onclick=()=>{
        if(document.getElementById('type').value==='OX'){return}
        if(opts.length>=6){document.getElementById('teachstatus').textContent='선택지는 최대 6개예요.';return}
        opts.push('선택지 '+(opts.length+1));renderOpts();
      };
      document.getElementById('addquestion').onclick=()=>{
        s.emit('add_question',{code,type:document.getElementById('type').value,
          text:document.getElementById('question').value,options:opts,
          correct:Number(document.getElementById('correct').value)});
      };
      document.getElementById('publish').onclick=()=>s.emit('publish_question',{code});
      document.getElementById('start').onclick=()=>s.emit('start_game',{code});
    }
    s.emit('get_room',{code});
    s.on('question_added',d=>{document.getElementById('teachstatus').textContent=d.message;document.getElementById('question').value='';});
    s.on('action_error',d=>document.getElementById('notice').textContent=d.message);
    s.on('room_update',r=>{
      room=r;document.getElementById('roomname').textContent=r.name;
      document.getElementById('mode').textContent=r.mode;
      document.getElementById('grade').textContent=r.grade;
      document.getElementById('subject').textContent=r.subject;
      document.getElementById('state').textContent=r.status;
      document.getElementById('count').textContent=r.players.length;
      document.getElementById('board').innerHTML='';
      [...r.players].sort((a,b)=>b.score-a.score).forEach((p,i)=>{
        let li=document.createElement('li');li.textContent=(i+1)+'. '+p.name+' — '+p.score.toLocaleString()+'P'+(p.team?' · '+p.team:'');
        document.getElementById('board').appendChild(li);
      });
      document.getElementById('target').innerHTML=r.players.filter(p=>p.id!==s.id).map(p=>'<option value="'+p.id+'">'+esc(p.name)+'</option>').join('');
      if(teacher){
        document.getElementById('questionlist').innerHTML='';
        r.questions.forEach((q,i)=>{let li=document.createElement('li');li.textContent=(i+1)+'. ['+q.type+'] '+q.text;document.getElementById('questionlist').appendChild(li)});
      }
      if(r.current){
        answered=false;
        document.getElementById('questiontext').textContent=r.current.text+' ('+r.current.type+')';
        if(!teacher){
          document.getElementById('answers').innerHTML='';
          r.current.options.forEach((o,i)=>{
            let b=document.createElement('button');b.textContent=(r.current.type==='OX'?'':(i+1)+'. ')+o;
            b.onclick=()=>{if(answered)return;answered=true;s.emit('answer',{code,choice:i});document.querySelectorAll('#answers button').forEach(x=>x.disabled=true)};
            document.getElementById('answers').appendChild(b);
          });
          document.getElementById('items').classList.toggle('hidden',r.mode!=='우주 아이템전');
        }
      }else if(!teacher){document.getElementById('questiontext').textContent='선생님이 문제를 출제할 때까지 기다려 주세요.'}
    });
    s.on('joined_game',()=>{});
    s.on('join_error',d=>document.getElementById('notice').textContent=d.message);
    s.on('answer_result',d=>document.getElementById('answerstatus').textContent=d.message);
    s.on('item_notice',d=>document.getElementById('notice').textContent=d.message);
    document.getElementById('useitem').onclick=()=>s.emit('use_item',{code,item:document.getElementById('item').value,target:document.getElementById('target').value,percent:Number(document.getElementById('percent').value),amount:Number(document.getElementById('amount').value)});
    function esc(x){return String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
    </script>"""
    return page("게임방", content, scripts)

@app.get("/health")
def health():
    return {"status": "ok", "app": "QuizRun"}

@socketio.on("create_room")
def create_room(data):
    data = data or {}
    mode = data.get("mode", "일반")
    if mode not in MODES:
        mode = "일반"
    code = new_code()
    room = {
        "code": code, "teacher": request.sid,
        "name": str(data.get("name", "QuizRun"))[:80],
        "grade": str(data.get("grade", "학년 제한 없음"))[:40],
        "subject": str(data.get("subject", "기타"))[:40],
        "mode": mode,
        "play_type": data.get("play_type", "개인전") if mode == "땅따먹기" else "개인전",
        "seconds": max(5, min(120, int(data.get("seconds", 20)))),
        "status": "대기 중", "players": {}, "questions": [],
        "question_index": -1, "current": None
    }
    with lock:
        rooms[code] = room
    join_room(code)
    emit("room_created", {"code": code})

@socketio.on("join_game")
def join_game(data):
    data = data or {}
    code = str(data.get("code", "")).strip()
    name = str(data.get("name", "학생")).strip()[:24] or "학생"
    room = rooms.get(code)
    if not room:
        emit("join_error", {"message": "방 번호가 없어요. 다시 확인해 주세요."})
        return
    if room["status"] == "진행 중":
        emit("join_error", {"message": "게임이 시작되어 새로 참가할 수 없어요."})
        return
    pid = request.sid
    room["players"][pid] = {
        "name": name, "score": 0, "team": None,
        "answered": False, "last_question": -1
    }
    if room["mode"] == "땅따먹기" and room["play_type"] == "팀전":
        room["players"][pid]["team"] = "블루" if len(room["players"]) % 2 else "퍼플"
    join_room(code)
    emit("joined_game", {"code": code})
    broadcast(code)

@socketio.on("get_room")
def get_room(data):
    code = str((data or {}).get("code", ""))
    room = rooms.get(code)
    if not room:
        emit("join_error", {"message": "방을 찾을 수 없어요."})
        return
    join_room(code)
    if is_teacher(room):
        emit("teacher_confirm", {"ok": True})
    emit("room_update", public_room(room))

@socketio.on("add_question")
def add_question(data):
    data = data or {}
    code = str(data.get("code", ""))
    room = rooms.get(code)
    if not room or not is_teacher(room):
        emit("action_error", {"message": "이 방의 교사만 문제를 추가할 수 있어요."})
        return
    qtype = data.get("type")
    if qtype not in TYPES:
        emit("action_error", {"message": "문제 유형을 확인해 주세요."})
        return
    text = str(data.get("text", "")).strip()[:500]
    options = [str(x).strip()[:160] for x in data.get("options", [])[:6]]
    if qtype == "OX":
        options = ["O", "X"]
    if not text or len(options) < 2 or any(not x for x in options):
        emit("action_error", {"message": "문제와 선택지를 입력해 주세요."})
        return
    try:
        correct = int(data.get("correct", 0))
    except (TypeError, ValueError):
        correct = 0
    correct = max(0, min(len(options)-1, correct))
    room["questions"].append({
        "type": qtype, "text": text,
        "options": options, "correct": correct
    })
    emit("question_added", {"message": f"문제 {len(room['questions'])}개째 추가 완료!"})
    broadcast(code)

@socketio.on("start_game")
def start_game(data):
    code = str((data or {}).get("code", ""))
    room = rooms.get(code)
    if not room or not is_teacher(room):
        emit("action_error", {"message": "교사만 게임을 시작할 수 있어요."})
        return
    if not room["questions"]:
        emit("action_error", {"message": "먼저 문제를 하나 이상 추가해 주세요."})
        return
    room["status"] = "진행 중"
    broadcast(code)

@socketio.on("publish_question")
def publish_question(data):
    code = str((data or {}).get("code", ""))
    room = rooms.get(code)
    if not room or not is_teacher(room):
        emit("action_error", {"message": "교사만 문제를 출제할 수 있어요."})
        return
    if not room["questions"]:
        emit("action_error", {"message": "먼저 문제를 추가해 주세요."})
        return
    room["question_index"] = (room["question_index"] + 1) % len(room["questions"])
    q = room["questions"][room["question_index"]]
    room["current"] = {
        "type": q["type"], "text": q["text"],
        "options": q["options"], "correct": q["correct"],
        "started_at": time.time(), "seconds": room["seconds"]
    }
    for p in room["players"].values():
        p["answered"] = False
        p["last_question"] = -1
    broadcast(code)

@socketio.on("answer")
def answer(data):
    data = data or {}
    code = str(data.get("code", ""))
    room = rooms.get(code)
    if not room or not room["current"]:
        emit("answer_result", {"message": "현재 출제된 문제가 없어요."})
        return
    player = room["players"].get(request.sid)
    if not player:
        emit("answer_result", {"message": "먼저 방에 입장해 주세요."})
        return
    q = room["current"]
    if player["answered"]:
        emit("answer_result", {"message": "이미 답을 제출했어요."})
        return
    player["answered"] = True
    player["last_question"] = room["question_index"]
    try:
        choice = int(data.get("choice", -1))
    except (ValueError, TypeError):
        choice = -1
    correct = choice == q["correct"]
    elapsed = time.time() - q["started_at"]
    remaining = max(0, q["seconds"] - elapsed)
    points = min(20000, 1000 + int(19000 * remaining / q["seconds"])) if correct else 0
    player["score"] += points
    emit("answer_result", {
        "correct": correct, "points": points,
        "message": f"정답! {points:,}P 획득!" if correct else "오답이에요. 다음 문제에 도전해 봐요!"
    })
    broadcast(code)

@socketio.on("use_item")
def use_item(data):
    data = data or {}
    code = str(data.get("code", ""))
    room = rooms.get(code)
    if not room or room["mode"] != "우주 아이템전":
        emit("action_error", {"message": "우주 아이템전에서만 사용할 수 있어요."})
        return
    players = room["players"]
    me = players.get(request.sid)
    if not me:
        emit("action_error", {"message": "게임 참가자만 사용할 수 있어요."})
        return
    item = data.get("item")
    target = players.get(str(data.get("target", "")))
    try:
        pct = int(data.get("percent", 5))
        amount = int(data.get("amount", 50))
    except (ValueError, TypeError):
        pct, amount = 5, 50
    if pct not in [5, 15, 25, 50]:
        pct = 5
    if amount not in [50, 100, 500, 1000]:
        amount = 50

    def subtract(p, value):
        p["score"] = max(0, p["score"] - value)

    if item in ("흡수", "보급품"):
        if target and target is not me:
            value = int(target["score"] * pct / 100)
            subtract(target, value)
            me["score"] += value
    elif item == "우주 쓰레기":
        subtract(me, int(me["score"] * pct / 100))
    elif item == "총":
        if target and target is not me:
            subtract(target, int(target["score"] * pct / 100))
    elif item == "공기":
        me["score"] = int(me["score"] * (1 + pct / 100))
    elif item == "물":
        me["score"] += amount
    elif item == "초거대 블랙홀":
        for p in players.values():
            p["score"] = 0
    elif item == "소형 블랙홀":
        subtract(me, 200)
    elif item == "중형 블랙홀":
        me["score"] = 0
    else:
        emit("action_error", {"message": "아이템을 확인해 주세요."})
        return
    socketio.emit("item_notice", {"message": f"{me['name']} 님이 {item} 사용!"}, to=code)
    broadcast(code)

@socketio.on("disconnect")
def disconnect():
    sid = request.sid
    for code, room in list(rooms.items()):
        if sid in room["players"]:
            del room["players"][sid]
            broadcast(code)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
