import json
import re
from urllib.parse import urljoin, urlencode, urlsplit, parse_qsl, urlunsplit
from bs4 import BeautifulSoup
BASE='https://filmi9.com/'
API='https://cdn.filmi9.com'

def flight_records(html):
    """Decode public Next.js data without executing website JavaScript."""
    chunks=[]
    for script in BeautifulSoup(html,'html.parser').select('script'):
        match=re.search(r'self\.__next_f\.push\((\[.*\])\)',script.string or '',re.S)
        if match:
            try:
                payload=json.loads(match[1])
                if len(payload)>1 and isinstance(payload[1],str):chunks.append(payload[1])
            except (ValueError,TypeError):pass
    stream=''.join(chunks).encode('utf-8');records={};position=0
    while position<len(stream):
        if stream[position:position+1]==b'\n':position+=1;continue
        colon=stream.find(b':',position)
        if colon<0:break
        key=stream[position:colon].decode('ascii',errors='ignore');start=colon+1
        if stream[start:start+1]==b'T':
            comma=stream.find(b',',start)
            try:length=int(stream[start+1:comma],16)
            except ValueError:break
            records[key]=stream[comma+1:comma+1+length].decode('utf-8',errors='replace');position=comma+1+length
        else:
            end=stream.find(b'\n',start)
            if end<0:end=len(stream)
            try:records[key]=json.loads(stream[start:end].decode('utf-8',errors='replace'))
            except ValueError:pass
            position=end+1
    return records

def objects(html):
    records=flight_records(html)
    def resolve(value,depth=0):
        if depth>15:return value
        if isinstance(value,str) and value.startswith('$') and value[1:] in records:return resolve(records[value[1:]],depth+1)
        if isinstance(value,dict):return {k:resolve(v,depth+1) for k,v in value.items()}
        if isinstance(value,list):return [resolve(v,depth+1) for v in value]
        return value
    def walk(value):
        if isinstance(value,dict):
            yield value
            for child in value.values():yield from walk(child)
        elif isinstance(value,list):
            for child in value:yield from walk(child)
    for value in records.values():yield from walk(resolve(value))

def movies(html):
    result=[];seen=set()
    for value in objects(html):
        if value.get('_id') and value.get('title') and value.get('slug') and value.get('type') in ('movie','series'):
            if value['_id'] not in seen:seen.add(value['_id']);result.append(value)
    return result

def catalogue_url(route, genre_id=''):
    path=urlsplit(route).path
    params=dict(page=1,limit=24,sort='-createdAt')
    if path=='/seriali':params['type']='series'
    elif path=='/filmi/bg-audio':params.update(isBgAudio='true',sort='-year,-createdAt,-rating')
    elif path=='/trending':params.update(type='movie',sort='-views')
    elif path.startswith('/genre/'):
        if not genre_id:return route
        params['genres']=genre_id
    else:params['type']='movie'
    return API+'/movies/?'+urlencode(params)


def categories(html):
    result=[];seen=set()
    ids={value['slug']:value['_id'] for value in objects(html) if value.get('_id') and value.get('slug') and value.get('name')}
    for a in BeautifulSoup(html,'html.parser').select('a[href]'):
        path=a['href'];name=a.get_text(' ',strip=True)
        if path in ('/filmi','/seriali','/filmi/bg-audio','/trending') or path.startswith('/genre/'):
            if path not in seen and name:
                seen.add(path)
                result.append((name,catalogue_url(urljoin(BASE,path),ids.get(path.split('/')[-1],''))))
    return result


def normalize(movie):
    title=str(movie.get('title') or '').strip();name=title.split('/',1)[-1].strip() if '/' in title else title
    year=int(movie.get('year') or 0)
    if not year:
        match=re.search(r'\((19\d{2}|20\d{2})\)\s*$',title)
        if match:year=int(match[1])
    name=re.sub(r'\s*\('+str(year)+r'\)\s*$', '',name).strip()
    route='serial/' if movie.get('type')=='series' else 'film/'
    countries = [str(c.get('name') or c.get('iso_3166_1') or '').strip() if isinstance(c,dict) else str(c).strip()
                 for c in movie.get('countries',[]) or []]
    countries = [country for country in countries if country]
    return dict(name=name,title=name,url=urljoin(BASE,route+movie['slug']),plot=movie.get('description') or '',
                icon=movie.get('movieImage') or '',fanart=movie.get('coverPhoto') or '',year=year,
                genres=[g['name'] if isinstance(g,dict) else str(g) for g in movie.get('genres',[])],
                countries=countries,
                duration=int(float(movie.get('movieLength') or 0)*60),originaltitle=movie.get('original_title') or title.split('/')[0].strip(),
                imdb=movie.get('imdb_id') or '',rating=float(movie.get('rating') or 0),media_type='tvshow' if movie.get('type')=='series' else 'movie')

def next_url(url):
    parts=urlsplit(url);params=dict(parse_qsl(parts.query));params['page']=str(int(params.get('page',1))+1)
    return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(params),''))

def listing(html,url):
    items=[normalize(m) for m in movies(html)]
    flags=[obj['hasMore'] for obj in objects(html) if isinstance(obj.get('hasMore'),bool)]
    has_more=any(flags) if flags else urlsplit(url).path!='/' and len(items)==24
    return items,next_url(url) if has_more else ''

def api_listing(data,url):
    raw=data.get('results',data.get('data',[])) if isinstance(data,dict) else data
    items=[normalize(m) for m in raw if isinstance(m,dict) and m.get('slug')]
    if not isinstance(data,dict):return items,next_url(url) if len(items)==24 else ''
    pagination=data.get('pagination',{})
    page=int(pagination.get('page',data.get('page',1)));pages=int(pagination.get('pages',data.get('totalPages',page)))
    return items,next_url(url) if page<pages else ''

def raw_movie(html,url):
    slug=urlsplit(url).path.rstrip('/').split('/')[-1]
    return next((m for m in movies(html) if m.get('slug')==slug),None)

def metadata(html,url):
    movie=raw_movie(html,url)
    if not movie:raise ValueError('Заглавието не е намерено във Filmi9.')
    return normalize(movie)

def source_rows(movie):
    result=[];seen=set()
    for source in movie.get('sources',[]):
        if not isinstance(source,dict):continue
        url=source.get('url','')
        if url.startswith(('https://','http://')) and url not in seen:seen.add(url);result.append((url,source.get('name') or urlsplit(url).hostname))
    video=movie.get('videoUrl') or ''
    if video.startswith(('https://','http://')) and video not in seen:result.append((video,urlsplit(video).hostname))
    tmdb=movie.get('tmdb_id')
    if movie.get('type')=='movie' and tmdb and str(tmdb).isdigit() and int(tmdb)>0:
        url='https://vsembed.su/embed/movie?'+urlencode(dict(tmdb=int(tmdb),ds_lang='bg'))
        if url not in seen and all(row[0]!=url for row in result):result.append((url,'Vsembed'))
    return result

def detail(html,url):
    movie=raw_movie(html,url)
    if not movie:raise ValueError('Заглавието не е намерено във Filmi9.')
    result=normalize(movie);result.update(sources=source_rows(movie),episodes=movie.get('episodes') or [],subtitles=movie.get('subtitles') or [])
    return result

def search_url(query):return API+'/movies/search/?'+urlencode(dict(term=query,page=1,limit=30))
