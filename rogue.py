import asyncio, random, secrets
from aiohttp import web, WSMsgType

ROOMS={}
RARITY={'일반':58,'희귀':27,'영웅':11,'전설':4}
# id, name, rarity, description
AUGS=[
('power','강철 손가락','일반','짝 피해 +2'),('guard','두꺼운 장갑','일반','받는 피해 -1'),
('heal','응급 처치','일반','스테이지 클리어 시 체력 2 회복'),('lucky','행운의 주사위','일반','짝 피해 20% 확률로 2배'),
('focus','정밀 감각','일반','기본 공격 피해 +1'),('heart','여분의 심장','일반','최대 체력 +6, 즉시 6 회복'),
('armor','카드 갑옷','일반','보스전 받는 피해 -2'),('thorns','반격의 가시','일반','적에게 공격받으면 피해 2 반사'),
('potion','약초 수집가','일반','매 스테이지 시작 시 체력 1 회복'),('hand','카드 전문가','일반','짝을 만들면 추가 피해 +1'),
('critical','치명적인 손','희귀','25% 확률로 피해 +6'),('ward','수호 룬','희귀','받는 피해 -2'),
('vamp','흡혈 계약','희귀','짝을 만들면 체력 2 회복'),('boss','보스 사냥꾼','희귀','보스에게 피해 +5'),
('combo','연속의 기술','희귀','연속 짝 성공 시 피해 증가'),('resist','불굴의 의지','희귀','최대 체력 +10'),
('echo','메아리 카드','희귀','20% 확률로 공격 피해 재발동'),('fortune','금빛 손','희귀','짝 피해 +3'),
('poison','독 묻은 카드','영웅','짝 성공 시 적에게 독 3 부여'),('frost','서리 문장','영웅','짝 성공 시 다음 적 공격 -2'),
('phoenix','불사조 깃털','영웅','한 번 쓰러질 때 체력 10으로 부활'),('gamble','도박사의 심장','영웅','30% 확률로 피해 3배, 실패하면 기본 피해'),
('execute','처형자','영웅','체력 30% 이하 적에게 피해 2배'),('regen','재생의 문장','영웅','턴마다 체력 2 회복'),
('meteor','운석 카드','전설','짝 성공 시 추가 피해 12'),('crown','조커의 왕관','전설','조커를 뽑아도 저주 피해 없음, 공격 +4'),
('immortal','불멸의 방패','전설','받는 피해 -4'),('storm','번개 사슬','전설','매 공격 추가 피해 +7'),
('holy','성스러운 빛','전설','짝 성공 시 전원 체력 3 회복'),('destiny','운명 재작성','전설','공격 피해 35% 확률로 2배')]
RELICS=[('lantern','진실의 랜턴','공격 피해 +3'),('chalice','생명의 성배','스테이지 완료 시 전원 체력 +4'),('shield','왕의 방패','피해 -2'),('dice','운명의 주사위','추가 치명타 확률 +15%'),('blade','붉은 검','보스 피해 +6'),('feather','불사조의 깃','부활 1회'),('bell','황금 종','공격 피해 +2'),('star','별의 파편','공격 피해 +5, 받는 피해 +1')]
ENEMIES=['떠돌이 도둑','낡은 카드 병사','어둠의 셔플러','조커 추종자','검은 패의 기사']
BOSSES=['가면 쓴 딜러','조커 수호자','운명의 왕']
def rank(c):return (c-2)%13 if c>=2 else -1
def rng_options(pool,used=()):
    avail=[a for a in pool if a[0] not in used] or pool
    found=[]
    while avail and len(found)<3:
        weighted=[RARITY.get(a[2],12) if len(a)>3 else 1 for a in avail]
        a=random.choices(avail,weights=weighted,k=1)[0]
        found.append(a);avail.remove(a)
    return [a[0] for a in found]
def player(name,ws=None,ai=False):
    return dict(name=name,ws=ws,ai=ai,token=secrets.token_hex(12),hp=30,maxhp=30,aug=[],relic=[],offer=[],ready=False,phoenix=False,streak=0)
def mods(p):
    keys=p['aug']+p['relic']
    def count(x):return keys.count(x)
    return count
def snapshot(r,index):
    p=r['players'][index];phase=r['phase']
    return dict(type='state',code=r['code'],seat=index,host=index==r['host'],phase=phase,stage=r['stage'],enemy=r.get('enemy'),turn=r.get('turn'),log=r['log'][-16:],players=[dict(name=x['name'],ai=x['ai'],hp=x['hp'],maxhp=x['maxhp'],ready=x['ready'],aug=x['aug'],relic=x['relic']) for x in r['players']],hand=r['hands'][index] if phase=='battle' else [],enemyCount=len(r.get('enemy_cards',[])),offer=p['offer'],rarity=RARITY,augs=AUGS,relics=RELICS)
async def send(r):
    for i,p in enumerate(r['players']):
        ws=p.get('ws')
        if ws and not ws.closed:
            try:await ws.send_json(snapshot(r,i))
            except Exception:pass
def log(r,msg):r['log'].append(msg);r['log']=r['log'][-30:]
def next_turn(r):
    alive=[i for i,p in enumerate(r['players']) if p['hp']>0]
    if not alive:
        r['phase']='lost';r['turn']=None;log(r,'파티 전멸! 다시 도전하세요.');return
    current=r.get('turn')
    if current not in alive:r['turn']=alive[0]
    else:
        pos=alive.index(current);r['turn']=alive[(pos+1)%len(alive)]
        if pos==len(alive)-1:
            enemy_attack(r)
            if not [i for i,p in enumerate(r['players']) if p['hp']>0]:
                r['phase']='lost';r['turn']=None;log(r,'파티 전멸! 다시 도전하세요.')
def enemy_attack(r):
    target=random.choice([p for p in r['players'] if p['hp']>0])
    c=mods(target);damage=max(0,r['enemy']['attack']-c('guard')-2*c('ward')-4*c('immortal')-2*c('shield')-2*c('armor')*(r['stage']%5==0)+c('star'))
    damage=max(0,damage-r['enemy'].get('frost',0));r['enemy']['frost']=0
    target['hp']-=damage
    r['enemy']['hp']=max(0,r['enemy']['hp']-2*c('thorns'))
    log(r,f"적 공격! {target['name']} 체력 -{damage}")
    if target['hp']<=0 and (c('phoenix')+c('feather')) and not target['phoenix']:
        target['phoenix']=True;target['hp']=10;log(r,target['name']+' 부활!')
def stage_start(r):
    n=r['stage'];boss=n%5==0
    r['enemy']=dict(name=BOSSES[(n//5-1)%3] if boss else ENEMIES[(n-1)%5],hp=32+n*11+(30 if boss else 0),maxhp=32+n*11+(30 if boss else 0),attack=2+n//3+(3 if boss else 0),poison=0,frost=0,boss=boss)
    r['enemy_cards']=[random.choice(range(2,41)) for _ in range(18)]
    r['hands']=[[random.choice(range(2,41)) for _ in range(5)] for p in r['players']]
    for p in r['players']:
        p['hp']=min(p['maxhp'],p['hp']+mods(p)('potion'));p['streak']=0
    r['phase']='battle';r['turn']=next((i for i,p in enumerate(r['players']) if p['hp']>0),None)
    log(r,f"STAGE {n} — {r['enemy']['name']} 등장!")
def reward(r):
    r['phase']='reward';r['turn']=None
    is_boss=r['stage']%5==0
    for p in r['players']:
        c=mods(p)
        p['hp']=min(p['maxhp'],p['hp']+2*c('heal')+4*c('chalice'))
        pool=RELICS if is_boss else AUGS
        p['offer']=rng_options(pool,p['relic'] if is_boss else []) 
        p['ready']=False
    log(r,'보스를 처치해 유물을 얻습니다!' if is_boss else '스테이지 클리어! 증강을 선택하세요.')
def attack(r,seat,index):
    if r['phase']!='battle' or r['turn']!=seat:return '차례가 아니에요.'
    if type(index)!=int or not 0<=index<len(r['enemy_cards']):return '카드를 다시 선택해 주세요.'
    p=r['players'][seat];c=mods(p)
    p['hp']=min(p['maxhp'],p['hp']+2*c('regen'))
    if p['hp']<=0:return '탈락한 플레이어예요.'
    card=r['enemy_cards'].pop(index);hand=r['hands'][seat]
    found=next((i for i,x in enumerate(hand) if rank(x)==rank(card) and rank(card)!=-1),None)
    if found is None:
        hand.append(card);damage=0;p['streak']=0
        if rank(card)==-1 and not c('crown'):
            p['hp']-=3;log(r,p['name']+' 조커 저주! 체력 -3')
        log(r,p['name']+' 카드 뽑기 — 짝 없음')
    else:
        hand.pop(found);p['streak']+=1
        damage=5+2*c('power')+c('focus')+c('hand')+3*c('fortune')+3*c('lantern')+2*c('bell')+5*c('star')+4*c('crown')+7*c('storm')+12*c('meteor')+min(9,max(0,p['streak']-1)*2*c('combo'))
        if r['enemy']['boss']:damage+=5*c('boss')+6*c('blade')
        if r['enemy']['hp']<=r['enemy']['maxhp']*.3:damage*=2 if c('execute') else 1
        if random.random()<.2*c('lucky')+.15*c('dice')+.25*c('critical'):damage+=6 if c('critical') else damage
        if random.random()<.35*c('destiny')+.3*c('gamble'):damage*=2
        if random.random()<.2*c('echo'):damage*=2
        p['hp']=min(p['maxhp'],p['hp']+2*c('vamp'))
        for ally in r['players']:ally['hp']=min(ally['maxhp'],ally['hp']+3*c('holy'))
        r['enemy']['poison']+=3*c('poison');r['enemy']['frost']+=2*c('frost')
        log(r,f"{p['name']} 짝 성공! {damage} 피해")
    r['enemy']['hp']-=damage+r['enemy']['poison']
    if r['enemy']['hp']<=0:
        log(r,r['enemy']['name']+' 격파!');reward(r);return None
    if not r['enemy_cards']:r['enemy_cards']=[random.choice(range(2,41)) for _ in range(15)]
    next_turn(r)
    if r['phase']=='battle' and r['enemy']['hp']<=0:reward(r)
    return None
async def ai_step(r):
    while r['phase']=='battle' and r['turn'] is not None and r['players'][r['turn']]['ai']:
        await asyncio.sleep(.6)
        if r['phase']!='battle':break
        attack(r,r['turn'],random.randrange(len(r['enemy_cards'])))
        await send(r)
def schedule(r):
    if r['phase']=='battle' and r['turn'] is not None and r['players'][r['turn']]['ai']:
        asyncio.create_task(ai_step(r))
async def ws_handler(req):
    ws=web.WebSocketResponse(heartbeat=25);await ws.prepare(req)
    room=None;seat=None
    try:
        async for msg in ws:
            if msg.type!=WSMsgType.TEXT:continue
            try:d=__import__('json').loads(msg.data)
            except Exception:continue
            cmd=d.get('type')
            if cmd=='create':
                code=secrets.token_hex(3).upper()
                room=dict(code=code,players=[player(str(d.get('name','플레이어'))[:15],ws)],host=0,phase='lobby',stage=1,turn=None,hands=[],enemy=None,log=['로그라이크 생존 대기실'],enemy_cards=[])
                ROOMS[code]=room;seat=0
                await ws.send_json({'type':'session','code':code,'token':room['players'][0]['token']});await send(room)
            elif cmd=='join':
                room=ROOMS.get(str(d.get('code','')).upper())
                if not room or room['phase']!='lobby' or len(room['players'])>=6:
                    await ws.send_json({'type':'error','message':'방에 입장할 수 없어요.'});room=None;continue
                seat=len(room['players']);room['players'].append(player(str(d.get('name','플레이어'))[:15],ws))
                await ws.send_json({'type':'session','code':room['code'],'token':room['players'][seat]['token']});await send(room)
            elif cmd=='reconnect':
                room=ROOMS.get(str(d.get('code','')).upper())
                seat=next((i for i,p in enumerate(room['players']) if p['token']==d.get('token') and not p['ai']),None) if room else None
                if seat is None:
                    await ws.send_json({'type':'error','message':'재접속 불가'});room=None;continue
                room['players'][seat]['ws']=ws;await send(room)
            elif room is None:continue
            elif cmd=='add_ai' and seat==room['host'] and room['phase']=='lobby' and len(room['players'])<6:
                room['players'].append(player(f"AI {len(room['players'])+1}",ai=True));await send(room)
            elif cmd=='remove_ai' and seat==room['host'] and room['phase']=='lobby':
                if room['players'][-1]['ai']:room['players'].pop();await send(room)
            elif cmd=='start' and seat==room['host'] and room['phase']=='lobby':
                if all(p['ai'] or p['ws'] and not p['ws'].closed for p in room['players']):
                    stage_start(room);await send(room);schedule(room)
            elif cmd=='attack':
                err=attack(room,seat,d.get('index'))
                if err:await ws.send_json({'type':'error','message':err})
                else:await send(room);schedule(room)
            elif cmd=='choose' and room['phase']=='reward':
                p=room['players'][seat];key=d.get('id')
                if p['ready'] or key not in p['offer']:continue
                if room['stage']%5==0:p['relic'].append(key)
                else:
                    p['aug'].append(key)
                    if key in ('heart','resist'):
                        inc=6 if key=='heart' else 10;p['maxhp']+=inc;p['hp']+=inc
                p['ready']=True;log(room,p['name']+' 보상 선택 완료')
                for ai in room['players']:
                    if ai['ai'] and not ai['ready']:
                        key=random.choice(ai['offer'])
                        if room['stage']%5==0:ai['relic'].append(key)
                        else:ai['aug'].append(key)
                        ai['ready']=True
                if all(x['ready'] for x in room['players']):
                    if room['stage']>=15:room['phase']='won';log(room,'15스테이지 클리어! 생존 성공!')
                    else:room['stage']+=1;stage_start(room)
                await send(room);schedule(room)
    finally:
        if room and seat is not None and seat<len(room['players']) and room['players'][seat]['ws'] is ws:room['players'][seat]['ws']=None
    return ws
def setup(app):
    app.router.add_get('/rogue/ws',ws_handler)
