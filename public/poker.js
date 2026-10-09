const $=id=>document.getElementById(id);let ws,st;const CARD=(c)=>{if(!c)return '<div class="pk-card back"></div>';let [r,s]=c;const symbol={S:'♠',H:'♥',D:'♦',C:'♣'}[s];return '<div class="pk-card '+('HD'.includes(s)?'red':'')+'">'+({11:'J',12:'Q',13:'K',14:'A'}[r]||r)+symbol+'</div>'};
async function connect(){if(ws&&ws.readyState===1)return;return new Promise((ok,fail)=>{ws=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/poker/ws');ws.onopen=ok;ws.onerror=fail;ws.onmessage=e=>{let x=JSON.parse(e.data);if(x.type==='error')alert(x.message);else if(x.type==='session'){sessionStorage.setItem('pokerSession',JSON.stringify(x));history.replaceState(null,'','?room='+x.code)}else if(x.type==='state'){st=x;render()}}})}
async function send(data){await connect();ws.send(JSON.stringify(data))}
$('pkcreate').onclick=()=>send({type:'create',name:$('pkname').value});$('pkjoin').onclick=()=>send({type:'join',name:$('pkname').value,code:$('pkcode').value.trim()});
$('pkadd').onclick=()=>send({type:'add_ai'});$('pkremove').onclick=()=>send({type:'remove_ai'});$('pkstart').onclick=()=>send({type:'start'});$('pknext').onclick=()=>send({type:'next'});
for(const action of ['fold','check','call','raise'])$('pk'+action).onclick=()=>send({type:action,amount:parseInt($('pkamount').value,10)});
function render(){const s=st;let lobby=s.phase==='lobby',mine=s.players[s.seat];$('pkhome').classList.add('hidden');$('pkroom').classList.remove('hidden');
$('pkstatus').textContent='ROOM '+s.code+' · 딜러 '+(s.dealer>=0?s.players[s.dealer].name:'미정')+' · 블라인드 10/20';
$('pkplayers').innerHTML=s.players.map((p,i)=>'<div class="pk-player '+(i===s.turn?'turn ':'')+(p.fold?'fold':'')+'">'+(p.ai?'🤖 ':'👤 ')+esc(p.name)+(i===s.seat?' (나)':'')+'<p>🪙 '+p.chips+' · 베팅 '+p.bet+'</p>'+((p.cards||[]).map(CARD).join('')||'<small>'+(p.count?'🂠 '+p.count+'장':'')+'</small>')+'</div>').join('');
$('pklobby').classList.toggle('hidden',!lobby);$('pkadd').classList.toggle('hidden',!s.host);$('pkremove').classList.toggle('hidden',!s.host);$('pkstart').classList.toggle('hidden',!s.host);
$('pkstreet').textContent=s.street||'대기실';$('pkpot').textContent='💰 POT '+s.pot;$('pkcommunity').innerHTML=s.board.map(CARD).join('')+Array.from({length:Math.max(0,5-s.board.length)},()=>CARD(null)).join('');
$('pkhand').innerHTML=s.hand.map(CARD).join('');
const myturn=s.phase==='betting'&&s.turn===s.seat;let due=s.current-mine.bet;
$('pkturn').textContent=s.phase==='betting'?(myturn?'내 차례 · 콜 '+due+' · 최소 레이즈 '+(s.current+s.minraise):s.players[s.turn]?.name+'의 차례'):'';
$('pkcontrols').classList.toggle('hidden',!myturn);$('pkcheck').disabled=due>0;$('pkcall').textContent='콜 '+due;
$('pknext').classList.toggle('hidden',s.phase!=='showdown'||!s.host);
$('pkwin').textContent=(s.winner||[]).map(x=>x.name+' +'+x.amount+'칩').join(' · ');$('pklog').innerHTML=s.log.slice().reverse().map(x=>'<p>'+esc(x)+'</p>').join('');
}
function esc(x){return String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
const room=new URLSearchParams(location.search).get('room');if(room)$('pkcode').value=room;
try{const sess=JSON.parse(sessionStorage.getItem('pokerSession'));if(sess)send({type:'reconnect',code:sess.code,token:sess.token})}catch{}
