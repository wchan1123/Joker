const $=id=>document.getElementById(id), card=c=>`cards/${String(c).padStart(2,'0')}.png`;
let ws=null,state=null,session=null,muted=false,ctx=null,seen=-1,animating=false,activeCode='';
let selectedPair=[],spectateSeat=null;const screens=['home','lobby','game','end'];
function show(which){screens.forEach(id=>$(id).classList.toggle('hidden',id!==which))}
function toast(t){$('toast').textContent=t;$('toast').classList.remove('hidden');setTimeout(()=>$('toast').classList.add('hidden'),2800)}
function audio(f=420,d=.11,type='sine',volume=.055){if(muted)return;try{ctx??=new(window.AudioContext||window.webkitAudioContext)();ctx.resume();const osc=ctx.createOscillator(),gain=ctx.createGain();osc.type=type;osc.frequency.setValueAtTime(f,ctx.currentTime);gain.gain.setValueAtTime(volume,ctx.currentTime);gain.gain.exponentialRampToValueAtTime(.001,ctx.currentTime+d);osc.connect(gain);gain.connect(ctx.destination);osc.start();osc.stop(ctx.currentTime+d)}catch{}}
function shuffleSound(){[230,270,310,350,390,440].forEach((f,i)=>setTimeout(()=>audio(f,.08,'triangle',.027),i*90))}
function soundDraw(){audio(360,.13,'triangle');setTimeout(()=>audio(600,.1,'triangle'),150)}
function soundPair(){[620,840].forEach((f,i)=>setTimeout(()=>audio(f,.2),i*120))}
function connection(){return new Promise((resolve,reject)=>{if(ws?.readyState===1)return resolve();ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);ws.onopen=resolve;ws.onerror=reject;ws.onclose=()=>{if(session){toast('연결이 끊겼어요. 재접속 중...');setTimeout(reconnect,2400)}};ws.onmessage=event=>{let d=JSON.parse(event.data);if(d.type==='session'){session={code:d.code,token:d.token};sessionStorage.setItem('jokerSession',JSON.stringify(session));history.replaceState({},'',`?room=${d.code}`)}else if(d.type==='error')toast(d.message);else if(d.type==='state')receive(d)}})}
async function send(obj){try{await connection();ws.send(JSON.stringify(obj))}catch{toast('서버에 연결할 수 없습니다.')}}
function reconnect(){if(!session)return;ws=null;send({type:'reconnect',code:session.code,token:session.token})}
function name(){return $('name').value.trim()||'플레이어'}
$('create').onclick=()=>send({type:'create',name:name()});
$('join').onclick=()=>send({type:'join',code:$('code').value.toUpperCase(),name:name()});
$('copy').onclick=async()=>{let link=`${location.origin}${location.pathname}?room=${state.code}`;try{await navigator.clipboard.writeText(link);toast('초대 링크를 복사했어요!')}catch{prompt('친구에게 이 링크를 보내세요:',link)}};
$('addai').onclick=()=>send({type:'add_ai'});
$('removeai').onclick=()=>{const slots=state.players.map((p,i)=>p?.ai?i:-1).filter(i=>i>=0);if(slots.length)send({type:'remove_ai',seat:slots.at(-1)});else toast('제거할 AI가 없어요.')};
$('start').onclick=$('rematch').onclick=()=>send({type:'start'});
function leave(){send({type:'leave'});session=null;state=null;sessionStorage.removeItem('jokerSession');history.replaceState({},'',location.pathname);show('home')}
$('exitlobby').onclick=$('exitgame').onclick=$('exitend').onclick=leave;
$('sound').onclick=()=>{muted=!muted;$('sound').textContent=muted?'🔇 소리 꺼짐':'🔊 소리 켜짐';if(!muted)audio(550)};
function receive(s){const prev=state;if(prev?.event!==s.event&&s.last.action==='pair')selectedPair=[];state=s;activeCode=s.code;
if(s.phase==='lobby'){show('lobby');lobby()}
else if(s.phase==='playing'||s.phase==='pairing'){show('game');renderGame();if(prev?.event!==s.event){if(s.last.action==='shuffle'){animateShuffle();shuffleSound()}else if(s.last.action==='pair'){animateDiscard(prev,s)}else if(s.last.action==='draw'){animateDraw(prev,s);if((s.discardPile?.length||0)>(prev?.discardPile?.length||0))animateDiscard(prev,s)}}}
else if(s.phase==='finished'){if(prev?.event!==s.event&&s.last.action==='finish'){show('game');renderGame();revealFinal(s);setTimeout(()=>renderEnd(s),2800)}else renderEnd(s)}
}
function lobby(){ $('roomcode').textContent=state.code;const occupied=state.players.filter(Boolean).length;
$('lobbyhint').textContent=`현재 ${occupied}/6명 · 사람 ${state.players.filter(p=>p&&!p.ai).length}명 · AI ${state.players.filter(p=>p?.ai).length}명`;
$('lobbyseats').innerHTML=state.players.map((p,i)=>`<div class="seat">${p?`${p.ai?'🤖':'👤'} ${esc(p.name)}${i===state.seat?' (나)':''}<em>${p.ai?'AI 봇':p.connected?'접속 중':'연결 끊김'}${i===0?' · 방장':''}</em>`:`◇ ${i+1}번 자리<em>비어 있음</em>`}</div>`).join('');
$('hosttools').classList.toggle('hidden',!state.host);$('start').classList.toggle('hidden',!state.host);$('start').disabled=occupied<2;
}
function esc(str){return String(str).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
function place(index,total){ // seats on arc, my seat always below
const coords={1:[],2:[[50,16]],3:[[22,27],[78,27]],4:[[19,37],[50,13],[81,37]],5:[[16,45],[29,16],[71,16],[84,45]],6:[[14,53],[17,21],[50,12],[83,21],[86,53]]};return coords[Math.min(6,total)]?.[index]||[50,15]}
function opponents(){let seats=[];for(let j=1;j<=5;j++){let i=(state.seat+j)%6;if(state.players[i])seats.push(i)}return seats}
function renderGame(){let s=state;const ps=s.players;const mine=ps[s.seat];$('round').textContent=s.round;$('gameroom').textContent=`ROOM ${s.code}`;
$('score').textContent=`승 ${mine.stats.wins} · 패 ${mine.stats.losses} · 연승 ${mine.stats.streak} · 최고 ${mine.stats.best}`;
$('info').textContent=s.spectating?'👁 관전 중 · 손패 공개':s.phase==='pairing'?'🃏 시작 패 짝 정리 중':s.turn===s.seat?'✨ 내 차례':s.turn===null?'게임 종료':`${ps[s.turn]?.name||'플레이어'} 차례`;
$('message').textContent=s.phase==='pairing'?'같은 숫자 두 장을 선택해 중앙에 버리세요':s.turn===s.seat?`${ps[s.target]?.name}의 카드를 선택하세요`:s.last.text;
$('event').textContent=s.last.action==='draw'?'카드를 뽑았습니다':'';
renderDiscard(s);const other=opponents();$('players').innerHTML=other.map((seat,order)=>{let p=ps[seat],pos=place(order,other.length+1),clickable=s.phase==='playing'&&s.turn===s.seat&&s.target===seat&&!animating;
return `<div class="player ${clickable?'pickable':''}" style="left:${pos[0]}%;top:${pos[1]}%"><div class="label ${s.turn===seat?'active':''} ${p.count===0?'out':''}">${p.ai?'🤖':'👤'} ${esc(p.name)} · ${p.count}장 ${p.count===0?('🏅 '+(s.finish.indexOf(seat)+1)+'위'):''}</div><div class="fan">${Array.from({length:p.count},(_,ix)=>`<img class="card" data-seat="${seat}" data-index="${ix}" src="${card(s.spectating&&s.visibleHands?.[seat]?s.visibleHands[seat][ix]:41)}" alt="상대 카드">`).join('')}</div></div>`}).join('');
$('players').querySelectorAll('.pickable img').forEach(el=>el.onclick=()=>{if(animating)return;animating=true;send({type:'draw',index:Number(el.dataset.index)});setTimeout(()=>animating=false,820)});
$('mycards').innerHTML=s.hand.map((c,i)=>`<img data-handindex="${i}" class="card ${selectedPair.includes(i)?'selectedpair':''}" src="${card(c)}" alt="내 카드" style="--rot:${((i-(s.hand.length-1)/2)*Math.min(5,50/Math.max(s.hand.length,1))).toFixed(2)}deg;--y:${Math.abs(i-(s.hand.length-1)/2)*1.0}px">`).join('');
 renderPairUI(s);renderSpectatorUI(s);
}
function animateShuffle(){
 const felt=document.querySelector('.felt');if(!felt)return;
 const layer=document.createElement('div');layer.className='shuffle-layer';
 for(let i=0;i<12;i++){
   const img=document.createElement('img');img.src=card(41);img.className='card shuffle-card';
   img.style.setProperty('--delay',`${i*.075}s`);img.style.setProperty('--dx',`${(i%2?1:-1)*(40+i*9)}px`);
   img.style.setProperty('--rot',`${(i%2?1:-1)*(40+i*3)}deg`);layer.append(img);
 }
 felt.append(layer);
 // Finish the shuffle by dealing face-down cards to all seats.
 setTimeout(()=>{for(let i=0;i<Math.min(12,state.players.filter(Boolean).length*2);i++){
   const el=document.createElement('img');el.src=card(41);el.className='card deal-card';felt.append(el);
   const occupied=[...felt.querySelectorAll('.player .fan, #mycards')];const target=occupied[i%occupied.length];
   if(target){let fr=felt.getBoundingClientRect(),tr=target.getBoundingClientRect();
    el.animate([{transform:'translate(-50%,-50%) rotate(0deg)',opacity:1},
    {transform:`translate(${tr.left-fr.left+tr.width/2-fr.width/2}px,${tr.top-fr.top+tr.height/2-fr.height/2}px) rotate(${i%2?14:-14}deg) scale(.8)`,opacity:0}],{duration:650,delay:i*75,fill:'forwards',easing:'cubic-bezier(.2,.7,.2,1)'});
   }
   setTimeout(()=>el.remove(),1700);
 }} ,650);
 setTimeout(()=>layer.remove(),2000);
}
function animateDraw(prev,s){
 soundDraw();if(s.last.discard?.length)setTimeout(soundPair,700);
 const felt=document.querySelector('.felt');if(!felt)return;
 const fromSeat=s.last.from,drawSeat=s.last.drawer;
 const from=document.querySelector(`[data-seat="${fromSeat}"] .card`)||document.querySelector('#mycards .card');
 const to=drawSeat===s.seat?document.getElementById('mycards'):
  document.querySelector(`[data-seat="${drawSeat}"]`)?.parentElement?.querySelector('.fan');
 const a=from?.getBoundingClientRect()||felt.getBoundingClientRect();
 const b=to?.getBoundingClientRect()||felt.getBoundingClientRect();
 const flying=document.createElement('div');flying.className='flying-3d';
 const back=document.createElement('img');back.src=card(41);back.className='flying-back';
 const front=document.createElement('img');front.src=drawSeat===s.seat&&Number.isInteger(s.last.card)?card(s.last.card):card(41);front.className='flying-front';
 flying.append(back,front);document.body.append(flying);
 const startX=a.left+a.width/2-31,startY=a.top+a.height/2-44;
 const endX=b.left+b.width/2-31,endY=b.top+b.height/2-44;
 flying.style.left=`${startX}px`;flying.style.top=`${startY}px`;
 const dx=endX-startX,dy=endY-startY;
 flying.animate([
 {transform:'translate(0,0) rotateZ(-12deg) rotateY(0deg) scale(.8)',offset:0},
 {transform:`translate(${dx*.45}px,${dy*.45-85}px) rotateZ(12deg) rotateY(80deg) scale(1.3)`,offset:.5},
 {transform:`translate(${dx}px,${dy}px) rotateZ(0deg) rotateY(${drawSeat===s.seat?180:360}deg) scale(.9)`,offset:1}
 ],{duration:900,fill:'forwards',easing:'cubic-bezier(.23,.7,.25,1)'});
 setTimeout(()=>flying.remove(),1000);
 if(s.last.discard?.length&&drawSeat===s.seat){
  setTimeout(()=>{const note=document.createElement('div');note.className='pair-burst';note.textContent='✨ PAIR!';felt.append(note);setTimeout(()=>note.remove(),1050)},800)
 }
}
function revealFinal(s){let res=s.results;if(!res)return;const loser=s.players[res.loser];$('jokerImg').src=card(res.joker);$('jokerName').textContent=`${loser?.name||'플레이어'}에게 조커가 남았다!`;$('jokerOverlay').classList.remove('hidden');[300,230,170].forEach((f,i)=>setTimeout(()=>audio(f,.55,'sawtooth',.07),i*300));setTimeout(()=>$('jokerOverlay').classList.add('hidden'),2600)}
function renderEnd(s){show('end');const loser=s.results?.loser,mine=s.players[s.seat];$('endtitle').textContent=loser===s.seat?'조커를 가진 패배자!':'🎉 조커를 피했어요!';$('endsub').textContent=`${s.players[loser]?.name||'플레이어'}님에게 조커가 남았어요.`;
$('ranking').innerHTML=(s.results?.order||[]).map((id,i)=>`<div>${id===loser?'🃏 패배':`🏅 ${i+1}위`} · ${esc(s.players[id]?.name||'플레이어')} ${id===s.seat?'(나)':''}</div>`).join('');$('myrecord').textContent=`내 기록: ${mine.stats.wins}승 ${mine.stats.losses}패 · 현재 ${mine.stats.streak}연승 · 최고 ${mine.stats.best}연승`;$('rematch').classList.toggle('hidden',!s.host)}
const urlRoom=new URLSearchParams(location.search).get('room');if(urlRoom){$('code').value=urlRoom.toUpperCase();$('join').textContent='초대받은 방 입장'}
try{const saved=JSON.parse(sessionStorage.getItem('jokerSession'));if(saved){session=saved;reconnect()}}catch{}

function renderDiscard(s){
 const zone=$('discard-stack'),count=$('discard-count');if(!zone)return;
 let pile=s.discardPile||[];count.textContent='버린 카드 '+pile.length+'장';
 zone.innerHTML=pile.map((x,i)=>'<img src="'+card(41)+'" class="pile-card" style="--n:'+i+';--angle:'+((i*7)%13-6)+'deg">').join('');
}
function animateDiscard(prev,s){
 const cards=(s.discardPile||[]).slice((prev?.discardPile||[]).length);
 const zone=$('discard-stack'),felt=document.querySelector('.felt');if(!zone||!felt||!cards.length)return;
 let a=(s.last.drawer===s.seat?$('mycards'):document.querySelector('.player .fan'))?.getBoundingClientRect()||felt.getBoundingClientRect(),b=zone.getBoundingClientRect();
 cards.forEach((id,i)=>{let el=document.createElement('img');el.src=card(id);el.className='discard-flight';el.style.left=(a.left+a.width/2-27)+'px';el.style.top=(a.top+a.height/2-38)+'px';document.body.append(el);let dx=b.left+b.width/2-(a.left+a.width/2),dy=b.top+b.height/2-(a.top+a.height/2);
 el.animate([{transform:'translate(0,0) rotate(-14deg)'},{transform:'translate('+dx*.5+'px,'+(dy*.5-80)+'px) rotate(18deg) rotateY(90deg)',offset:.55},{transform:'translate('+dx+'px,'+dy+'px) rotate(0deg) rotateY(180deg) scale(.83)'}],{duration:850,delay:i*170,fill:'forwards',easing:'ease-in-out'});setTimeout(()=>{el.src=card(41)},430+i*170);setTimeout(()=>el.remove(),1000+i*170)});
}

function renderPairUI(s){
 const active=s.phase==='pairing'&&!s.ready?.[s.seat];$('pairtools').classList.toggle('hidden',s.phase!=='pairing');
 $('pairdiscard').disabled=!active||selectedPair.length!==2;
 $('pairready').disabled=!active;
 $('pairhint').textContent=s.ready?.[s.seat]?'준비 완료 · 다른 플레이어를 기다리는 중':selectedPair.length+' / 2장 선택';
 $('mycards').querySelectorAll('[data-handindex]').forEach(el=>el.onclick=()=>{
  if(!active)return;const i=Number(el.dataset.handindex);selectedPair=selectedPair.includes(i)?selectedPair.filter(x=>x!==i):selectedPair.length<2?[...selectedPair,i]:[i];
  renderGame();
 });
}
$('pairdiscard').onclick=()=>{if(selectedPair.length!==2)return;send({type:'discard_pair',indices:selectedPair});selectedPair=[]};
$('pairready').onclick=()=>{selectedPair=[];send({type:'pair_ready'})};
function renderSpectatorUI(s){
 const active=s.phase==='playing'&&s.spectating;const panel=$('spectools');panel.classList.toggle('hidden',!active);if(!active)return;
 const seats=s.players.map((p,i)=>p&&p.count?i:null).filter(i=>i!==null);
 if(!seats.includes(spectateSeat))spectateSeat=seats[0]??null;
 $('spectarget').innerHTML=seats.map(i=>'<option value="'+i+'" '+(i===spectateSeat?'selected':'')+'>'+esc(s.players[i].name)+'</option>').join('');
 const cards=s.visibleHands?.[spectateSeat]||[];
 $('specthand').innerHTML=cards.map(id=>'<img src="'+card(id)+'" class="card">').join('');
 $('chatlog').innerHTML=(s.chat||[]).map(m=>'<div><strong>'+esc(m.name)+'</strong>: '+esc(m.text)+'</div>').join('');
}
$('spectarget').onchange=e=>{spectateSeat=Number(e.target.value);renderSpectatorUI(state)};
$('chatsend').onclick=()=>{let el=$('chatinput');if(!el.value.trim())return;send({type:'spectator_chat',text:el.value});el.value=''};
$('chatinput').onkeydown=e=>{if(e.key==='Enter')$('chatsend').click()};
$('discard-stack').onclick=()=>{if(!state)return;$('pilemodal').classList.remove('hidden');$('pilelist').innerHTML=(state.discardPile||[]).map(id=>'<img src="'+card(id)+'" class="card">').join('')};
$('pileclose').onclick=()=>$('pilemodal').classList.add('hidden');
