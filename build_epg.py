import csv, copy, gzip, os, pathlib, urllib.request, xml.etree.ElementTree as ET
from collections import defaultdict

ROOT=pathlib.Path(__file__).resolve().parent
URLS={'epg2':'https://raw.githubusercontent.com/ferteque/Curated-M3U-Repository/main/epg2.xml.gz', 'epg37':'https://raw.githubusercontent.com/ferteque/Curated-M3U-Repository/main/epg37.xml.gz'}

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'MyEPGBuilder/1.0'})
    with urllib.request.urlopen(req,timeout=240) as response:
        content=response.read(120*1024*1024+1)
    if len(content)>120*1024*1024: raise ValueError('Source too large')
    return gzip.decompress(content) if content[:2]==b'\x1f\x8b' else content

def main():
    # The M3U URL is stored only as a GitHub secret, never written to a public artifact.
    playlist_url=os.environ.get('PLAYLIST_URL','')
    if not playlist_url: raise RuntimeError('PLAYLIST_URL GitHub Actions secret is required')
    playlist=get(playlist_url).decode('utf-8-sig',errors='replace')
    playlist_ids=set()
    import re
    for line in playlist.splitlines():
        if line.startswith('#EXTINF:'):
            m=re.search(r'\btvg-id="([^"]*)"',line)
            if m and m.group(1):playlist_ids.add(m.group(1))
    print('Playlist parsed; distinct nonblank tvg-id values:',len(playlist_ids))
    mapping=defaultdict(lambda:defaultdict(set))
    with (ROOT/'matches.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            source=row['source'].lower()
            key='epg2' if 'epg2' in source else 'epg37' if 'epg37' in source else None
            if not key or not row['source_channel_id']:continue
            # Only publish IDs that the existing M3U actually uses. Blank IDs need a separately remapped playlist.
            target=row['original_tvg_id']
            if target and target in playlist_ids:
                mapping[key][row['source_channel_id']].add(target)
    channels={}; programmes=[]
    for key,url in URLS.items():
        print('Downloading',key)
        root=ET.fromstring(get(url))
        for element in root:
            if element.tag.rsplit('}',1)[-1]=='channel':
                for target in mapping[key].get(element.get('id',''),()):
                    if target not in channels:
                        clone=copy.deepcopy(element);clone.set('id',target);channels[target]=clone
        count=0
        for element in root:
            if element.tag.rsplit('}',1)[-1]=='programme':
                for target in mapping[key].get(element.get('channel',''),()):
                    if target in channels:
                        clone=copy.deepcopy(element);clone.set('channel',target);programmes.append(clone);count+=1
        print(key,'programmes selected:',count)
    if not channels or not programmes:raise RuntimeError('No matched programmes; refusing to publish empty guide')
    out=ET.Element('tv',{'generator-info-name':'My-EPG'})
    out.extend(channels.values());out.extend(programmes)
    dest=ROOT/'site';dest.mkdir(exist_ok=True)
    with gzip.open(dest/'epg.xml.gz','wb',compresslevel=6) as f:
        ET.ElementTree(out).write(f,encoding='utf-8',xml_declaration=True)
    (dest/'.nojekyll').touch()
    print('Built',len(channels),'channels and',len(programmes),'programmes')
if __name__=='__main__':main()
