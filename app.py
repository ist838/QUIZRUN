import os
import time
import random
import string
import secrets
from threading import RLock

from flask import Flask, request, render_template_string, session
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "change-this-before-deploying"
)
socketio = SocketIO(
    app, cors_allowed_origins="*", async_mode="threading"
)

rooms = {}
lock = RLock()

MODES = ["우주선", "우주 아이템전", "땅따먹기", "사막 위 자동차", "일반"]
TYPES = ["OX", "객관식", "번호 선택형"]
ITEMS = [
    "흡수", "우주 쓰레기", "총", "공기", "물",
    "초거대 블랙홀", "소형 블랙홀", "중형 블랙홀", "보급품"
]

STYLE = """
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Noto+Sans+KR:wght@400;600;800&display=swap');
:root{--bg:#080914;--panel:#121428;--line:#303253;--purple:#a855f7;--blue:#38bdf8}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(ellipse at 10% 0%,#29104b,transparent 40%),radial-gradient(ellipse at 95% 25%,#092849,transparent 35%),var(--bg);color:#f5f5ff;font-family:'Noto Sans KR',sans-serif}
nav{display:flex;justify-content:space-between;align-items:center;padding:20px max(18px,calc((100% - 950px)/2));border-bottom:1px solid #ffffff18}
nav a{color:#c4b5fd;text-decoration:none;margin-left:15px}
.brand{font:800 22px Orbitron;color:white}
main{max-width:950px;margin:35px auto;padding:0 18px}
.hero{text-align:center;padding:40px 0}
h1{font-size:clamp(30px,6vw,52px);line-height:1.25}
h1 span{background:linear-gradient(90deg,#c084fc,#38bdf8);color:transparent;background-clip:text}
h2{margin-top:28px}p,.muted{color:#a7a8c9;line-height:1.7}
.panel,.tile{background:linear-gradient(145deg,#15172e,#0c0d1c);border:1px solid var(--line);border-radius:18px;padding:22px;margin:15px 0}
.btn,button{display:inline-block;border:1px solid #41436b;border-radius:11px;padding:12px 17px;background:#1a1c36;color:white;text-decoration:none;font:600 14px inherit;cursor:pointer}
button:disabled{opacity:.45;cursor:not-allowed}
.primary{background:linear-gradient(100deg,#7c3aed,#2563eb);border:0}
.full{width:100%;margin-top:12px}
input,select,textarea{display:block;width:100%;margin-top:7px;padding:12px;background:#090a18;border:1px solid #343657;border-radius:9px;color:white;font:inherit}
label{display:block;margin:13px 0;font-size:13px;color:#dadaf3}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.modes{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:30px}
.tile{text-align:center;padding:18px 8px;margin:0}
.tile .ship{font-size:42px}
small{color:#a7a8c9}.hidden{display:none!important}
.code{font:800 40px Orbitron;color:#67e8f9;letter-spacing:7px;text-align:center;margin:20px}
.answers{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.answers button{text-align:left;min-height:55px;white-space:normal}
.notice{color:#c4b5fd;min-height:20px}
li{padding:10px;border-bottom:1px solid #ffffff14}
.question-editor{border:1px solid #38395e;border-radius:12px;padding:16px;margin:12px 0}
.ship-stage{position:relative;overflow:hidden;text-align:center;padding:22px;border-radius:15px;background:radial-gradient(circle at 50% 30%,#243a72,#101126 65%);border:1px solid #303253;margin:15px 0}
.bigship{font-size:62px;filter:drop-shadow(0 0 16px #60a5fa);animation:float 2s ease-in-out infinite}
.stars{font-size:18px;letter-spacing:12px;color:#c4b5fd}
@keyframes float{0%,100%{transform:translateY(0) rotate(-3deg)}50%{transform:translateY(-9px) rotate(3deg)}}
.timer{font:800 30px Orbitron;color:#67e8f9}
.progress{height:10px;background:#242642;border-radius:20px;overflow:hidden}
#progressbar{height:100%;width:100%;background:linear-gradient(90deg,#a855f7,#38bdf8);transition:width .4s}
.rank{display:flex;gap:10px;align-items:center}
.rank .medal{font-size:25px}
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
    return render_template_string(
        BASE, title=title, content=content, scripts=scripts
    )


def new_code():
    while True:
        code = "".join(random.choices(string.digits, k=6))
        if code not in rooms:
            return code


def public_room(room):
    """정답과 비공개 토큰은 공개 데이터에서 제외한다."""
    now = time.time()
    remaining = max(0, room["ends_at"] - now) if room["ends_at"] else None
    players = []
    for pid, p in room["players"].items():
        players.append({
            "id": pid,
            "name": p["name"],
            "score": p["score"],
            "team": p["team"],
            "finished": p["finished"],
            "ship": p["ship"],
            "answered_count": len(p["answers"]),
        })

    # 학생에게는 문제 본문과 선택지만 전송한다.
    safe_questions = [
        {"type": q["type"], "text": q["text"], "options": q["options"]}
        for q in room["questions"]
    ]

    return {
        "code": room["code"],
        "name": room["name"],
        "grade": room["grade"],
        "subject": room["subject"],
        "mode": room["mode"],
        "play_type": room["play_type"],
        "duration": room["duration"],
        "status": room["status"],
        "questions": safe_questions,
        "players": players,
        "remaining": remaining,
        "ends_at": room["ends_at"],
        "question_count": len(room["questions"]),
    }


def broadcast(code):
    room = rooms.get(code)
    if room:
        socketio.emit("room_update", public_room(room), to=code)


def is_teacher(room, data=None):
    data = data or {}
    return secrets.compare_digest(
        str(data.get("teacher_token", "")),
        str(room["teacher_token"])
    )


def finish_if_due(room):
    if room["status"] == "진행 중" and room["ends_at"]:
        if time.time() >= room["ends_at"]:
            room["status"] = "종료"
            room["ends_at"] = None
            return True
    return room["status"] == "종료"


def timer_loop(code):
    while True:
        socketio.sleep(1)
        with lock:
            room = rooms.get(code)
            if not room or room["status"] != "진행 중":
                break
            ended = finish_if_due(room)
        broadcast(code)
        if ended:
            socketio.emit("game_finished", {"message": "시간 종료! 최종 순위를 확인하세요."}, to=code)
            broadcast(code)
            break


@app.get("/")
def home():
    content = """
    <section class="hero">
      <p>✦ THE UNIVERSE OF QUIZZES</p>
      <h1>정답을 맞히고,<br><span>우주를 정복해!</span></h1>
      <p>실시간 퀴즈 · 우주 아이템전 · 랜덤 문제 순서</p>
      <p><a class="btn primary" href="/teach">＋ 교사: 방 만들기</a>
      <a class="btn" href="/play">학생: 참가하기 ↗</a></p>
      <div class="modes">
        <div class="tile"><div class="ship">🚀</div><p>우주선</p></div>
        <div class="tile"><div class="ship">🌌</div><p>우주 아이템전</p></div>
        <div class="tile"><div class="ship">🗺️</div><p>땅따먹기</p></div>
        <div class="tile"><div class="ship">🏎️</div><p>사막 자동차</p></div>
        <div class="tile"><div class="ship">🎯</div><p>일반 퀴즈</p></div>
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
      <label>전체 게임 시간<select id="duration">
        <option value="60">1분</option><option value="180">3분</option>
        <option value="300" selected>5분</option><option value="600">10분</option>
        <option value="900">15분</option>
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
    </section>"""
    scripts = """
    <script>
    const s=io(), mode=document.getElementById('mode');
    let teacherToken='';
    mode.onchange=()=>document.getElementById('teamwrap').classList.toggle('hidden',mode.value!=='땅따먹기');
    document.getElementById('create').onclick=()=>{
      document.getElementById('status').textContent='방을 만들고 있어요...';
      s.emit('create_room',{
        name:document.getElementById('name').value,
        grade:document.getElementById('grade').value,
        subject:document.getElementById('subject').value,
        mode:mode.value,play_type:document.getElementById('play_type').value,
        duration:Number(document.getElementById('duration').value)});
    };
    s.on('room_created',d=>{
      teacherToken=d.teacher_token;
      sessionStorage.setItem('teacher_'+d.code,teacherToken);
      const url=location.origin+'/play?code='+d.code;
      document.getElementById('created').classList.remove('hidden');
      document.getElementById('code').textContent=d.code;
      document.getElementById('link').textContent=url;
      document.getElementById('open').href='/room/'+d.code+'?teacher='+encodeURIComponent(teacherToken);
      document.getElementById('qr').innerHTML='';
      new QRCode(document.getElementById('qr'),{text:url,width:180,height:180});
      document.getElementById('status').textContent='방이 만들어졌어요!';
    });
    document.getElementById('copy').onclick=async()=>{
      try{
        await navigator.clipboard.writeText(document.getElementById('link').textContent);
        document.getElementById('copy').textContent='복사 완료!';
      }catch(e){document.getElementById('status').textContent='링크를 길게 눌러 복사해 주세요.'}
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
      if(!/^\\d{6}$/.test(code)||!name){
        document.getElementById('status').textContent='방 번호 6자리와 닉네임을 입력해 주세요.';return
      }
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
      <p>LIVE ARENA · ROOM <b id="code"></b></p>
      <h1 id="roomname">QuizRun</h1>
      <p>게임: <b id="mode"></b> · <span id="grade"></span> · <span id="subject"></span></p>
      <p>상태: <b id="state">연결 중</b> · 참가자: <b id="count">0</b>명</p>
      <div class="ship-stage">
        <div class="stars">✦ · ✧ · ✦ · ✧</div>
        <div class="bigship" id="ship">🚀</div>
        <p id="shipmsg">우주 탐험을 준비하세요!</p>
      </div>
      <div id="timerbox" class="hidden">
        <p>남은 시간</p><div class="timer" id="timer">05:00</div>
        <div class="progress"><div id="progressbar"></div></div>
      </div>
      <div id="teacher" class="hidden">
        <h2>교사용 컨트롤</h2>
        <button class="btn primary" id="start">전체 퀴즈 시작</button>
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
      </div>
      <div id="student" class="hidden">
        <h2 id="progressText">선생님을 기다려 주세요.</h2>
        <div id="quizarea" class="hidden">
          <p id="questionnumber"></p>
          <h2 id="questiontext"></h2>
          <div id="answers" class="answers"></div>
          <p id="answerstatus" class="notice"></p>
        </div>
        <div id="finished" class="panel hidden">
          <h2>🎉 모든 문제를 풀었어요!</h2>
          <p>다른 친구들이 끝날 때까지 잠시 기다려 주세요. 최종 순위는 게임이 끝난 후 공개됩니다.</p>
          <div style="font-size:80px;text-align:center">🚀</div>
        </div>
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
      <h2>🏆 순위</h2><ol id="board"></ol><p id="notice" class="notice"></p>
    </section>"""

    scripts = """
    <script>
    const s=io(),code=location.pathname.split('/').pop();
    const params=new URLSearchParams(location.search);
    let teacherToken=params.get('teacher')||sessionStorage.getItem('teacher_'+code)||'';
    let teacher=!!teacherToken, room=null, opts=['O','X'], currentQuestion=null;
    let order=[], index=0, answeredSet=new Set(), deadline=null, timerHandle=null;
    document.getElementById('code').textContent=code;
    document.getElementById(teacher?'teacher':'student').classList.remove('hidden');

    function teacherPayload(extra={}) {
      return Object.assign({code,teacher_token:teacherToken},extra);
    }

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
        inp.oninput=()=>{opts[i]=inp.value;sel.options[i].text=(i+1)+'. '+opts[i]};
        l.appendChild(inp);area.appendChild(l);
        let o=document.createElement('option');o.value=i;o.textContent=(i+1)+'. '+v;sel.appendChild(o);
      });
    }
    if(teacher){
      optionUI();
      document.getElementById('type').onchange=()=>optionUI();
      document.getElementById('addoption').onclick=()=>{
        if(document.getElementById('type').value==='OX')return;
        if(opts.length>=6){document.getElementById('teachstatus').textContent='선택지는 최대 6개예요.';return}
        opts.push('선택지 '+(opts.length+1));renderOpts();
      };
      document.getElementById('addquestion').onclick=()=>{
        s.emit('add_question',teacherPayload({
          type:document.getElementById('type').value,
          text:document.getElementById('question').value,
          options:opts,correct:Number(document.getElementById('correct').value)
        }));
      };
      document.getElementById('start').onclick=()=>{
        if(!confirm('게임을 시작할까요? 시작 후에는 문제를 추가할 수 없어요.'))return;
        s.emit('start_game',teacherPayload());
      };
    }

    s.emit('get_room',{code,teacher_token:teacherToken});

    s.on('teacher_confirm',d=>{
      if(d.ok){
        teacher=true;
        sessionStorage.setItem('teacher_'+code,teacherToken);
        document.getElementById('teacher').classList.remove('hidden');
        document.getElementById('student').classList.add('hidden');
      }
    });
    s.on('question_added',d=>{
      document.getElementById('teachstatus').textContent=d.message;
      document.getElementById('question').value='';
    });
    s.on('action_error',d=>document.getElementById('notice').textContent=d.message);
    s.on('room_update',r=>{
      room=r;
      document.getElementById('roomname').textContent=r.name;
      document.getElementById('mode').textContent=r.mode;
      document.getElementById('grade').textContent=r.grade;
      document.getElementById('subject').textContent=r.subject;
      document.getElementById('state').textContent=r.status;
      document.getElementById('count').textContent=r.players.length;

      const board=document.getElementById('board');
      board.innerHTML='';
      [...r.players].sort((a,b)=>b.score-a.score).forEach((p,i)=>{
        let li=document.createElement('li');
        const medals=['🥇','🥈','🥉'];
        li.className='rank';
        li.innerHTML='<span class="medal">'+(medals[i]||'🚀')+'</span>';
        const span=document.createElement('span');
        span.textContent=(i+1)+'. '+p.name+' — '+p.score.toLocaleString()+'P'+(p.finished?' · 완료':'');
        li.appendChild(span);board.appendChild(li);
      });

      document.getElementById('target').innerHTML=r.players
        .filter(p=>p.id!==s.id)
        .map(p=>'<option value="'+p.id+'">'+esc(p.name)+'</option>').join('');

      if(teacher){
        document.getElementById('questionlist').innerHTML='';
        r.questions.forEach((q,i)=>{
          let li=document.createElement('li');
          li.textContent=(i+1)+'. ['+q.type+'] '+q.text;
          document.getElementById('questionlist').appendChild(li);
        });
      }

      if(r.status==='진행 중'){
        document.getElementById('timerbox').classList.remove('hidden');
        startTimer(r.ends_at, r.duration);
        if(!teacher) prepareStudentQuiz(r);
      } else if(r.status==='종료'){
        stopTimer();
        document.getElementById('timerbox').classList.remove('hidden');
        document.getElementById('timer').textContent='00:00';
        if(!teacher){
          document.getElementById('quizarea').classList.add('hidden');
          document.getElementById('finished').classList.remove('hidden');
          document.getElementById('finished').innerHTML='<h2>🏆 게임 종료!</h2><p>최종 순위를 확인해 주세요.</p><div style="font-size:70px;text-align:center">🚀</div>';
        }
      } else {
        document.getElementById('timerbox').classList.add('hidden');
      }
    });

    function prepareStudentQuiz(r){
      if(!order.length && r.question_count>0){
        order=Array.from({length:r.question_count},(_,i)=>i);
        for(let i=order.length-1;i>0;i--){
          const j=Math.floor(Math.random()*(i+1));
          [order[i],order[j]]=[order[j],order[i]];
        }
        index=0;
        showQuestion();
      }
    }

    function showQuestion(){
      if(!room || teacher)return;
      if(index>=order.length){
        document.getElementById('quizarea').classList.add('hidden');
        document.getElementById('finished').classList.remove('hidden');
        document.getElementById('progressText').textContent='모든 문제 완료!';
        s.emit('finish_player',{code});
        return;
      }
      currentQuestion=order[index];
      document.getElementById('quizarea').classList.remove('hidden');
      document.getElementById('finished').classList.add('hidden');
      document.getElementById('progressText').textContent='문제를 풀고 있어요!';
      document.getElementById('questionnumber').textContent=
        '문제 '+(index+1)+' / '+order.length;
      const q=room.questions[currentQuestion];
      document.getElementById('questiontext').textContent=q.text+' ('+q.type+')';
      document.getElementById('answerstatus').textContent='';
      const area=document.getElementById('answers');area.innerHTML='';
      q.options.forEach((o,i)=>{
        const b=document.createElement('button');
        b.textContent=(q.type==='OX'?'':(i+1)+'. ')+o;
        b.onclick=()=>{
          if(answeredSet.has(currentQuestion)||room.status!=='진행 중')return;
          answeredSet.add(currentQuestion);
          area.querySelectorAll('button').forEach(x=>x.disabled=true);
          s.emit('answer',{code,question_index:currentQuestion,choice:i});
        };
        area.appendChild(b);
      });
      document.getElementById('items').classList.toggle('hidden',room.mode!=='우주 아이템전');
    }

    s.on('answer_result',d=>{
      document.getElementById('answerstatus').textContent=d.message;
      if(d.accepted){
        index++;
        setTimeout(showQuestion,350);
      } else if(d.expired){
        document.getElementById('quizarea').classList.add('hidden');
      }
    });
    s.on('player_finished',()=>{
      document.getElementById('quizarea').classList.add('hidden');
      document.getElementById('finished').classList.remove('hidden');
    });
    s.on('game_finished',()=>{
      document.getElementById('quizarea').classList.add('hidden');
      document.getElementById('finished').classList.remove('hidden');
    });
    s.on('join_error',d=>document.getElementById('notice').textContent=d.message);
    s.on('item_notice',d=>document.getElementById('notice').textContent=d.message);

    function startTimer(endsAt,duration){
      deadline=endsAt;
      if(timerHandle)return;
      timerHandle=setInterval(()=>{
        if(!deadline)return;
        const seconds=Math.max(0,Math.ceil(deadline-Date.now()/1000));
        const m=String(Math.floor(seconds/60)).padStart(2,'0');
        const sec=String(seconds%60).padStart(2,'0');
        document.getElementById('timer').textContent=m+':'+sec;
        document.getElementById('progressbar').style.width=
          Math.max(0,Math.min(100,seconds/duration*100))+'%';
        if(seconds<=0)stopTimer();
      },250);
    }
    function stopTimer(){if(timerHandle){clearInterval(timerHandle);timerHandle=null}}
    document.getElementById('useitem').onclick=()=>{
      s.emit('use_item',{code,item:document.getElementById('item').value,
        target:document.getElementById('target').value,
        percent:Number(document.getElementById('percent').value),
        amount:Number(document.getElementById('amount').value)});
    };
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

    try:
        duration = int(data.get("duration", 300))
    except (TypeError, ValueError):
        duration = 300
    duration = max(60, min(900, duration))

    code = new_code()
    token = secrets.token_urlsafe(32)
    room = {
        "code": code,
        "teacher_token": token,
        "name": str(data.get("name", "QuizRun"))[:80],
        "grade": str(data.get("grade", "학년 제한 없음"))[:40],
        "subject": str(data.get("subject", "기타"))[:40],
        "mode": mode,
        "play_type": data.get("play_type", "개인전") if mode == "땅따먹기" else "개인전",
        "duration": duration,
        "status": "대기 중",
        "players": {},
        "questions": [],
        "ends_at": None,
        "started_at": None,
    }
    with lock:
        rooms[code] = room
    join_room(code)
    emit("room_created", {"code": code, "teacher_token": token})


@socketio.on("join_game")
def join_game(data):
    data = data or {}
    code = str(data.get("code", "")).strip()
    name = str(data.get("name", "학생")).strip()[:24] or "학생"
    room = rooms.get(code)
    if not room:
        emit("join_error", {"message": "방 번호가 없어요. 다시 확인해 주세요."})
        return
    if room["status"] != "대기 중":
        emit("join_error", {"message": "이미 시작했거나 종료된 게임이에요."})
        return

    pid = request.sid
    room["players"][pid] = {
        "name": name, "score": 0, "team": None,
        "finished": False, "answers": {}, "ship": random.choice(["🚀", "🛸", "🚀", "🛰️"])
    }
    if room["mode"] == "땅따먹기" and room["play_type"] == "팀전":
        room["players"][pid]["team"] = "블루" if len(room["players"]) % 2 else "퍼플"
    join_room(code)
    emit("joined_game", {"code": code})
    broadcast(code)


@socketio.on("get_room")
def get_room(data):
    data = data or {}
    code = str(data.get("code", ""))
    room = rooms.get(code)
    if not room:
        emit("join_error", {"message": "방을 찾을 수 없어요."})
        return
    join_room(code)
    if is_teacher(room, data):
        emit("teacher_confirm", {"ok": True})
    emit("room_update", public_room(room))


@socketio.on("add_question")
def add_question(data):
    data = data or {}
    code = str(data.get("code", ""))
    room = rooms.get(code)
    if not room or not is_teacher(room, data):
        emit("action_error", {"message": "교사 권한을 확인할 수 없어요. 교사 페이지에서 다시 열어 주세요."})
        return
    if room["status"] != "대기 중":
        emit("action_error", {"message": "게임 시작 후에는 문제를 추가할 수 없어요."})
        return

    qtype = data.get("type")
    if qtype not in TYPES:
        emit("action_error", {"message": "문제 유형을 확인해 주세요."})
        return
    text = str(data.get("text", "")).strip()[:500]
    raw_options = data.get("options", [])
    if not isinstance(raw_options, list):
        raw_options = []
    options = [str(x).strip()[:160] for x in raw_options[:6]]
    if qtype == "OX":
        options = ["O", "X"]
    if not text or len(options) < 2 or any(not x for x in options):
        emit("action_error", {"message": "문제와 선택지를 입력해 주세요."})
        return

    try:
        correct = int(data.get("correct", 0))
    except (TypeError, ValueError):
        correct = 0
    if not 0 <= correct < len(options):
        emit("action_error", {"message": "정답 선택지를 확인해 주세요."})
        return

    room["questions"].append({
        "type": qtype, "text": text,
        "options": options, "correct": correct
    })
    emit("question_added", {"message": f"문제 {len(room['questions'])}개째 추가 완료!"})
    broadcast(code)


@socketio.on("start_game")
def start_game(data):
    data = data or {}
    code = str(data.get("code", ""))
    room = rooms.get(code)
    if not room or not is_teacher(room, data):
        emit("action_error", {"message": "교사 권한을 확인할 수 없어요."})
        return
    if room["status"] != "대기 중":
        emit("action_error", {"message": "게임이 이미 시작되었어요."})
        return
    if not room["questions"]:
        emit("action_error", {"message": "먼저 문제를 하나 이상 추가해 주세요."})
        return
    if not room["players"]:
        emit("action_error", {"message": "학생이 한 명 이상 참가해야 해요."})
        return

    with lock:
        room["status"] = "진행 중"
        room["started_at"] = time.time()
        room["ends_at"] = room["started_at"] + room["duration"]
        for p in room["players"].values():
            p["score"] = 0
            p["answers"] = {}
            p["finished"] = False

    broadcast(code)
    socketio.start_background_task(timer_loop, code)


@socketio.on("answer")
def answer(data):
    data = data or {}
    code = str(data.get("code", ""))
    room = rooms.get(code)
    if not room:
        emit("answer_result", {"message": "방을 찾을 수 없어요."})
        return
    player = room["players"].get(request.sid)
    if not player:
        emit("answer_result", {"message": "먼저 게임에 참가해 주세요."})
        return

    with lock:
        if finish_if_due(room):
            emit("answer_result", {"message": "시간이 끝났어요.", "expired": True})
            broadcast(code)
            return
        if room["status"] != "진행 중":
            emit("answer_result", {"message": "현재 게임이 진행 중이 아니에요."})
            return

        try:
            qi = int(data.get("question_index", -1))
            choice = int(data.get("choice", -1))
        except (TypeError, ValueError):
            emit("answer_result", {"message": "답을 확인해 주세요."})
            return

        if qi < 0 or qi >= len(room["questions"]):
            emit("answer_result", {"message": "문제를 확인할 수 없어요."})
            return
        if qi in player["answers"]:
            emit("answer_result", {"message": "이 문제는 이미 답을 제출했어요."})
            return

        q = room["questions"][qi]
        if choice < 0 or choice >= len(q["options"]):
            emit("answer_result", {"message": "선택지를 확인해 주세요."})
            return

        correct = choice == q["correct"]
        elapsed = time.time() - room["started_at"]
        remaining = max(0, room["duration"] - elapsed)
        points = min(20000, 1000 + int(19000 * remaining / room["duration"])) if correct else 0
        player["answers"][qi] = {"correct": correct, "points": points}
        player["score"] += points

        if len(player["answers"]) >= len(room["questions"]):
            player["finished"] = True

    emit("answer_result", {
        "accepted": True,
        "correct": correct,
        "points": points,
        "message": f"정답! {points:,}P 획득!" if correct else "오답이에요. 다음 문제로 이동해요!"
    })
    if player["finished"]:
        socketio.emit("player_finished", {}, to=request.sid)
    broadcast(code)


@socketio.on("finish_player")
def finish_player(data):
    code = str((data or {}).get("code", ""))
    room = rooms.get(code)
    if not room:
        return
    player = room["players"].get(request.sid)
    if player and room["status"] == "진행 중":
        if len(player["answers"]) >= len(room["questions"]):
            player["finished"] = True
            emit("player_finished", {})
            broadcast(code)


@socketio.on("use_item")
def use_item(data):
    data = data or {}
    code = str(data.get("code", ""))
    room = rooms.get(code)
    if not room or room["mode"] != "우주 아이템전":
        emit("action_error", {"message": "우주 아이템전에서만 사용할 수 있어요."})
        return
    if room["status"] != "진행 중":
        emit("action_error", {"message": "게임 진행 중에만 사용할 수 있어요."})
        return

    players = room["players"]
    me = players.get(request.sid)
    if not me:
        emit("action_error", {"message": "게임 참가자만 사용할 수 있어요."})
        return

    item = data.get("item")
    if item not in ITEMS:
        emit("action_error", {"message": "아이템을 확인해 주세요."})
        return
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

    with lock:
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
    socketio.run(
        app, host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
                 )
