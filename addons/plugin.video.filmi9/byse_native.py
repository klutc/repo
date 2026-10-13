"""HTTP-only Byse/FileMoon client using the player-issued attestation protocol."""
import base64
import datetime
import json
import os
import platform
import time
from urllib.parse import urlsplit,urljoin
import requests
import p256
import byse_pow


def unb64(text):return base64.urlsafe_b64decode(text+'='*((-len(text))%4))


def read_cache(directory,key):
    if not directory:return {}
    try:
        path=os.path.join(directory,'byse-tokens.json')
        if os.path.getsize(path)>262144:return {}
        with open(path,encoding='utf-8') as f:rows=json.load(f)
        if not isinstance(rows,dict):return {}
        row=rows.get(key,{})
        if row.get('expires',0)>time.time()+30 and isinstance(row.get('fingerprint'),dict) and isinstance(row.get('captcha'),str):return row
    except (OSError,ValueError,TypeError):pass
    return {}


def write_cache(directory,key,row):
    if not directory:return
    try:
        os.makedirs(directory,exist_ok=True);path=os.path.join(directory,'byse-tokens.json');rows={}
        try:
            with open(path,encoding='utf-8') as f:rows=json.load(f)
        except (OSError,ValueError):pass
        if not isinstance(rows,dict):rows={}
        rows={k:v for k,v in rows.items() if isinstance(v,dict) and v.get('expires',0)>time.time()};rows[key]=row
        temp=path+'.'+os.urandom(4).hex()+'.tmp'
        with os.fdopen(os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w',encoding='utf-8') as f:json.dump(rows,f)
        os.replace(temp,path)
    except (OSError,ValueError,TypeError):pass


def decrypt_playback(data):
    envelope=data.get('playback')
    if not envelope:return data
    from resolveurl.lib.aesgcm import python_aesgcm
    parts=envelope['key_parts']
    try:version=int(envelope.get('version',''))
    except (TypeError,ValueError):version=0
    indices=[version-1,30-version] if 1<=version<=20 and len(parts)>max(version-1,30-version) else range(len(parts))
    key=b''.join(unb64(parts[i]) for i in indices)
    plain=python_aesgcm.new(key).open(unb64(envelope['iv']),unb64(envelope['payload']))
    if plain is None:raise ValueError('Неуспешно декодиране на видеоадреса на Byse.')
    return json.loads(plain.decode('utf-8'))


def resolve(session,url,referer,progress=None,cache_directory=''):
    from native_resolver import play_url,caption
    parsed=urlsplit(url);host=parsed.scheme+'://'+parsed.netloc;code=parsed.path.rstrip('/').split('/')[-1]
    if not code.isalnum():raise ValueError('Невалиден идентификатор на Byse.')
    parent=urlsplit(referer).hostname or ''
    headers={'Referer':url,'X-Embed-Origin':parent,'X-Embed-Referer':referer,'X-Embed-Parent':url}
    response=session.get(host+'/api/videos/'+code+'/embed/details',headers=headers,timeout=(10,25));response.raise_for_status();frame=response.json().get('embed_frame_url') or url
    frame=urljoin(url,frame);parsed=urlsplit(frame);origin=parsed.scheme+'://'+parsed.netloc
    response=session.get(frame,headers={'Referer':url},timeout=(10,25));response.raise_for_status()
    headers.update({'Referer':frame,'Origin':origin});api=origin+'/api/videos/'+code+'/embed/'
    response=session.get(api+'settings',headers=headers,timeout=(10,25));response.raise_for_status();settings=response.json()
    if settings.get('premium_only'):raise ValueError('Този източник изисква платен достъп при видео хоста.')
    key=origin+'/'+code;cached=read_cache(cache_directory,key)
    for attempt in range(2):
        fingerprint=cached.get('fingerprint');token=cached.get('captcha','')
        if not fingerprint:
            if progress and progress(15):raise ValueError('Зареждането е отказано.')
            access=origin+'/api/videos/access/';access_headers={'Referer':frame,'Origin':origin}
            response=session.post(access+'challenge',headers=access_headers,timeout=(10,25));response.raise_for_status();challenge=response.json()
            public,signature=p256.sign_nonce(challenge['nonce'])
            client={'user_agent':session.headers.get('User-Agent',''),'platform':platform.system(),'architecture':platform.machine(),'languages':['bg'],'timezone':time.tzname[0]}
            body={'viewer_id':os.urandom(16).hex(),'device_id':os.urandom(16).hex(),'challenge_id':challenge['challenge_id'],'nonce':challenge['nonce'],'signature':signature,'public_key':public,'client':client,'storage':{},'attributes':{'entropy':'low'}}
            response=session.post(access+'attest',json=body,headers=access_headers,timeout=(10,25));response.raise_for_status();attested=response.json()
            fingerprint={k:attested[k] for k in ('token','viewer_id','device_id','confidence')}
            response=session.post(api+'captcha',json={'fingerprint':fingerprint},headers=headers,timeout=(10,25));response.raise_for_status();check=response.json()
            solution=byse_pow.solve(check['pow_nonce'],check['pow_difficulty'],progress=progress,timeout=240)
            response=session.post(api+'captcha/verify',json={'fingerprint':fingerprint,'pow_token':check['pow_token'],'solution':solution},headers=headers,timeout=(10,25));response.raise_for_status();verified=response.json()
            if verified.get('status')!='ok' or not verified.get('token'):raise ValueError('Автоматичната проверка на Byse не беше приета.')
            token=verified['token'];expires=time.time()+min(verified.get('expires_in',600),600)
            try:
                raw=unb64(fingerprint['token'].split('.')[0]);expires=min(expires,json.loads(raw).get('exp',expires))
            except (ValueError,TypeError):pass
            cached={'fingerprint':fingerprint,'captcha':token,'expires':expires};write_cache(cache_directory,key,cached)
        response=session.post(api+'playback',json={'fingerprint':fingerprint},headers=dict(headers,**{'X-Captcha-Token':token}),timeout=(10,25))
        if response.status_code in (401,403,428) and attempt==0:
            cached={};continue
        response.raise_for_status();data=decrypt_playback(response.json());sources=data.get('sources',[])
        if not sources:raise ValueError('Byse не върна достъпно видео.')
        source=max(sources,key=lambda x:int(x.get('height') or 0));video=urljoin(frame,source.get('url') or source.get('file',''))
        return play_url(session,video,origin+'/'),caption(data.get('tracks'),frame)
    raise ValueError('Byse отказа достъп до плейъра.')
