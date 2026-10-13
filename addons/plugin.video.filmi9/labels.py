import re
from urllib.parse import parse_qsl, urlsplit

def movie_year(data):
    try:year=int(data.get('year') or 0)
    except (ValueError,TypeError):year=0
    if year:return year
    for key in ('name','title','originaltitle'):
        match=re.search(r'\((19\d{2}|20\d{2})\)\s*$',str(data.get(key) or ''))
        if match:return int(match[1])
    return 0

def movie_label(name, year):
    title=str(name or '').strip()
    try:year=int(year or 0)
    except (ValueError,TypeError):year=0
    suffix=' ('+str(year)+')'
    return title if not year or title.endswith(suffix) else title+suffix


def source_label(name, year, source):
    title=movie_label(name,year)
    return title+' — '+source if source else title


def episode_metadata(data, episode, source_url='', page_url=''):
    """Expose series and episode fields to Kodi subtitle providers."""
    if not episode:
        return data
    result=dict(data)
    source_query=dict(parse_qsl(urlsplit(source_url).query))
    season=source_query.get('season') or source_query.get('s')
    episode_number=source_query.get('episode') or source_query.get('e')
    raw=str(episode)
    match=re.search(r'(?i)(?:s(\d{1,2})[ ._-]*e(\d{1,3})|(\d{1,2})x(\d{1,3}))',raw)
    if match:
        season=season or match.group(1) or match.group(3)
        episode_number=episode_number or match.group(2) or match.group(4)
    elif not episode_number and raw.isdigit():
        episode_number=raw
    if not season:
        for value in (page_url,data.get('title',''),data.get('originaltitle','')):
            match=re.search(r'(?i)(?:season|series|сезон)[^0-9]{0,4}(\d{1,2})',str(value or ''))
            if match:
                season=match.group(1)
                break
            match=re.search(r'(?i)(?:^|[/._ -])s(\d{1,2})(?:$|[/._ -])',str(value or ''))
            if match:
                season=match.group(1)
                break
    show_title=str(data.get('originaltitle') or data.get('title') or data.get('name') or '').strip()
    show_title=re.sub(r'(?i)\s*[-–—:]?\s*(?:season|series|сезон)\s*\d+\s*$','',show_title).strip()
    if show_title:
        result['originaltitle']=show_title
        result['tvshowtitle']=show_title
    result['media_type']='episode'
    for key,value in (('season',season),('episode',episode_number)):
        try:
            if value is not None and str(value).isdigit():result[key]=int(value)
        except (ValueError,TypeError):
            pass
    return result
