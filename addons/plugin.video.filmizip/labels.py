import re

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
