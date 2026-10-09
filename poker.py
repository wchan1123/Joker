import asyncio, random, secrets, itertools, json
from collections import Counter
from aiohttp import web, WSMsgType

ROOMS={}
SUITS='SHDC'
def deck():return [(r,s) for r in range(2,15) for s in SUITS]
def score5(cards):
    ranks=sorted((r for r,s in cards),reverse=True);cnt=Counter(ranks)
    flush=len({s for r,s in cards})==1
    uniq=sorted(set(ranks),reverse=True)
    if 14 in uniq:uniq.append(1)
    straight=next((uniq[i] for i in range(len(uniq)-4) if uniq[i]-uniq[i+4]==4),0)
    if straight and flush:return (8,straight)
    groups=sorted(((n,r) for r,n in cnt.items()),reverse=True)
    if groups[0][0]==4:return (7,groups[0][1],groups[1][1])
    if groups[0][0]==3 and groups[1][0]>=2:return (6,groups[0][1],groups[1][1])
    if flush:return (5,*ranks)
    if straight:return (4,straight)
    if groups[0][0]==3:return (3,groups[0][1],*sorted((r for r in ranks if r!=groups[0][1]),reverse=True))
    pairs=sorted((r for r,n in cnt.items() if n==2),reverse=True)
    if len(pairs)==2:return (2,*pairs,next(r for r in ranks if r not in pairs))
    if pairs:return (1,pairs[0],*sorted((r for r in ranks if r!=pairs[0]),reverse=True))
    return (0,*ranks)
def handscore(cards):return max(map(score5,itertools.combinations(cards,5)))
NAMES=['하이 카드','원 페어','투 페어','트리플','스트레이트','플러시','풀하우스','포카드','스트레이트 플러시']
def player(name,ws=None,ai=False):return dict(name=name,ws=ws,ai=ai,token=secrets.token_hex(12),chips=1000,hand=[],fold=False,bet=0,total=0,acted=False,allin=False)
def active(r):return [i for i,p in enumerate(r['players']) if not p['fold']]
def available(r):return [i for i in active(r) if not r['players'][i]['allin']]
def nxt(r,seat,eligible):
    for step in range(1,len(r['players'])+1):
        i=(seat+step)%len(r['players'])
        if i in eligible:return i
    return None
def snapshot(r,i):
    p=r['players'][i]
    return dict(type='state',code=r['code'],seat=i,host=i==r['host'],phase=r['phase'],street=r.get('street'),board=r['board'],pot=sum(x['total'] for x in r['players']),current=r['current'],turn=r['turn'],dealer=r['dealer'],minraise=r['minraise'],players=[dict(name=x['name'],ai=x['ai'],chips=x['chips'],bet=x['bet'],total=x['total'],fold=x['fold'],allin=x['allin'],count=len(x['hand']),cards=x['hand'] if i==j or r['phase']=='showdown' and not x['fold'] else None) for j,x in enumerate(r['players'])],hand=p['hand'],log=r['log'][-15:],winner=r.get('winner'),sb=10,bb=20)
async def send(r):
    await asyncio.gather(*(p['ws'].send_json(snapshot(r,i)) for i,p in enumerate(r['players']) if p['ws'] and not p['ws'].closed),return_exceptions=True)
def note(r,s):r['log'].append(s);r['log']=r['log'][-35:]
def pay(p,n):
    v=min(p['chips'],n);p['chips']-=v;p['bet']+=v;p['total']+=v
    if not p['chips']:p['allin']=True
def newhand(r):
    eligible=[i for i,p in enumerate(r['players']) if p['chips']>0]
    if len(eligible)<2:r['phase']='over';r['turn']=None;note(r,'게임 종료 · 칩을 보유한 마지막 플레이어 승리');return
    r['dealer']=nxt(r,r.get('dealer',-1),eligible)
    for p in r['players']:
        p.update(hand=[],fold=p['chips']==0,bet=0,total=0,acted=False,allin=False)
    cards=deck();random.shuffle(cards);r['deck']=cards;r['board']=[];r['street']='프리플롭';r['winner']=None
    for _ in range(2):
        for i in range(len(r['players'])):
            if i in eligible:r['players'][i]['hand'].append(cards.pop())
    if len(eligible)==2:
        sb=r['dealer'];bb=nxt(r,sb,eligible)
    else:
        sb=nxt(r,r['dealer'],eligible);bb=nxt(r,sb,eligible)
    pay(r['players'][sb],10);pay(r['players'][bb],20)
    r['current']=max(p['bet'] for p in r['players']);r['minraise']=20
    r['turn']=nxt(r,bb,available(r));r['phase']='betting'
    note(r,'새 핸드! 스몰 블라인드 10 / 빅 블라인드 20')
    advance_if_needed(r)
def needs_action(r,i):return i in available(r) and (not r['players'][i]['acted'] or r['players'][i]['bet']<r['current'])
def advance_if_needed(r):
    if len(active(r))==1:return award(r)
    if any(needs_action(r,i) for i in range(len(r['players']))):
        if r['turn'] is None or not needs_action(r,r['turn']):
            choices=[i for i in range(len(r['players'])) if needs_action(r,i)]
            r['turn']=nxt(r,r['dealer'],choices)
        return
    steps={'프리플롭':('플롭',3),'플롭':('턴',1),'턴':('리버',1)}
    if r['street']=='리버':return award(r)
    street,count=steps[r['street']];r['street']=street
    r['deck'].pop() # burn card
    for _ in range(count):r['board'].append(r['deck'].pop())
    for p in r['players']:p['bet']=0;p['acted']=False
    r['current']=0;r['minraise']=20
    note(r,street+' 공개')
    options=available(r)
    r['turn']=nxt(r,r['dealer'],options) if options else None
    if len(options)<=1:
        for p in r['players']:p['acted']=True
        advance_if_needed(r)
def award(r):
    contenders=active(r)
    levels=sorted(set(p['total'] for p in r['players'] if p['total']>0))
    prev=0;paid=Counter();details=[]
    for level in levels:
        share=(level-prev)*sum(p['total']>=level for p in r['players']);prev=level
        participants=[i for i in contenders if r['players'][i]['total']>=level]
        if not participants:continue
        best=max(handscore(r['players'][i]['hand']+r['board']) for i in participants) if len(contenders)>1 else None
        wins=[i for i in participants if len(contenders)==1 or handscore(r['players'][i]['hand']+r['board'])==best]
        portion,rem=divmod(share,len(wins))
        for i in wins:paid[i]+=portion
        for i in sorted(wins,key=lambda j:(j-r['dealer'])%len(r['players']))[:rem]:paid[i]+=1
        if best is not None:details.append(NAMES[best[0]])
    for i,value in paid.items():r['players'][i]['chips']+=value
    r['phase']='showdown';r['turn']=None
    r['winner']=[dict(seat=i,name=r['players'][i]['name'],amount=amount) for i,amount in paid.items()]
    note(r,'정산 완료: '+', '.join(r['players'][i]['name']+' +'+str(amount) for i,amount in paid.items()))
def action(r,seat,cmd,amount=None):
    if r['phase']!='betting' or r['turn']!=seat:return '지금 내 차례가 아니에요.'
    p=r['players'][seat];due=r['current']-p['bet']
    if cmd=='fold':p['fold']=True;note(r,p['name']+' 폴드')
    elif cmd=='check':
        if due:return '콜이 필요해요.'
        note(r,p['name']+' 체크')
    elif cmd=='call':pay(p,due);note(r,p['name']+' 콜')
    elif cmd=='raise':
        if not isinstance(amount,int) or isinstance(amount,bool):return '숫자를 입력하세요.'
        maximum=p['bet']+p['chips']
        if amount<=r['current'] or amount>maximum:return '베팅 금액이 올바르지 않아요.'
        inc=amount-r['current']
        if inc<r['minraise'] and amount!=maximum:return '최소 레이즈 금액을 확인하세요.'
        pay(p,amount-p['bet']);r['current']=amount
        if inc>=r['minraise']:
            r['minraise']=inc
            for q in r['players']:q['acted']=False
        note(r,p['name']+' 레이즈 → '+str(amount))
    else:return '잘못된 명령이에요.'
    p['acted']=True
    choices=[i for i in range(len(r['players'])) if needs_action(r,i)]
    r['turn']=nxt(r,seat,choices) if choices else None
    advance_if_needed(r)
async def ai_play(r):
    while r['phase']=='betting' and r['turn'] is not None and r['players'][r['turn']]['ai']:
        await asyncio.sleep(.85)
        if r['phase']!='betting':return
        i=r['turn'];p=r['players'][i];due=r['current']-p['bet']
        cmd='call' if due else 'check'
        if due>p['chips']*.6 and random.random()<.35:cmd='fold'
        action(r,i,cmd);await send(r)
def schedule(r):
    if r['phase']=='betting' and r['turn'] is not None and r['players'][r['turn']]['ai']:
        asyncio.create_task(ai_play(r))
async def handler(req):
    ws=web.WebSocketResponse(heartbeat=25);await ws.prepare(req);r=None;seat=None
    try:
        async for msg in ws:
            if msg.type!=WSMsgType.TEXT:continue
            try:d=json.loads(msg.data)
            except Exception:continue
            cmd=d.get('type')
            if cmd=='create':
                code=secrets.token_hex(3).upper();r=dict(code=code,players=[player(str(d.get('name','플레이어'))[:14],ws)],host=0,phase='lobby',dealer=-1,deck=[],board=[],turn=None,current=0,minraise=20,log=[],winner=None)
                ROOMS[code]=r;seat=0
                await ws.send_json(dict(type='session',code=code,token=r['players'][seat]['token']));await send(r)
            elif cmd=='join':
                r=ROOMS.get(str(d.get('code','')).upper())
                if not r or r['phase']!='lobby' or len(r['players'])>=6:
                    await ws.send_json(dict(type='error',message='방에 입장할 수 없어요.'));r=None;continue
                seat=len(r['players']);r['players'].append(player(str(d.get('name','플레이어'))[:14],ws))
                await ws.send_json(dict(type='session',code=r['code'],token=r['players'][seat]['token']));await send(r)
            elif cmd=='reconnect':
                r=ROOMS.get(str(d.get('code','')).upper())
                seat=next((i for i,p in enumerate(r['players']) if not p['ai'] and p['token']==d.get('token')),None) if r else None
                if seat is None:
                    await ws.send_json(dict(type='error',message='재접속 실패'));r=None;continue
                r['players'][seat]['ws']=ws;await send(r)
            elif not r:continue
            elif cmd=='add_ai' and seat==r['host'] and r['phase']=='lobby' and len(r['players'])<6:
                r['players'].append(player('AI '+str(len(r['players'])+1),ai=True));await send(r)
            elif cmd=='remove_ai' and seat==r['host'] and r['phase']=='lobby':
                if r['players'][-1]['ai']:r['players'].pop();await send(r)
            elif cmd in ('start','next') and seat==r['host'] and (r['phase']=='lobby' or cmd=='next' and r['phase']=='showdown'):
                if len(r['players'])>=2 and all(p['ai'] or p['ws'] and not p['ws'].closed for p in r['players']):
                    newhand(r);await send(r);schedule(r)
            elif cmd in ('fold','check','call','raise'):
                result=action(r,seat,cmd,d.get('amount'))
                if result:await ws.send_json(dict(type='error',message=result))
                else:await send(r);schedule(r)
    finally:
        if r and seat is not None and seat<len(r['players']) and r['players'][seat]['ws'] is ws:r['players'][seat]['ws']=None
    return ws
def setup(app):app.router.add_get('/poker/ws',handler)
