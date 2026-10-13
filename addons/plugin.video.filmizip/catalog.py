import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from parser import metadata

class Catalog:
    def __init__(self, directory, agent):
        self.directory = directory
        self.agent = agent
        self.local = threading.local()
        self.failures = []
        os.makedirs(directory, exist_ok=True)

    def filename(self, url):
        return os.path.join(self.directory, hashlib.sha256(url.encode()).hexdigest() + '.json')

    def read(self, url):
        try:
            with open(self.filename(url), encoding='utf-8') as f:
                data = json.load(f)
            if data.get('url') == url and time.time() - data['time'] < 86400:
                return data['metadata']
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def write(self, url, data):
        path = self.filename(url)
        temp = path + '.tmp-' + str(threading.get_ident())
        with open(temp,'w',encoding='utf-8') as f:
            json.dump(dict(url=url,time=time.time(),metadata=data),f,ensure_ascii=False)
        os.replace(temp,path)

    def fetch(self, url):
        cached = self.read(url)
        if cached is not None:
            return cached
        if not hasattr(self.local,'session'):
            self.local.session = requests.Session()
            self.local.session.headers['User-Agent'] = self.agent
        response = self.local.session.get(url,timeout=(5,12))
        response.raise_for_status()
        response.encoding = 'utf-8'
        data = metadata(response.text,url)
        if not data['plot'] and not data['title']:
            raise ValueError('Няма достъпни метаданни.')
        self.write(url,data)
        return data

    def enrich(self, items, progress=None):
        self.failures = []
        failed = []
        def apply(item, data):
            for key in ('plot','icon','year','genres','fanart','duration','originaltitle','imdb'):
                if data.get(key):item[key]=data[key]
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs={pool.submit(self.fetch,item['url']):item for item in items}
            for count,future in enumerate(as_completed(jobs),1):
                item=jobs[future]
                try:
                    apply(item,future.result())
                except Exception as error:
                    failed.append((item,error))
                if progress:progress(int(count*90/max(1,len(items))))
        # Retry a small number of transient failures with lower concurrency.
        if failed and len(failed) <= 24 and len(failed) <= max(1,len(items)//2):
            time.sleep(.4)
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs={pool.submit(self.fetch,item['url']):item for item,error in failed}
                failed=[]
                for count,future in enumerate(as_completed(jobs),1):
                    item=jobs[future]
                    try:
                        apply(item,future.result())
                    except Exception as error:
                        failed.append((item,error))
                    if progress:progress(90+int(count*10/max(1,len(jobs))))
        self.failures=[(item['url'],str(error)) for item,error in failed]
        if progress:progress(100)
        return items
