const $=id=>document.getElementById(id),img=id=>'/cards/'+String(id).padStart(2,'0')+'.png';let ws,state,session;
function connect(){return new Promise((resolve,reject)=>{if(ws&&ws.readyState===1)return resolve();ws=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/rogue/ws');ws.onopen=resolve;ws.onerror=reject;ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.type==='session'){session=d;sessionStorage.setItem('rogueSession',JSON.stringify(d));history.replaceState(null,'','?room='+d.code)}else if(d.type==='error')alert(d.message);else if(d.type==='state'){state=d;render()}}})}
async function send(d){await connect();ws.send(JSON.stringify(d))}
$('rcreate').onclick=()=>send({type:'create',name:$('rname').value});
$('rjoin').onclick=()=>send({type:'join',name:$('rname').value,code:$('rcode').value.trim().toUpperCase()});
$('radd').onclick=()=>send({type:'add_ai'});$('rremove').onclick=()=>send({type:'remove_ai'});
$('rstart').onclick=()=>send({type:'start'});
function render(){const s=state,m=s.players[s.seat],lobby=s.phase==='lobby';$('startscreen').classList.add('hidden');$('rroom').classList.remove('hidden');
$('rstage').textContent='STAGE '+s.stage+' / 15 · 방 코드 '+s.code;$('rphase').textContent={lobby:'팀원을 모으거나 AI를 추가하세요',battle:'적 카드에서 한 장을 뽑아 내 패와 숫자가 같으면 공격!',reward:'클리어! 증강 또는 유물 선택',won:'15스테이지 생존 성공',lost:'파티 전멸'}[s.phase]||s.phase;
$('rplayers').innerHTML=s.players.map((p,i)=>'<p>'+(p.ai?'🤖 ':'👤 ')+escapeHTML(p.name)+' · HP '+Math.max(0,p.hp)+'/'+p.maxhp+(i===s.turn?' 🎯 차례':'')+' · 증강 '+p.aug.length+' · 유물 '+p.relic.length+'</p>').join('');
for(const id of ['radd','rremove','rstart'])$(id).classList.toggle('hidden',!lobby||!s.host);
$('rdeck').innerHTML=s.phase==='battle'?Array.from({length:Math.min(s.enemyCount,18)},(_,i)=>'<img data-i="'+i+'" src="'+img(41)+'">').join(''):'';
$('rdeck').querySelectorAll('img').forEach(el=>el.onclick=()=>{if(s.turn===s.seat)send({type:'attack',index:Number(el.dataset.i)})});
$('rhand').innerHTML=s.hand.map(i=>'<img src="'+img(i)+'">').join('');
$('rturn').textContent=s.phase==='battle'?(s.turn===s.seat?'내 차례! 카드를 뽑으세요':s.players[s.turn]?.name+'의 차례'):'';
$('renemy').textContent=s.enemy?.name||'탐험 대기';$('renemyhp').style.width=s.enemy?Math.max(0,100*s.enemy.hp/s.enemy.maxhp)+'%':'0%';$('renemystats').textContent=s.enemy?'HP '+Math.max(0,s.enemy.hp)+'/'+s.enemy.maxhp+' · 공격력 '+s.enemy.attack+(s.enemy.boss?' · 👑 BOSS':''):'';
$('roguelog').innerHTML=s.log.slice().reverse().map(x=>'<div>'+escapeHTML(x)+'</div>').join('');
$('rewardbox').classList.toggle('hidden',s.phase!=='reward');let source=s.stage%5===0?s.relics:s.augs;
$('rewards').innerHTML=s.phase==='reward'?s.offer.map(key=>{const a=source.find(x=>x[0]===key);if(!a)return '';return '<button class="reward" data-key="'+key+'" '+(m.ready?'disabled':'')+'><div> '+(a[2]&&s.stage%5?'【'+a[2]+'】':'유물')+'</div><b>'+escapeHTML(a[1])+'</b><small>'+escapeHTML(a[3]||a[2])+'</small></button>'}).join(''):'';
$('rewards').querySelectorAll('button').forEach(el=>el.onclick=()=>send({type:'choose',id:el.dataset.key}));
$('rfinish').classList.toggle('hidden',!['won','lost'].includes(s.phase));$('rfinish').innerHTML=s.phase==='won'?'🏆 15스테이지 클리어!':s.phase==='lost'?'💀 파티 전멸 — 새 방에서 다시 도전하세요':'';
}
function escapeHTML(x){return String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
const urlRoom=new URLSearchParams(location.search).get('room');if(urlRoom)$('rcode').value=urlRoom;
try{const stored=JSON.parse(sessionStorage.getItem('rogueSession'));if(stored){session=stored;send({type:'reconnect',code:stored.code,token:stored.token})}}catch{}
