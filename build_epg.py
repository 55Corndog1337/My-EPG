"""Build an XMLTV guide and a PRIVATE, matching M3U playlist.

Source playlist is downloaded from the PLAYLIST_URL Actions secret. Never publish
playlist.m3u: streaming URLs may contain authentication credentials.
"""
import csv
import gzip
import io
import os
from pathlib import Path
import re
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent
SOURCES = {
    'epg2': 'https://raw.githubusercontent.com/ferteque/Curated-M3U-Repository/main/epg2.xml.gz',
    'epg37': 'https://raw.githubusercontent.com/ferteque/Curated-M3U-Repository/main/epg37.xml.gz',
}
ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'My-EPG/2.0'})
    with urllib.request.urlopen(request, timeout=240) as response:
        data = response.read(160 * 1024 * 1024 + 1)
    if len(data) > 160 * 1024 * 1024:
        raise ValueError('Download exceeds 160 MiB')
    return gzip.decompress(data) if data.startswith(b'\x1f\x8b') else data


def normalize(s):
    return re.sub(r'[^a-z0-9]+', '', s.casefold())


def read_m3u(raw):
    lines = raw.decode('utf-8-sig', 'replace').splitlines()
    if not lines or not lines[0].startswith('#EXTM3U'):
        raise ValueError('Invalid M3U playlist')
    items = []
    pending = None
    for line in lines[1:]:
        if line.startswith('#EXTINF:'):
            pending = line
        elif pending and line.strip() and not line.startswith('#'):
            meta, _, name = pending.partition(',')
            attrs = dict(ATTR.findall(meta))
            items.append({'extinf': pending, 'url': line, 'name': name.strip(),
                          'group': attrs.get('group-title', ''), 'id': attrs.get('tvg-id', '')})
            pending = None
    return lines[0], items


def main():
    playlist_url = os.environ.get('PLAYLIST_URL', '').strip()
    if not playlist_url:
        raise RuntimeError('Missing GitHub Actions secret PLAYLIST_URL')
    header, items = read_m3u(download(playlist_url))
    print('Playlist entries:', len(items))
    rows = list(csv.DictReader((ROOT / 'matches.csv').open(encoding='utf-8-sig', newline='')))
    by_pair = defaultdict(list)
    by_id = defaultdict(list)
    by_name = defaultdict(list)
    for row in rows:
        if not row['source_channel_id'] or not row['output_tvg_id']:
            continue
        by_pair[(normalize(row['group']), normalize(row['playlist_channel']))].append(row)
        by_name[normalize(row['playlist_channel'])].append(row)
        if row['original_tvg_id']:
            by_id[row['original_tvg_id'].casefold()].append(row)

    assigned = []
    counts = Counter()
    for item in items:
        # Exact group+name is safest; original ID is a fallback when uniquely mapped.
        candidates = by_pair.get((normalize(item['group']), normalize(item['name'])), [])
        method = 'group+name'
        if not candidates:
            candidates = by_name.get(normalize(item['name']), [])
            method = 'name'
        if not candidates and item['id']:
            candidates = by_id.get(item['id'].casefold(), [])
            method = 'original id'
        distinct = {(r['source'], r['source_channel_id'], r['output_tvg_id']) for r in candidates}
        if len(distinct) == 1:
            row = candidates[0]
            src = 'epg2' if 'epg2' in row['source'].lower() else 'epg37'
            assigned.append((item, src, row['source_channel_id'], row['output_tvg_id']))
            counts[method] += 1
        else:
            assigned.append((item, None, None, None))
            counts['ambiguous' if distinct else 'unmatched'] += 1
    print('Mapping methods:', dict(counts))

    # Preserve original tvg-id for unmatched channels; assign known custom IDs to
    # matched channels. Multiple playlist variants can legitimately share one ID.
    private = ROOT / 'private'; private.mkdir(exist_ok=True)
    with (private / 'playlist.m3u').open('w', encoding='utf-8', newline='\n') as output:
        # Do not keep source url-tvg, which would override our new guide in some players.
        output.write('#EXTM3U\n')
        for item, src, channel, target in assigned:
            extinf = item['extinf']
            if target:
                if re.search(r'\btvg-id="[^"]*"', extinf):
                    extinf = re.sub(r'\btvg-id="[^"]*"', f'tvg-id="{target}"', extinf, count=1)
                else:
                    extinf = extinf.replace(',', f' tvg-id="{target}",', 1)
            output.write(extinf + '\n' + item['url'] + '\n')

    selected = defaultdict(lambda: defaultdict(set))
    for _, src, channel, target in assigned:
        if src:
            selected[src][channel].add(target)
    channels = {}
    programs = []
    for source, url in SOURCES.items():
        print('Downloading', source)
        xml = download(url)
        # iterparse allows freeing XML elements after selection, limiting memory use.
        stream = io.BytesIO(xml)
        for event, elem in ET.iterparse(stream, events=('end',)):
            tag = elem.tag.rsplit('}', 1)[-1]
            if tag == 'channel':
                for target in selected[source].get(elem.get('id'), ()):
                    if target not in channels:
                        clone = ET.fromstring(ET.tostring(elem, encoding='utf-8'))
                        clone.set('id', target)
                        channels[target] = clone
                elem.clear()
            elif tag == 'programme':
                for target in selected[source].get(elem.get('channel'), ()):
                    if target in channels:
                        clone = ET.fromstring(ET.tostring(elem, encoding='utf-8'))
                        clone.set('channel', target)
                        programs.append(clone)
                elem.clear()
        print('Processed', source)
    if not channels or not programs:
        raise RuntimeError('No channels or programmes matched; refusing to publish')
    root = ET.Element('tv', {'generator-info-name': 'My-EPG'})
    root.extend(channels.values())
    root.extend(programs)
    site = ROOT / 'site'; site.mkdir(exist_ok=True)
    with gzip.open(site / 'epg.xml.gz', 'wb', compresslevel=6) as out:
        ET.ElementTree(root).write(out, encoding='utf-8', xml_declaration=True)
    (site / '.nojekyll').touch()
    (site / 'index.html').write_text(
    '<h1>My EPG</h1>'
    '<p><a href="epg.xml.gz">Download EPG</a></p>',
    encoding='utf-8'
)
print('Site files:', [p.name for p in site.iterdir()])
    print('Published:', len(channels), 'channels,', len(programs), 'programmes')
    print('PRIVATE playlist:', len(items), 'entries')
    print('Note: download the private playlist from the Actions artifact, never Pages')


if __name__ == '__main__':
    main()
