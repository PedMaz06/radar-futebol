#!/usr/bin/env python3
"""Coleta moderada de links dos sites institucionais do piloto.

Não faz checagem factual nem garante cobertura; apenas identifica candidatos
pelas manchetes de domínios autorizados. Sem conta X e sem scraping do ge/ESPN.
Variáveis SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY são segredos do Actions.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, urlencode
from urllib.request import Request, urlopen
import hashlib
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
SOURCES = json.loads((BASE/'pilot_sources.json').read_text(encoding='utf-8'))
NOW = lambda: datetime.now(timezone.utc)
CAP_BYTES = 1_500_000
TIMEOUT = 9
UA = 'RadarFutebol/6.0 (leitor editorial; links de fontes institucionais; contato via repositorio)'

def norm(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()

RULES = [
  ('lesao', r'\b(lesao|lesionado|lesionados|boletim medico|parte medico|injury|injured|injuries|injury update|medical update|surgery|cirurgia|operado|fitness update|contusao|desfalque|fractura|fracture)\b'),
  ('renovacao', r'\b(renova|renovou|renovado|renovacao|renews|renewed|extends contract|extension|new contract|new deal|contract extension|renueva|prolonga)\b'),
  ('contratacao', r'\b(contratado|contratacao|contrata|novo reforco|reforco anunciado|new signing|signs for|signs with|signed from|joins the club|welcome to|has joined|signing confirmed|fichaje oficial|fichado)\b'),
  ('tecnico', r'\b(novo tecnico|novo treinador|demissao do tecnico|demissao de treinador|treinador demitido|tecnico demitido|desligamento de treinador|new head coach|new manager|appointed head coach|appoints manager|part ways with|sacked|dismissed|manager leaves|head coach leaves|nuevo entrenador)\b'),
  ('convocacao', r'\b(convocacao|convocado|convocados|convocada|convocadas|desconvocado|called up|call up|squad named|squad announced|named in the squad|lista de convocados|convocados para)\b'),
  ('saida', r'\b(saida de|deixa o clube|deixou o clube|rescisao|departed|departure|departs|leaves the club|has left|emprestado|cedido por emprestimo|loan completed|transferencia concretizada)\b'),
  ('suspensao', r'\b(suspensao|suspenso|suspended|suspension|banned)\b'),
  ('comunicado', r'\b(comunicado oficial|nota oficial|official statement|club statement|esclarecimento oficial)\b'),
]
NEGATIVE = re.compile(r'\b(rumou?r|boato|speculat|rumour|rumor|reportedly|would sign|could sign|may sign|might sign|interesse em|negociacao|negocia com|linked with|possible signing|pode contratar|pode ser contratado|pode deixar|may leave|could leave|planeja contratar|expected to|close to signing|set to sign|quer contratar|alvo do|sondagem|acertaria)\b', re.I)
OTHER_SCOPE = re.compile(r'\b(feminino|feminina|women|woman|ladies|femenino|femenina|femminile|frauen|academy|youth|under[- ]?1[3579]|under[- ]?2[013]|u[- ]?1[3579]|u[- ]?2[013]|sub[- ]?1[3579]|sub[- ]?2[013]|categoria de base|categorias de base|juniores|futsal|basquete|basketball|volei|handebol)\b', re.I)
RULES = [(cat,re.compile(exp,re.I)) for cat,exp in RULES]
PRIORITY = dict(tecnico=5,convocacao=5,lesao=4,contratacao=4,renovacao=4,saida=4,suspensao=4,comunicado=3)

def classify(title):
    txt=norm(title)
    if NEGATIVE.search(txt) or OTHER_SCOPE.search(txt):return None
    for cat,pattern in RULES:
        if pattern.search(txt):return cat
    return None

def allowed_url(url, domain):
    try:
        u=urlsplit(url)
        h=(u.hostname or '').lower().rstrip('.')
        d=domain.lower().rstrip('.')
        return (u.scheme=='https' and (h==d or h.endswith('.'+d))
                and not u.username and not u.password and u.port in (None,443))
    except (TypeError,ValueError):return False

def looks_like_article(url):
    path=urlsplit(url).path.lower().rstrip('/')
    if len(path)<12 or re.search(r'\.(?:png|jpeg|jpg|svg|gif|webp|pdf|mp4|css|js)$',path):return False
    if re.search(r'/(?:shop|store|tickets|calendar|fixture|match|search|players|squad|teams|privacy|login|category|tag)/',path+'/'):return False
    return bool(re.search(r'/(?:news|noticias?|noticias-de|comunicad|sele[cç][aã]o-brasileira|articles|stories|actualites|notizie|futebol)/',path+'/'))

class Links(HTMLParser):
    def __init__(self, base, domain):
        super().__init__(convert_charrefs=True)
        self.base,self.domain=base,domain;self.active=None;self.rows=[];self.in_anchor=False
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='a':
            dest=urljoin(self.base,d.get('href') or '')
            self.active={'url':dest,'chunks':[], 'hint':d.get('aria-label') or d.get('title') or ''} if allowed_url(dest,self.domain) else None
    def handle_data(self,data):
        if self.active:self.active['chunks'].append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.active:
            self.rows.append({'url':self.active['url'],'title':' '.join(''.join(self.active['chunks']).split()) or self.active['hint']})
            self.active=None

def normalize_date(raw):
    if not raw:return None
    raw=str(raw).strip()
    try:date=datetime.fromisoformat(raw.replace('Z','+00:00'))
    except ValueError:
        try:date=parsedate_to_datetime(raw)
        except (ValueError,IndexError,TypeError):return None
    if date.tzinfo is None:date=date.replace(tzinfo=timezone.utc)
    date=date.astimezone(timezone.utc)
    if not datetime(2000,1,1,tzinfo=timezone.utc)<=date<=NOW()+timedelta(days=1):return None
    return date

def extract_pubdate(body):
    s=body.decode('utf-8','replace')
    # JSON-LD datePublished, OG article:published_time, or <time datetime> in an article
    for expression in [
      r'"datePublished"\s*:\s*"([^"]+)"',
      r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|datePublished|publishdate|date)["\'][^>]+content=["\']([^"\']+)["\']',
      r'<time[^>]+datetime=["\']([^"\']+)["\']',
    ]:
        m=re.search(expression,s,re.I)
        if m:
            d=normalize_date(m.group(1))
            if d:return d
    return None

def parse_rss(body,base,domain):
    root=ET.fromstring(body)
    out=[]
    for item in root.iter():
        if item.tag.rsplit('}',1)[-1] not in ('item','entry'):continue
        def val(name):
            for n in item:
                if n.tag.rsplit('}',1)[-1]==name:return ''.join(n.itertext()).strip() or n.attrib.get('href','')
            return ''
        url=urljoin(base,val('link'))
        if allowed_url(url,domain):out.append({'title':unescape(re.sub('<[^>]*>','',val('title'))),'url':url,'published_at':normalize_date(val('pubDate') or val('published') or val('updated'))})
    return out

def download(url,domain):
    req=Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/rss+xml,application/atom+xml;q=0.7,*/*;q=0.3'})
    with urlopen(req,timeout=TIMEOUT) as r:
        final=r.geturl()
        if not allowed_url(final,domain):raise ValueError('Redirecionamento para endereço não autorizado')
        body=r.read(CAP_BYTES+1)
        if len(body)>CAP_BYTES:raise ValueError('Página acima do limite de leitura')
        return body,final,r.headers.get('Content-Type','')

def collect_source(source,fetch=download, now=None):
    now=now or NOW()
    checked_at=now.isoformat()
    result={'id':source['id'],'checked_at':checked_at,'ok':False,'error':None,'seen_links':0,'relevant_links':0,'articles':[]}
    domain=source['domain']
    if not allowed_url(source['url'],domain):
        result['error']='Página inicial fora do domínio oficial autorizado';return result
    try:
        body,url,ctype=fetch(source['url'],domain)
        if 'xml' in ctype or body.lstrip().startswith((b'<?xml',b'<rss',b'<feed')):
            links=parse_rss(body,url,domain)
        else:
            p=Links(url,domain);p.feed(body.decode('utf-8','replace'));links=p.rows
        result['seen_links']=len(links)
        seen=set()
        for link in links:
            dest=urlunsplit(urlsplit(link['url'])._replace(fragment=''))
            title=' '.join(unescape(link.get('title','')).split()).strip()
            if dest in seen or not allowed_url(dest,domain) or not looks_like_article(dest) or len(title)<13 or len(title)>180:continue
            seen.add(dest)
            cat=classify(title)
            if not cat:continue
            result['relevant_links']+=1
            date=link.get('published_at')
            if date is None and len(result['articles'])<6:
                try:article_body,_,_=fetch(dest,domain);date=extract_pubdate(article_body)
                except Exception:pass
            # Publicações antigas não devem ressurgir como alertas novos.
            if date is not None and date < now-timedelta(days=21):continue
            identifier=hashlib.sha256(dest.encode('utf-8')).hexdigest()[:20]
            result['articles'].append({'id':identifier,'entity_id':source['id'],'title':title,'url':dest,'category':cat,
             'status':'official_domain','source':source['name']+' · site oficial','published_at':date.isoformat() if date else None,
             'priority':PRIORITY.get(cat,3),'first_seen':checked_at})
            if len(result['articles'])>=10:break
        result['ok']=True
    except Exception as e:result['error']=str(e)[:180]
    return result

def supabase(path,method='GET',data=None,params=None,prefer=''):
    base=os.environ['SUPABASE_URL'].strip().rstrip('/')
    secret=os.environ['SUPABASE_SERVICE_ROLE_KEY'].strip()
    if not re.fullmatch(r'https://[a-z0-9-]+\.supabase\.co',base):raise ValueError('SUPABASE_URL inválida')
    if not secret or secret.startswith('COLE_'):raise ValueError('Credencial da API não foi configurada')
    url=base+'/rest/v1/'+path+('?' + urlencode(params) if params else '')
    hdr={'apikey':secret,'Authorization':'Bearer '+secret,'Content-Type':'application/json'}
    if prefer:hdr['Prefer']=prefer
    body=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
    req=Request(url,data=body,headers=hdr,method=method)
    with urlopen(req,timeout=20) as r:return r.read(10000).decode('utf-8','replace')

def run(save=True):
    print('Coleta do Radar Futebol: sites oficiais, '+str(len(SOURCES))+' fontes')
    results=[]
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures={executor.submit(collect_source,s):s for s in SOURCES}
        for f in as_completed(futures):
            r=f.result();results.append(r)
            print(f"{r['id']}: {'OK' if r['ok'] else 'FALHA'}; {r['seen_links']} links; {len(r['articles'])} candidatos; {r['error'] or ''}")
    if save:
        for r in results:
            if r['articles']:
                # Somente inserção. first_seen não pode ser alterado por reconsultas.
                supabase('radar_articles','POST',r['articles'],{'on_conflict':'id'},'resolution=ignore-duplicates,return=minimal')
            check={k:r[k] for k in ('id','checked_at','ok','error','seen_links','relevant_links')}
            supabase('radar_sources','POST',[check],{'on_conflict':'id'},'resolution=merge-duplicates,return=minimal')
        cutoff=(NOW()-timedelta(days=30)).isoformat()
        supabase('radar_articles','DELETE',None,{'first_seen':'lt.'+cutoff},'return=minimal')
    print('Concluído: '+str(sum(r['ok'] for r in results))+' fontes responderam, '+str(sum(len(r['articles']) for r in results))+' títulos candidatos encontrados')
    return results

if __name__=='__main__':
    if '--dry-run' not in sys.argv and not all(os.environ.get(x) for x in ('SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY')):
        sys.exit('Faltam SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY. Para prévia: python collect.py --dry-run')
    run(save='--dry-run' not in sys.argv)
