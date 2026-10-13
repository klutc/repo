"""Vsembed's public player protocol, using only portable Python and HTTP."""
import base64
import difflib
import json
import math
import re
import struct
import requests
from urllib.parse import urlsplit,urljoin,parse_qs,urlencode


def leb(data,pos,signed=False):
    value=shift=0
    for _ in range(5):
        byte=data[pos];pos+=1;value|=(byte&127)<<shift;shift+=7
        if byte<128:
            if signed and byte&64:value-=1<<shift
            return value,pos
    raise ValueError('Invalid WebAssembly integer')


def wasm_key(wasm):
    # Read the ChaCha key and its mask from the loader's data segments. Do not
    # execute remote WASM. Match all eight word loads before accepting a key.
    if not wasm.startswith(b'\0asm\x01\0\0\0') or len(wasm)>131072:
        raise ValueError('Vsembed върна непознат декодер.')
    pos=8;memory=bytearray(65536);code=b''
    while pos<len(wasm):
        kind=wasm[pos];pos+=1;size,pos=leb(wasm,pos);part=wasm[pos:pos+size];pos+=size
        if len(part)!=size:raise ValueError('Incomplete WebAssembly section')
        if kind==10:code=part
        if kind!=11:continue
        count,i=leb(part,0)
        if count>128:raise ValueError('Too many data segments')
        for _ in range(count):
            mode,i=leb(part,i)
            if mode!=0 or part[i]!=0x41:raise ValueError('Unsupported WebAssembly data segment')
            offset,i=leb(part,i+1,True)
            if part[i]!=0x0b:raise ValueError('Unsupported WebAssembly offset')
            length,i=leb(part,i+1)
            if offset<0 or offset+length>len(memory) or i+length>len(part):raise ValueError('Invalid data bounds')
            memory[offset:offset+length]=part[i:i+length];i+=length
    start=code.find(b'\x41\x00\x28\x02\x00\x41')
    if start<0:raise ValueError('Vsembed промени формата на декодера.')
    mask,end=leb(code,start+6,True)
    if not 0<=mask<=len(memory)-32:raise ValueError('Invalid key offset')
    pos=start
    for word in range(8):
        if code[pos]!=0x41:raise ValueError('Invalid key load')
        left,pos=leb(code,pos+1,True)
        if code[pos:pos+4]!=b'\x28\x02\x00\x41':raise ValueError('Invalid key load')
        right,pos=leb(code,pos+4,True)
        if left!=word*4 or right!=mask+word*4 or code[pos:pos+5]!=b'\x28\x02\x00\x73\x21':raise ValueError('Invalid key mask')
        _,pos=leb(code,pos+5)
    return bytes(a^b for a,b in zip(memory[:32],memory[mask:mask+32]))


def rot(value,bits):return ((value<<bits)|(value>>(32-bits)))&0xffffffff


def chacha20(key,encrypted):
    if len(key)!=32 or len(encrypted)<12:raise ValueError('Invalid ChaCha20 input')
    nonce,data=encrypted[:12],encrypted[12:];out=bytearray()
    constants=list(struct.unpack('<4I',b'expand 32-byte k'))+list(struct.unpack('<8I',key))
    for counter,offset in enumerate(range(0,len(data),64)):
        initial=constants+[counter]+list(struct.unpack('<3I',nonce));state=initial[:]
        def quarter(a,b,c,d):
            state[a]=(state[a]+state[b])&0xffffffff;state[d]=rot(state[d]^state[a],16)
            state[c]=(state[c]+state[d])&0xffffffff;state[b]=rot(state[b]^state[c],12)
            state[a]=(state[a]+state[b])&0xffffffff;state[d]=rot(state[d]^state[a],8)
            state[c]=(state[c]+state[d])&0xffffffff;state[b]=rot(state[b]^state[c],7)
        for _ in range(10):
            for indices in ((0,4,8,12),(1,5,9,13),(2,6,10,14),(3,7,11,15),(0,5,10,15),(1,6,11,12),(2,7,8,13),(3,4,9,14)):quarter(*indices)
        block=struct.pack('<16I',*((a+b)&0xffffffff for a,b in zip(state,initial)))
        out.extend(a^b for a,b in zip(data[offset:offset+64],block))
    return bytes(out)


def opensubtitle(session,data):
    """Pick a Bulgarian OpenSubtitles file when the Vsembed API has no track."""
    imdb=re.sub(r'^tt','',str(data.get('imdb_id') or '').lower())
    if not imdb.isdigit():return ''
    season,episode=data.get('season'),data.get('episode')
    try:
        season,episode=int(season),int(episode)
    except (TypeError,ValueError):
        season=episode=0
    if season>0 and episode>0:
        url='https://rest.opensubtitles.org/search/episode-%d/imdbid-%s/season-%d/sublanguageid-bul' % (episode,imdb,season)
    else:
        url='https://rest.opensubtitles.org/search/imdbid-'+imdb+'/sublanguageid-bul'
    try:
        response=session.get(url,headers={'X-User-Agent':'trailers.to-UA','Accept':'application/json'},timeout=(8,18))
        response.raise_for_status();rows=response.json()
    except (requests.RequestException,ValueError):return ''
    if not isinstance(rows,list):return ''
    release=str(data.get('file_name') or '').replace('\\','/').rsplit('/',1)[-1]
    release=re.sub(r'\.[^.]+$','',release).lower()
    candidates=[]
    for row in rows:
        if not isinstance(row,dict) or row.get('SubLanguageID')!='bul':continue
        if season and episode:
            try:
                if int(row.get('SeriesSeason') or 0)!=season or int(row.get('SeriesEpisode') or 0)!=episode:continue
            except (TypeError,ValueError):continue
        link=row.get('SubDownloadLink') or ''
        if not link.startswith('https://') or '/filead/' not in link:continue
        name=' '.join(str(row.get(key) or '') for key in ('SubFileName','MovieReleaseName')).lower()
        match=difflib.SequenceMatcher(None,release,name).ratio() if release else 0
        downloads=int(row.get('SubDownloadsCnt') or 0)
        score=match*100+math.log1p(downloads)
        candidates.append((score,link,str(row.get('SubEncoding') or 'UTF-8')))
    if not candidates:return ''
    _,link,encoding=max(candidates,key=lambda item:item[0])
    return link+'|'+urlencode({'_encoding':encoding})


def embedded_subtitle(data,base):
    rows=data.get('default_subs') or (data.get('data') or {}).get('default_subs') or []
    choices=[]
    if isinstance(rows,dict):rows=[rows]
    for row in rows:
        if isinstance(row,str):row={'url':row}
        if not isinstance(row,dict):continue
        address=row.get('url') or row.get('file') or row.get('src')
        if not isinstance(address,str) or not address.startswith(('http://','https://','/')):continue
        language=str(row.get('label') or row.get('language') or row.get('lang') or '').lower()
        score=3 if language in ('bg','bul','bulgarian','български') else 1 if row.get('default') else 0
        choices.append((score,urljoin(base,address)))
    return max(choices,key=lambda item:item[0])[1] if choices else ''


def config(html,name):
    match=re.search(r'window\.'+name+r'\s*=\s*(\{[^\n]+?\})\s*;',html)
    if not match:raise ValueError('Vsembed не предоставя плейър за това видео.')
    return json.loads(match[1])


def resolve(session,url,referer,progress=None):
    from native_resolver import fetch,play_url
    p=urlsplit(url);query=parse_qs(p.query)
    if p.path.startswith('/embed/movie'):
        ident=(query.get('tmdb') or query.get('imdb') or [''])[0];media='movie'
    elif p.path.startswith('/embed/tv'):
        ident=(query.get('tmdb') or query.get('imdb') or [''])[0];media='tv'
    else:raise ValueError('Неподдържан адрес на Vsembed.')
    if not ident:raise ValueError('Липсва идентификатор на Vsembed.')
    params={'type':media,'id':ident,'ds_lang':'bg'}
    for key in ('season','episode'):
        if query.get(key):params[key]=query[key][0]
    origin=p.scheme+'://'+p.netloc
    r=session.get(origin+'/vs_src.php',params=params,headers={'Referer':url},timeout=(10,25));r.raise_for_status();frame=r.json().get('src','')
    html,frame=fetch(session,frame,url);landing=config(html,'CFG')
    player=urljoin(frame,landing['playerUrl']);html,player=fetch(session,player,frame);cfg=config(html,'CONFIG')
    r=session.get(cfg['api'],params={'api_token':cfg.get('apiToken','')},headers={'Referer':player,'Accept':'application/json'},timeout=(10,25));r.raise_for_status();data=r.json();streams=data.get('data',{}).get('stream_urls')
    if isinstance(streams,str):
        decoder=data.get('vs',{})
        if decoder.get('wasm_url'):
            r=session.get(decoder['wasm_url'],headers={'Referer':player},timeout=(10,25));r.raise_for_status();wasm=r.content
        else:wasm=base64.b64decode(decoder.get('wasm',''))
        streams=chacha20(wasm_key(wasm),base64.b64decode(streams)).decode('utf-8').splitlines()
    if not isinstance(streams,list):raise ValueError('Vsembed не върна видеоизточници.')
    for index,stream in enumerate(streams[:5]):
        if progress and progress(40+index*10):raise ValueError('Зареждането е отказано.')
        if not isinstance(stream,str) or not stream.startswith(('http://','https://')):continue
        host=urlsplit(stream);token_url=host.scheme+'://'+host.netloc+'/generate.php'
        try:
            r=session.get(token_url,headers={'Referer':player},timeout=(10,15));token=r.text.strip() if r.ok else ''
            if token.startswith(('{','[','"')):
                obj=json.loads(token);token=obj if isinstance(obj,str) else next((obj.get(k) for k in ('token','data','string','result') if obj.get(k)),'') if isinstance(obj,dict) else ''
            address=stream.replace('__TOKEN__',token) if '__TOKEN__' in stream else stream+('&' if '?' in stream else '?')+urlencode({'token':token}) if token else stream
            r=session.get(address,headers={'Referer':player},timeout=(10,15));r.raise_for_status()
            if not r.text.lstrip().startswith('#EXTM3U'):continue
            subtitle=embedded_subtitle(data,player) or opensubtitle(session,data.get('data') or {})
            return play_url(session,r.url,player),subtitle
        except (ValueError,requests.RequestException):
            continue
    raise ValueError('Видео сървърите на Vsembed са недостъпни. Опитайте отново по-късно.')
