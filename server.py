import asyncio, json, random, secrets, os
from aiohttp import web, WSMsgType
ROOT=os.path.dirname(__file__)
rooms={}
MAX=6

def pair_off(hand):
    removed=[]
    ranks={}
    for c in hand:
        if c>=2:ranks.setdefault((c-2)%13,[]).append(c)
    for cards in ranks.values():
        while len(cards)>1:
            a,b=cards.pop(),cards.pop();hand.remove(a);hand.remove(b);removed.extend([a,b])
    return removed

def live(room):return [i for i,p in enumerate(room['players']) if p and room['hands'][i]]
def next_live(room,seat):
    active=live(room)
    if len(active)<2:return None
    return next((i for step in range(1,MAX+1) if (i:=(seat+step)%MAX) in active),None)

def status(room,seat):
    p=room['players'][seat]
    last=room['last'].copy()
    if room['phase']=='playing' and last.get('action')=='draw' and last.get('drawer')!=seat:last.pop('card',None);last.pop('discard',None)
    return dict(type='state',code=room['code'],seat=seat,phase=room['phase'],turn=room['turn'],target=room['target'],round=room['round'],last=last,finish=room['finish'],players=[dict(name=x['name'],ai=x['ai'],connected=bool(x['ai'] or (x['ws'] and not x['ws'].closed)),count=len(room['hands'][i]),stats=x['stats']) if x else None for i,x in enumerate(room['players'])],hand=room['hands'][seat] if room['phase']!='lobby' else [],host=seat==room['host'],results=room['results'],event=room['event'])
async def send(ws,payload):
    if ws and not ws.closed:
        try:await ws.send_json(payload)
        except ConnectionError:pass
async def broadcast(room):
    await asyncio.gather(*(send(p['ws'],status(room,i)) for i,p in enumerate(room['players']) if p and not p['ai']),return_exceptions=True)

def codegen():
    while True:
        c=''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789',k=5))
        if c not in rooms:return c

def prep(room):
    seats=[i for i,p in enumerate(room['players']) if p]
    if len(seats)<2:return False
    # Exactly two cards per rank + one Joker. This guarantees all non-jokers can pair off.
    deck=[]
    for rank in range(13):deck.extend(random.sample([2+rank,15+rank,28+rank],2))
    deck.append(random.choice([0,1]));random.shuffle(deck)
    room['hands']=[[] for _ in range(MAX)]
    for j,c in enumerate(deck):room['hands'][seats[j%len(seats)]].append(c)
    removed=sum(len(pair_off(room['hands'][s])) for s in seats)
    for s in seats:random.shuffle(room['hands'][s])
    room['finish']=[s for s in seats if not room['hands'][s]]
    room['phase']='playing';room['round']+=1;room['results']=None;room['event']+=1
    remaining=live(room)
    room['turn']=random.choice(remaining) if len(remaining)>1 else None
    room['target']=next_live(room,room['turn']) if room['turn'] is not None else None
    room['last']={'text':f'카드를 섞어 나눴어요! 짝 {removed//2}쌍 자동 제거.','action':'shuffle','id':room['event']}
    if len(remaining)<=1:finalize(room)
    return True

def finalize(room):
    room['phase']='finished';room['turn']=None;room['target']=None
    loser=next((s for s in live(room) if any(c<2 for c in room['hands'][s])),None)
    if loser is None:loser=next(iter(live(room)),None)
    order=room['finish'][:]
    if loser is not None and loser not in order:order.append(loser)
    room['results']={'order':order,'loser':loser,'joker':next((c for s in range(MAX) for c in room['hands'][s] if c<2),0)}
    for s in order:
        p=room['players'][s];t=p['stats'];t['games']+=1
        if s==loser:t['losses']+=1;t['streak']=0
        else:t['wins']+=1;t['streak']+=1;t['best']=max(t['best'],t['streak'])
    room['last']={'text':'게임 종료! 마지막 조커의 주인이 결정됐어요.','action':'finish','id':room['event']}

def draw(room,seat,index):
    if room['phase']!='playing' or seat!=room['turn']:return '차례가 아닙니다.'
    target=room['target'];hand=room['hands'][target]
    if not isinstance(index,int) or isinstance(index,bool) or not 0<=index<len(hand):return '카드를 다시 선택해 주세요.'
    card=hand.pop(index);room['hands'][seat].append(card);discard=pair_off(room['hands'][seat]);random.shuffle(room['hands'][seat]);room['event']+=1
    if not room['hands'][target] and target not in room['finish']:room['finish'].append(target)
    if not room['hands'][seat] and seat not in room['finish']:room['finish'].append(seat)
    room['last']={'text':f"{room['players'][seat]['name']} → {room['players'][target]['name']} 카드 뽑기"+(' · 짝 제거!' if discard else ''),'action':'draw','drawer':seat,'from':target,'card':card,'discard':discard,'id':room['event']}
    if len(live(room))<=1:finalize(room)
    else:
        room['turn']=next_live(room,seat)
        room['target']=next_live(room,room['turn'])
    return None

async def ai_drive(room):
    try:
        while room['phase']=='playing' and room['turn'] is not None:
            s=room['turn'];p=room['players'][s]
            if not p or not p['ai']:break
            await asyncio.sleep(random.uniform(.85,1.5))
            if room['phase']!='playing' or room['turn']!=s:break
            target=room['target']
            if not room['hands'][target]:break
            draw(room,s,random.randrange(len(room['hands'][target])))
            await broadcast(room)
    finally:room['ai_task']=None

def schedule_ai(room):
    if room['phase']=='playing' and room['turn'] is not None and room['players'][room['turn']]['ai'] and not room['ai_task']:
        room['ai_task']=asyncio.create_task(ai_drive(room))

async def websocket(req):
    ws=web.WebSocketResponse(heartbeat=25,max_msg_size=4096);await ws.prepare(req)
    room=None;seat=None
    try:
        async for msg in ws:
            if msg.type!=WSMsgType.TEXT:continue
            try:d=json.loads(msg.data)
            except (ValueError,TypeError):continue
            cmd=d.get('type')
            if cmd in ('create','join','reconnect'):
                if room:await send(ws,dict(type='error',message='이미 방에 있습니다.'));continue
                if cmd=='create':
                    code=codegen();room=dict(code=code,players=[None]*MAX,hands=[[] for _ in range(MAX)],phase='lobby',host=0,turn=None,target=None,round=0,last={'text':'친구 또는 AI를 추가하세요.','id':0},finish=[],event=0,results=None,ai_task=None)
                    rooms[code]=room;seat=0
                else:
                    code=str(d.get('code','')).upper().strip();room=rooms.get(code)
                    if not room:await send(ws,dict(type='error',message='방이 없습니다.'));continue
                    if cmd=='reconnect':
                        seat=next((i for i,p in enumerate(room['players']) if p and not p['ai'] and p['token']==d.get('token')),None)
                        if seat is None:await send(ws,dict(type='error',message='재접속 정보가 일치하지 않습니다.'));room=None;continue
                        old=room['players'][seat]['ws']
                        if old and old!=ws:await old.close()
                        room['players'][seat]['ws']=ws
                    else:
                        if room['phase']!='lobby':await send(ws,dict(type='error',message='진행 중인 게임에는 들어갈 수 없습니다.'));room=None;continue
                        seat=next((i for i,p in enumerate(room['players']) if not p),None)
                        if seat is None:await send(ws,dict(type='error',message='정원이 꽉 찼습니다.'));room=None;continue
                if cmd!='reconnect':
                    name=str(d.get('name','플레이어')).strip()[:14] or '플레이어'
                    room['players'][seat]=dict(name=name,ws=ws,token=secrets.token_hex(16),ai=False,stats=dict(games=0,wins=0,losses=0,streak=0,best=0))
                await send(ws,dict(type='session',code=code,token=room['players'][seat]['token']))
                await broadcast(room);schedule_ai(room)
            elif room is None:await send(ws,dict(type='error',message='방에 먼저 입장해 주세요.'))
            elif cmd=='add_ai':
                if seat!=room['host'] or room['phase']!='lobby':await send(ws,dict(type='error',message='방장만 대기실에서 AI를 추가할 수 있습니다.'));continue
                idx=next((i for i,p in enumerate(room['players']) if not p),None)
                if idx is None:await send(ws,dict(type='error',message='최대 6명까지 참여할 수 있습니다.'));continue
                name=f'AI {idx+1}';room['players'][idx]=dict(name=name,ws=None,token='',ai=True,stats=dict(games=0,wins=0,losses=0,streak=0,best=0));await broadcast(room)
            elif cmd=='remove_ai':
                idx=d.get('seat')
                if seat!=room['host'] or room['phase']!='lobby' or type(idx)!=int or not 0<=idx<MAX or not room['players'][idx] or not room['players'][idx]['ai']:
                    await send(ws,dict(type='error',message='AI 제거가 불가능합니다.'));continue
                room['players'][idx]=None;await broadcast(room)
            elif cmd=='start':
                if seat!=room['host'] or room['phase'] not in ('lobby','finished'):await send(ws,dict(type='error',message='방장만 게임을 시작할 수 있습니다.'));continue
                if any(p and not p['ai'] and (not p['ws'] or p['ws'].closed) for p in room['players']):await send(ws,dict(type='error',message='오프라인 플레이어가 있습니다.'));continue
                if not prep(room):await send(ws,dict(type='error',message='최소 두 명(인간 또는 AI)이 필요합니다.'));continue
                await broadcast(room);schedule_ai(room)
            elif cmd=='draw':
                if room['target'] is not None and room['players'][room['target']] and not room['players'][room['target']]['ai'] and (not room['players'][room['target']]['ws'] or room['players'][room['target']]['ws'].closed):
                    await send(ws,dict(type='error',message='상대방 재접속을 기다려주세요.'));continue
                err=draw(room,seat,d.get('index'))
                if err:await send(ws,dict(type='error',message=err));continue
                await broadcast(room);schedule_ai(room)
            elif cmd=='leave':
                if room['phase']=='lobby':
                    room['players'][seat]=None
                    humans=[i for i,p in enumerate(room['players']) if p and not p['ai']]
                    if not humans:rooms.pop(room['code'],None)
                    else:room['host']=humans[0];await broadcast(room)
                else:
                    room['players'][seat]['ws']=None;await broadcast(room)
                room=None;seat=None
    finally:
        if room is not None and seat is not None and room['players'][seat] and room['players'][seat]['ws']==ws:
            room['players'][seat]['ws']=None;await broadcast(room)
    return ws

async def health(req):return web.json_response({'ok':True,'rooms':len(rooms)})
app=web.Application();app.router.add_get('/health',health);app.router.add_get('/ws',websocket);app.router.add_static('/',os.path.join(ROOT,'public'),show_index=True)
if __name__=='__main__':web.run_app(app,host='0.0.0.0',port=int(os.environ.get('PORT','8080')))
