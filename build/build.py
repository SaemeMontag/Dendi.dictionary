"""Сборка сайта «Словарь денди» из Google-документа.

Использование:
  python3 build.py <документ> <страница.html> <выход.html> [--site <папка> --base <URL>]

<документ> — папка хранилища Obsidian (читается только, см. vault.py) либо выгрузка
  Google-документа: JSON-результат Google Drive (download_file_content) или файл .html/.txt. Лучше HTML (exportMimeType "text/html"): из него берутся ссылки
  на страницы источников. Из текстовой выгрузки сайт тоже собирается, но без этих ссылок.
<страница.html> — страница-фрагмент для claude.ai (данные в ней заменяются) или шаблон с __DATA__.
--site: дополнительно собрать полноценный сайт для GitHub Pages в <папке>.

На сайт не попадает «Редакторский раздел» (от его заголовка до «Введения для читателя»).

Код выхода: 0 — собрано (STATUS CHANGED или UNCHANGED); 2 — документ не прошёл проверки
(STATUS FAILED), ничего не записано, публиковать нельзя.
"""
import re, json, sys, os, base64, html as htmlmod, urllib.parse, datetime

# ---------- ввод ----------

args = sys.argv[1:]
site_dir = base_url = None
if '--site' in args:
    i = args.index('--site'); site_dir = args[i + 1]; del args[i:i + 2]
if '--base' in args:
    i = args.index('--base'); base_url = args[i + 1].rstrip('/') + '/'; del args[i:i + 2]
src_path, page_path, out = args[0], args[1], args[2]


def fail_now(msg):
    print('STATUS FAILED'); print(' -', msg); sys.exit(2)


def load_raw(path):
    raw = open(path, encoding='utf-8').read()
    if raw.lstrip().startswith('{'):
        d = json.loads(raw); c = d.get('content', '')
        try:
            return base64.b64decode(c, validate=True).decode('utf-8')
        except Exception:
            return c
    return raw


def clean_url(u):
    u = htmlmod.unescape(u)
    m = re.match(r'https?://www\.google\.com/url\?q=([^&]+)', u)
    return urllib.parse.unquote(m[1]) if m else u


def strip_tags(s):
    return htmlmod.unescape(re.sub(r'<[^>]+>', '', s)).replace('\xa0', ' ')


LINES = []          # [(текст, ссылка всей строки или '')]
EXTRA = {}
if os.path.isdir(src_path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import vault
    try:
        LINES, EXTRA = vault.load(src_path)
    except vault.VaultError as err:
        fail_now(f'хранилище: {err}')
    raw = ''
else:
    raw = load_raw(src_path)
if not LINES and re.search(r'<(p|h[1-6])\b', raw[:200000], re.I):
    body = re.sub(r'(?is)<(style|script|head)\b.*?</\1>', '', raw)
    for _, inner in re.findall(r'(?is)<(p|h[1-6]|li)\b[^>]*>(.*?)</\1>', body):
        text = re.sub(r'\s+', ' ', strip_tags(inner)).strip()
        links = [(re.sub(r'\s+', ' ', strip_tags(t)).strip(), clean_url(h))
                 for h, t in re.findall(r'(?is)<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', inner)]
        url = next((u for t, u in links if t == text and u.startswith('http')), '')
        LINES.append((text, url))
elif not LINES:
    for l in raw.replace('\r', '').split('\n'):
        LINES.append((re.sub(r'\s+', ' ', l.replace('﻿', '')).strip(), ''))
LINES = [(t.replace('﻿', ''), u) for t, u in LINES]
L = [t for t, _ in LINES]
URL = [u if 'docs.google.com/document' not in u else '' for _, u in LINES]
problems = []
warnings = []


def find(pred, start=0, name=''):
    for i in range(start, len(L)):
        if pred(L[i]):
            return i
    fail_now(f'не найден раздел «{name}»')


# ---------- разделы ----------

i_edit = find(lambda l: l.startswith('Редакторский раздел'), 0, 'Редакторский раздел')
i_intro = find(lambda l: l == 'Введение для читателя', i_edit, 'Введение для читателя')
i_gram = find(lambda l: l.startswith('Грамматика:'), i_intro, 'Грамматика')
i_dict = find(lambda l: l == 'Словарные статьи', i_gram, 'Словарные статьи')
i_src = find(lambda l: l == 'Источники и границы их использования', i_dict, 'Источники и границы их использования')

meta = {'title': L[0], 'intro': [l for l in L[i_intro + 1:i_gram] if l]}

SRC_CODE = r'(?:NT18|NT95|AL\d+|COV|CAL|CFA|ANT|SM19|T68/72|N78|N89|G88|GYK|H|AT|AZ|RST)'
REF_RE = re.compile(r'^' + SRC_CODE + r'\b[ ,:]')
HEAD_RE = re.compile(r'^(\d+)\. (.+)$')
ROMAN_RE = re.compile(r'^([IVXLC]+)\. (.+)$')


def ref(i):
    return {'t': L[i], 'u': URL[i]}


# грамматика
grammar = {'title': L[i_gram], 'intro': [], 'rules': []}
cur = None
for i in range(i_gram + 1, i_dict):
    l = L[i]
    if not l: continue
    m = HEAD_RE.match(l)
    if m and not REF_RE.match(l):
        cur = {'n': int(m[1]), 'title': m[2], 'paras': [], 'refs': []}; grammar['rules'].append(cur)
    elif cur is None:
        grammar['intro'].append(l)
    elif REF_RE.match(l):
        cur['refs'].append(ref(i))
    else:
        cur['paras'].append(l)

# ---------- словарные статьи ----------

KIND_EXTRA = 'Дополнительная лексика и грамматика.'
SW_RE = re.compile(r'^Сводеш № (\d+)$')
FULLN_RE = re.compile(r'^Полных примеров для этого варианта: (\d+)\.$')
EX_RE = re.compile(r'^Пример (\d+) \((П\d+)\) — (.+)$')
LINKED_RE = re.compile(r'^Пример по ссылке \((П\d+)\)$')
LINKED_HEAD = 'Полные примеры по ссылкам исходного разбора'
EX_FIELDS = [('Денди: ', 'dendi'), ('Источник: ', 'source'), ('Опубликованный русский перевод: ', 'pub'),
             ('Авторский дословный перевод: ', 'lit'), ('Разбор по словам: ', 'parse'), ('Примечание: ', 'note')]


def is_head(i):
    return bool(HEAD_RE.match(L[i])) and i + 1 < len(L) and (bool(SW_RE.match(L[i + 1])) or L[i + 1] == KIND_EXTRA)


def letter_of(title):
    for ch in title:
        if ch.isalpha():
            return ch.upper().replace('Ё', 'Е')
    return '#'


def fill_ex(ex, l, i):
    if l == 'Синодальный перевод — русский параллельный текст':
        ex['rst'] = True; return True
    for pre, key in EX_FIELDS:
        if l.startswith(pre) and key not in ex:
            ex[key] = l[len(pre):]
            if key == 'source': ex['source_url'] = URL[i]
            return True
    return False


def parse_entry(a, b):
    m = HEAD_RE.match(L[a])
    e = {'n': int(m[1]), 'title': m[2], 'letter': letter_of(m[2]), 'variants': [], 'extra_refs': [], 'linked': [], 'stray': []}
    sw = SW_RE.match(L[a + 1])
    if sw: e.update(kind='swadesh', swadesh=int(sw[1]))
    else: e['kind'] = 'extra'
    var = ex = None
    pending = []          # пояснение между примерами — относится к следующему примеру
    mode = 'pre'          # pre | var | ex | refs | xrefs
    for i in range(a + 2, b):
        l = L[i]
        if not l: continue
        if l.startswith('Значение и употребление: ') and 'meaning' not in e:
            e['meaning'] = l[len('Значение и употребление: '):]; continue
        if l.startswith('Практическое написание не установлено'):
            e['unestablished'] = l; continue
        if l.startswith('Научный указатель: '):
            e['sci'] = l[len('Научный указатель: '):]; mode = 'post'; continue
        if l == 'Дополнительные источниковые привязки:':
            mode = 'xrefs'; continue
        if l == LINKED_HEAD:
            if pending and var is not None: var['notes'] += pending; pending = []
            mode = 'linked'; ex = None; continue
        if l.startswith('Связанные примеры:'):
            e['related'] = l[len('Связанные примеры:'):].strip(); continue
        lm = LINKED_RE.match(l)
        if lm:
            ex = {'k': len(e['linked']) + 1, 'pid': lm[1], 'head': '', 'rst': False}
            e['linked'].append(ex); mode = 'lex'; continue
        if mode == 'lex':
            if not fill_ex(ex, l, i): e['stray'].append(l)
            continue
        if mode == 'linked':
            e['stray'].append(l); continue
        rm = ROMAN_RE.match(l)
        if rm and mode not in ('ex',) or (rm and mode == 'ex' and ex and all(ex.get(k) for k in ('dendi', 'source', 'lit'))):
            if pending and var is not None: var['notes'] += pending; pending = []
            var = {'label': rm[1], 'form': rm[2], 'notes': [], 'full': None, 'status': '', 'examples': [], 'refs': []}
            e['variants'].append(var); ex = None; mode = 'var'; continue
        if mode == 'pre':
            if REF_RE.match(l) or EX_RE.match(l) or FULLN_RE.match(l):
                e['stray'].append(l); continue
            var = {'label': '', 'form': l, 'notes': [], 'full': None, 'status': '', 'examples': [], 'refs': []}
            e['variants'].append(var); mode = 'var'; continue
        if mode in ('var', 'ex'):
            fm = FULLN_RE.match(l)
            if fm and not var['examples']:
                var['full'] = int(fm[1]); continue
            if l.startswith('Полный пример с дословным разбором отсутствует'):
                var['status'] = l; continue
            em = EX_RE.match(l)
            if em:
                ex = {'k': int(em[1]), 'pid': em[2], 'head': em[3], 'rst': False}
                if pending: ex['lead'] = pending; pending = []
                var['examples'].append(ex); mode = 'ex'; continue
            if l == 'Источники формы и дополнительные контексты:':
                if pending: var['notes'] += pending; pending = []
                mode = 'refs'; ex = None; continue
            if mode == 'ex':
                if not fill_ex(ex, l, i):
                    if ex.get('lit') and ex.get('parse'): pending.append(l)
                    else: e['stray'].append(l)
                continue
            if not var['examples'] and not var['status']:
                var['notes'].append(l); continue
            e['stray'].append(l); continue
        if mode == 'refs':
            if REF_RE.match(l): var['refs'].append(ref(i)); continue
            em = EX_RE.match(l)
            if em and var is not None:
                warnings.append(f'статья {e["n"]} «{e["title"]}»: {em[2]} стоит после списка источников варианта; принят как пример этого варианта')
                ex = {'k': int(em[1]), 'pid': em[2], 'head': em[3], 'rst': False}
                var['examples'].append(ex); mode = 'ex'; continue
            e['stray'].append(l); continue
        if mode == 'xrefs':
            if REF_RE.match(l): e['extra_refs'].append(ref(i)); continue
            e['stray'].append(l); continue
        e['stray'].append(l)
    if pending: e['stray'] += pending
    return e


heads = [i for i in range(i_dict + 1, i_src) if is_head(i)]
for i in range(i_dict + 1, heads[0] if heads else i_src):
    if L[i]: problems.append(f'строка до первой статьи: {L[i][:70]}')
entries = [parse_entry(a, b) for a, b in zip(heads, heads[1:] + [i_src])]

# ---------- источники ----------

sources, rst = [], None
src_lines = [(L[i], URL[i]) for i in range(i_src + 1, len(L)) if L[i]]
j = 0
while j < len(src_lines):
    t, u = src_lines[j]
    nxt = src_lines[j + 1][0] if j + 1 < len(src_lines) else ''
    lab = src_lines[j + 2] if j + 2 < len(src_lines) else ('', '')
    if t.startswith('Опубликованный русский параллельный текст'):
        rst = {'title': t, 'desc': nxt, 'label': lab[0], 'url': lab[1]}; j += 3; continue
    if lab[0].startswith('Источник') or (lab[1] and len(lab[0]) < 60):
        sources.append({'code': t, 'desc': nxt, 'url': lab[1]}); j += 3
    else:
        sources.append({'code': t, 'desc': nxt, 'url': ''}); j += 2

data = {'meta': meta, 'grammar': grammar, 'entries': entries, 'sources': sources, 'rst': rst}
data.update(EXTRA)

# ---------- морфология русских слов (OpenCorpora через Az.js, см. build/vendor/az) ----------

def ru_vocab(d):
    words = set()
    def add(t):
        words.update(w.lower() for w in re.findall(r'[А-Яа-яЁё]+', t or ''))
    for e in d['entries']:
        add(re.sub(r'\(.*?\)', ' ', e['title']))
        for x in [x for v in e['variants'] for x in v['examples']] + e.get('linked', []):
            add(x.get('lit')); add(x.get('pub'))
            for seg in (x.get('parse') or '').split(';'):
                mm = re.match(r'^\s*(.+?) — (.+)$', seg)
                if mm: add(re.split(r'[,(]', mm[2])[0])
    return sorted(words)


def ru_morph(d):
    import subprocess
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'morph.js')
    try:
        r = subprocess.run(['node', script], input=json.dumps(ru_vocab(d), ensure_ascii=False),
                           capture_output=True, text=True, timeout=900)
    except Exception as err:
        return None, f'морфология не собрана ({err}); «Перевод фразы» будет искать по основе слова'
    if r.returncode != 0:
        return None, 'морфология не собрана: ' + (r.stderr or '').strip()[:200]
    return json.loads(r.stdout), None


_ru, _err = ru_morph(data)
if _ru: data['ru'] = _ru
else: warnings.append(_err)

# ---------- проверки ----------

if len(entries) < 150: problems.append(f'статей только {len(entries)}')
if [e['n'] for e in entries] != list(range(1, len(entries) + 1)):
    problems.append('нумерация статей нарушена: ожидалось 1…N подряд')
all_heads = [i for i in range(len(L)) if is_head(i)]
if len(all_heads) != len(entries): problems.append(f'заголовков статей в документе {len(all_heads)}, разобрано {len(entries)}')
pid_text = {}
for e in entries:
    if e['stray']:
        problems.append(f'нераспознанные строки в статье {e["n"]} «{e["title"]}»: ' + ' | '.join(x[:70] for x in e['stray'][:3]))
    if not e['variants'] and not e.get('unestablished'):
        problems.append(f'статья {e["n"]} «{e["title"]}» без форм и без пометки «написание не установлено»')
    for v in e['variants']:
        if v['full'] is not None and v['full'] != len(v['examples']):
            problems.append(f'статья {e["n"]}, вариант {v["form"]}: заявлено полных примеров {v["full"]}, найдено {len(v["examples"])}')
    for x in [x for v in e['variants'] for x in v['examples']] + e['linked']:
        miss = [k for k in ('dendi', 'source', 'lit', 'parse') if not x.get(k)]
        if miss: problems.append(f'статья {e["n"]}, пример {x["pid"]}: нет полей {miss}')
        if x.get('dendi'):
            if x['pid'] in pid_text and pid_text[x['pid']] != x['dendi']:
                problems.append(f'пример {x["pid"]} записан по-разному в разных статьях')
            pid_text.setdefault(x['pid'], x['dendi'])
if not sources: problems.append('библиография не распознана')
if not grammar['rules']: problems.append('раздел грамматики не распознан')

n_ex = len(pid_text)
summary = {'entries': len(entries), 'swadesh': sum(e['kind'] == 'swadesh' for e in entries),
           'extra': sum(e['kind'] == 'extra' for e in entries), 'unique_examples': n_ex,
           'unestablished': sum(1 for e in entries if e.get('unestablished')),
           'links': sum(1 for u in URL if u), 'ru_lemmas': len(data.get('ru') or {})}
print('SUMMARY', json.dumps(summary, ensure_ascii=False))
for w in warnings: print('WARNING', w)
if problems:
    print('STATUS FAILED')
    for p in problems[:40]: print(' -', p)
    sys.exit(2)

# ---------- запись ----------

page = open(page_path, encoding='utf-8').read()
m = re.search(r'(<script type="application/json" id="data">)(.*?)(</script>)', page, re.S)
if not m: fail_now('в странице нет блока данных')
old = None
if m.group(2) != '__DATA__':
    try:
        old = json.loads(m.group(2).replace('<\\/', '</'))
    except Exception:
        old = None
old_built = old.pop('built', None) if isinstance(old, dict) else None
status = 'UNCHANGED' if old == json.loads(json.dumps(data)) else 'CHANGED'
moscow = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
data['built'] = old_built if status == 'UNCHANGED' and old_built else moscow.strftime('%d.%m.%Y')
new_json = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
page = page[:m.start(2)] + new_json + page[m.end(2):]
open(out, 'w', encoding='utf-8').write(page)
if site_dir:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sitegen
    sitegen.build_site(data, page, site_dir, base_url or '/')
    print('SITE', site_dir)
print('STATUS', status)
