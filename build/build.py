"""Сборка сайта «Словарь денди» из текста Google-документа.
Использование: python3 build.py <документ.txt или JSON Drive> <страница.html> <выход.html> [--site <папка> --base <URL>]
<страница.html> — страница-фрагмент для claude.ai (данные в ней заменяются) или шаблон с __DATA__.
--site: дополнительно собрать полноценный сайт для GitHub Pages в <папке>: index.html с заголовком
для поисковиков, отдельные страницы слов w/<номер>.html, sitemap.xml, robots.txt, assets/site.css.
Код выхода: 0 — собрано (STATUS CHANGED или UNCHANGED), 2 — документ не прошёл проверки, публиковать нельзя.
"""
import re, json, sys, base64

def load_text(path):
    raw = open(path, encoding='utf-8').read()
    if raw.lstrip().startswith('{'):
        d = json.loads(raw); c = d.get('content', '')
        try:
            return base64.b64decode(c, validate=True).decode('utf-8')
        except Exception:
            return c
    return raw

args = sys.argv[1:]
site_dir = base_url = None
if '--site' in args:
    i = args.index('--site'); site_dir = args[i + 1]; del args[i:i + 2]
if '--base' in args:
    i = args.index('--base'); base_url = args[i + 1].rstrip('/') + '/'; del args[i:i + 2]
src_path, page_path, out = args[0], args[1], args[2]
L = [l.rstrip('\r').replace('﻿', '') for l in load_text(src_path).split('\n')]

def idx(text, start=0):
    for i in range(start, len(L)):
        if L[i].strip() == text:
            return i
    raise SystemExit('not found: ' + text)

BOILER = 'Засвидетельствованная форма в данном контексте. См. пояснение к примеру; грамматические показатели и тон сохранены.'
SRC_RE = r'(NT18|NT95|AL65|AL64|COV|CAL|CFA|ANT|SM19|T68/72|N78|H|AT|AZ|RST)'
FORM_RE = re.compile(r'^([^Ѐ-ӿ]+?) — (' + SRC_RE + r'\b.*)$')
EX_RE = re.compile(r'^(\d+)\) (.*)$')
HEAD_RE = re.compile(r'^(\d+)\. (.+)$')
SW_RE = re.compile(r'^Сводеш № (\d+) · Примеров: (\d+)(.*)$')
LETTER_RE = re.compile(r'^[А-ЯЁ]$')

meta = {
    'title': L[0].strip(),
    'updated': L[1].strip(),
    'about': L[2].strip(),
    'history': [L[4].strip()],
    'stats': L[12].strip(),
}

i_how = idx('Как пользоваться')
i_dist = idx('Распределение примеров по источникам')
meta['howto'] = [l.strip() for l in L[i_how+1:i_dist] if l.strip()]
i_first_letter = next(i for i in range(i_dist, len(L)) if LETTER_RE.match(L[i].strip()))
dist_lines = [l.strip() for l in L[i_dist+2:i_first_letter] if l.strip()]
meta['distribution'] = []
meta['distribution_notes'] = []
for l in dist_lines:
    m = re.match(r'^(\S+) — (.+?): (\d+) \(([\d,]+)%\)\.$', l)
    if m:
        meta['distribution'].append({'code': m[1], 'label': m[2], 'n': int(m[3]), 'pct': m[4]})
    else:
        meta['distribution_notes'].append(l)

i_src = idx('Источники и степень доступа')
i_suppl_head = idx('Грамматика и дополнительные статьи')

entries = []

def parse_block(lines, letter, suppl=False):
    """lines: list of stripped lines of one entry incl header"""
    m = HEAD_RE.match(lines[0])
    e = {'n': int(m[1]), 'title': m[2], 'letter': letter, 'forms': [], 'notes': [],
         'examples': [], 'suppl': suppl}
    k = 1
    if not suppl:
        s = SW_RE.match(lines[1])
        e['swadesh'] = int(s[1]); e['count'] = int(s[2]); e['few'] = 'меньше пяти' in s[3]
        k = 2
    else:
        # "ya — desc" then "Дополнение; ... · Контекстов: 5"
        fm = re.match(r'^(.+?) — (.+)$', lines[1])
        e['forms'].append({'form': fm[1], 'sources': '', 'note': fm[2]})
        cm = re.search(r'Контекстов: (\d+)', lines[2])
        e['count'] = int(cm[1]) if cm else 0
        e['label'] = lines[2]
        k = 3
    cur_form = None
    cur_ex = None
    while k < len(lines):
        l = lines[k]
        exm = EX_RE.match(l)
        fm = FORM_RE.match(l) if not suppl else None
        if exm and not l.startswith(('Значение', 'Дополнительный', 'Научный')):
            cur_ex = {'k': int(exm[1]), 'text': exm[2], 'gloss': '', 'gloss_type': '', 'source': ''}
            e['examples'].append(cur_ex); cur_form = None
            if suppl:
                cur_ex['gloss'] = exm[2]; cur_ex['text'] = ''; cur_ex['gloss_type'] = 'note'
        elif cur_ex is not None:
            if l.startswith('Пояснение: '):
                cur_ex['gloss'] = l[len('Пояснение: '):]; cur_ex['gloss_type'] = 'note'
            elif l.startswith('Рус. параллельный контекст: '):
                cur_ex['gloss'] = l[len('Рус. параллельный контекст: '):]; cur_ex['gloss_type'] = 'rst'
            elif not cur_ex['source']:
                cur_ex['source'] = l
            else:
                cur_ex['source'] += ' ' + l
        elif fm:
            cur_form = {'form': fm[1].strip(), 'sources': fm[2].strip(), 'note': ''}
            e['forms'].append(cur_form)
        elif l.startswith('Значение и ограничения. '):
            e['meaning'] = l[len('Значение и ограничения. '):]; cur_form = None
        elif l.startswith('Дополнительный указатель. '):
            e['index_extra'] = l[len('Дополнительный указатель. '):]; cur_form = None
        elif l.startswith('Научный указатель. '):
            e['index_sci'] = l[len('Научный указатель. '):]; cur_form = None
        elif l.startswith('Практическое написание не установлено'):
            e['unestablished'] = l; cur_form = None
        elif cur_form is not None:
            note = l.replace(BOILER, '').strip()
            if note:
                cur_form['note'] = (cur_form['note'] + ' ' + note).strip()
        else:
            e['notes'].append(l)
        k += 1
    return e

def collect(start, end, suppl=False):
    letter = None
    block = None
    res = []
    for i in range(start, end):
        l = L[i].strip()
        if not l:
            continue
        if not suppl and LETTER_RE.match(l):
            letter = l; continue
        if HEAD_RE.match(l) and (suppl or (i+1 < end and SW_RE.match(L[i+1].strip()))):
            if block: res.append(parse_block(block, blet, suppl))
            block = [l]; blet = letter
            continue
        if block is not None:
            block.append(l)
    if block: res.append(parse_block(block, blet, suppl))
    return res

entries = collect(i_first_letter, i_src)

# sources
i_few = idx('Статьи с менее чем пятью примерами')
src_lines = [l.strip() for l in L[i_src+1:i_few] if l.strip()]
sources_intro = src_lines[0]
sources = []
j = 1
while j < len(src_lines):
    code = src_lines[j]
    desc = src_lines[j+1]
    url = src_lines[j+2] if j+2 < len(src_lines) and src_lines[j+2].startswith('http') else ''
    sources.append({'code': code, 'desc': desc, 'url': url})
    j += 3 if url else 2

# grammar
i_g = idx('Вопросы на «да/нет»')
i_rules = idx('Правила и порядок слов')
i_exs = idx('Примеры с разбором по словам')
i_addl = idx('Дополнительные словарные статьи')
i_gsrc = idx('Источники и проверка')
g_intro = [l.strip() for l in L[i_g+1:i_rules] if l.strip()]
grammar = {'subtitle': g_intro[0], 'date': g_intro[1], 'intro': [], 'correction': None, 'rules': [], 'examples': []}
rest = g_intro[2:]
if 'Исправление прежнего объяснения' in rest:
    p = rest.index('Исправление прежнего объяснения')
    grammar['intro'] = rest[:p]; grammar['correction'] = ' '.join(rest[p+1:])
else:
    grammar['intro'] = rest
rl = [l.strip() for l in L[i_rules+1:i_exs] if l.strip()]
for a in range(0, len(rl), 2):
    t = re.match(r'^(\d+)\. (.+)$', rl[a])
    body = rl[a+1]
    refs = re.findall(r'NT18, [^;]+?\d+:\d+', body)
    grammar['rules'].append({'n': int(t[1]), 'title': t[2], 'text': body})
el = [l.strip() for l in L[i_exs+1:i_addl] if l.strip()]
a = 0
while a < len(el):
    m = re.match(r'^([БД]\d)\. (.+)$', el[a])
    ex = {'id': m[1], 'dendi': m[2], 'ru': el[a+1], 'comment': el[a+2], 'parse': el[a+3], 'source': el[a+4]}
    grammar['examples'].append(ex); a += 5
grammar['sources'] = [l.strip() for l in L[i_gsrc+1:] if l.strip()]

suppl = collect(i_addl+1, i_gsrc, suppl=True)
for s in suppl:
    s['letter'] = s['title'][0].upper()

few_text = [l.strip() for l in L[i_few+1:i_suppl_head] if l.strip()]

data = {'meta': meta, 'entries': entries + suppl, 'sources_intro': sources_intro,
        'sources': sources, 'few': few_text, 'grammar': grammar}

# --- проверки ---
problems = []
main = entries
if len(main) < 150: problems.append(f'основных статей только {len(main)}')
if [e['n'] for e in main] != list(range(1, len(main) + 1)): problems.append('нумерация основных статей нарушена')
bad = [e['n'] for e in main if e['count'] != len(e['examples'])]
if bad: problems.append(f'число примеров не совпадает с заголовком в статьях {bad}')
if [e['n'] for e in suppl] != list(range(len(main) + 1, len(main) + 1 + len(suppl))): problems.append('нумерация дополнительных статей нарушена')
nos = [(e['n'], x['k']) for e in entries + suppl for x in e['examples'] if not x['source']]
if nos: problems.append(f'примеры без источника {nos[:10]}')
empty = [e['n'] for e in main if not e['forms'] and not e.get('unestablished')]
if empty: problems.append(f'статьи без форм и без пометки {empty}')
stray = [e['n'] for e in entries + suppl if e['notes']]
if stray: problems.append(f'нераспознанные строки в статьях {stray}')
if not sources: problems.append('раздел источников не распознан')
if not grammar['rules'] or not grammar['examples']: problems.append('раздел грамматики не распознан')
summary = {'entries': len(main), 'suppl': len(suppl), 'examples': sum(len(e['examples']) for e in main),
           'unestablished': sum(1 for e in main if e.get('unestablished')), 'updated': meta['updated']}
print('SUMMARY', json.dumps(summary, ensure_ascii=False))
if problems:
    print('STATUS FAILED')
    for p in problems: print(' -', p)
    sys.exit(2)

page = open(page_path, encoding='utf-8').read()
new_json = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
m = re.search(r'(<script type="application/json" id="data">)(.*?)(</script>)', page, re.S)
if not m:
    print('STATUS FAILED'); print(' - в странице нет блока данных'); sys.exit(2)
status = 'UNCHANGED' if m.group(2) == new_json else 'CHANGED'
page = page[:m.start(2)] + new_json + page[m.end(2):]
open(out, 'w', encoding='utf-8').write(page)
if site_dir:
    import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sitegen
    sitegen.build_site(data, page, site_dir, base_url or '/')
    print('SITE', site_dir)
print('STATUS', status)
