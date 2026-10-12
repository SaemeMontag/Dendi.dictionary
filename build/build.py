"""Сборка сайта «Словарь денди» из текста Google-документа.

Использование:
  python3 build.py <документ.txt или JSON Drive> <страница.html> <выход.html> [--site <папка> --base <URL>]

<страница.html> — страница-фрагмент для claude.ai (данные в ней заменяются) или шаблон с __DATA__.
--site: дополнительно собрать полноценный сайт для GitHub Pages в <папке>: index.html с заголовком
для поисковиков, отдельные страницы слов w/<номер>.html, sitemap.xml, robots.txt, assets/site.css.

Разделы документа «История обновлений» и «Постоянные правила словаря» на сайт не попадают.

Код выхода: 0 — собрано (STATUS CHANGED или UNCHANGED); 2 — документ не прошёл проверки
(STATUS FAILED), ничего не записано, публиковать нельзя.
"""
import re, json, sys, os, base64

# ---------- ввод ----------

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

L = [l.rstrip('\r').replace('﻿', '').strip() for l in load_text(src_path).split('\n')]
problems = []

def fail_now(msg):
    print('STATUS FAILED'); print(' -', msg); sys.exit(2)

def find(pred, start=0, end=None, name=''):
    for i in range(start, len(L) if end is None else end):
        if pred(L[i]):
            return i
    fail_now(f'не найден раздел «{name}»')

def eq(t): return lambda l: l == t
def starts(t): return lambda l: l.startswith(t)

# ---------- шаблоны строк ----------

BOILER = 'Засвидетельствованная форма в данном контексте. См. пояснение к примеру; грамматические показатели и тон сохранены.'
SRC_CODE = r'(?:NT18|NT95|AL\d+|COV|CAL|CFA|ANT|SM19|T68/72|N78|N89|G88|GYK|H|AT|AZ|RST)'
SRC_LINE = re.compile(r'^' + SRC_CODE + r'\b[ ,]')
FORM_RE = re.compile(r'^([^Ѐ-ӿ]+?) — (' + SRC_CODE + r'\b.*)$')
EX_RE = re.compile(r'^(\d+)\) (.*)$')
HEAD_RE = re.compile(r'^(\d+)\. (.+)$')
SW_RE = re.compile(r'^Сводеш № (\d+) · Примеров: (\d+)(.*)$')
LETTER_RE = re.compile(r'^[А-ЯЁ]$')
NEWFMT_RE = re.compile(r'^Форма: (.+?)\. Русский смысл: (.+?)\. (.*)$')
ADD_HEAD_RE = re.compile(r'^Дополнение: (.+)$')
ADD_CTX_RE = re.compile(r'^Дополнительный контекст (\d+): (.+?) — «(.+?)»\.? ?(.*)$')

def is_suppl_head(i):
    return bool(HEAD_RE.match(L[i])) and i + 2 < len(L) and L[i + 2].startswith('Дополнение;')

def is_main_head(i):
    return bool(HEAD_RE.match(L[i])) and i + 1 < len(L) and bool(SW_RE.match(L[i + 1]))

def example_from(k, text):
    x = {'k': k, 'text': text, 'gloss': '', 'gloss_type': '', 'source': ''}
    m = NEWFMT_RE.match(text)
    if m:
        x.update(text=m[1], sense=m[2], gloss=m[3], gloss_type='situation')
    return x

# ---------- шапка документа ----------

meta = {'title': L[0], 'updated': L[1]}
i_how = find(eq('Как пользоваться'), name='Как пользоваться')
i_dist = find(eq('Распределение примеров по источникам'), i_how, name='Распределение примеров по источникам')
meta['howto'] = [l for l in L[i_how + 1:i_dist] if l]
i_first_letter = find(lambda l: bool(LETTER_RE.match(l)), i_dist, name='первая буква словаря')
meta['distribution'], meta['distribution_notes'] = [], []
for l in L[i_dist + 1:i_first_letter]:
    if not l or l.startswith('Источник — число'):
        continue
    m = re.match(r'^(\S+) — (.+?): (\d+) \(([\d,]+)%\)\.$', l)
    if m: meta['distribution'].append({'code': m[1], 'label': m[2], 'n': int(m[3]), 'pct': m[4]})
    else: meta['distribution_notes'].append(l)

# ---------- основной словарь ----------

def parse_main(lines, letter):
    m = HEAD_RE.match(lines[0]); s = SW_RE.match(lines[1])
    e = {'n': int(m[1]), 'title': m[2], 'letter': letter, 'suppl': False, 'forms': [], 'examples': [],
         'addenda': [], 'clarifications': [], 'notes': [],
         'swadesh': int(s[1]), 'count': int(s[2]), 'few': 'меньше пяти' in s[3]}
    cur_form = cur_ex = cur_add = cur_ctx = None
    for l in lines[2:]:
        fm, exm, am, cm = FORM_RE.match(l), EX_RE.match(l), ADD_HEAD_RE.match(l), ADD_CTX_RE.match(l)
        if cur_ctx is not None and not cur_ctx['source']:
            if SRC_LINE.match(l): cur_ctx['source'] = l; continue
            e['notes'].append(l); continue
        if cur_ex is not None and not cur_ex['source']:
            if l.startswith('Пояснение: ') and not cur_ex['gloss']:
                cur_ex['gloss'] = l[len('Пояснение: '):]; cur_ex['gloss_type'] = 'note'; continue
            if l.startswith('Рус. параллельный контекст: ') and not cur_ex['gloss']:
                cur_ex['gloss'] = l[len('Рус. параллельный контекст: '):]; cur_ex['gloss_type'] = 'rst'; continue
            if SRC_LINE.match(l): cur_ex['source'] = l; continue
            e['notes'].append(l); continue
        if am:
            cur_add = {'title': am[1], 'note': '', 'contexts': []}; e['addenda'].append(cur_add)
            cur_form = cur_ex = cur_ctx = None
        elif cm and cur_add is not None:
            cur_ctx = {'k': int(cm[1]), 'text': cm[2], 'sense': cm[3], 'gloss': cm[4], 'gloss_type': 'situation', 'source': ''}
            cur_add['contexts'].append(cur_ctx)
        elif cur_add is not None and not cur_add['contexts']:
            cur_add['note'] = (cur_add['note'] + ' ' + l).strip()
        elif l.startswith('Уточнение: '):
            e['clarifications'].append(l[len('Уточнение: '):]); cur_form = None
        elif cur_add is not None:
            e['notes'].append(l)
        elif exm:
            cur_ex = example_from(int(exm[1]), exm[2]); e['examples'].append(cur_ex); cur_form = None
        elif cur_ex is not None:
            e['notes'].append(l)
        elif fm:
            cur_form = {'form': fm[1].strip(), 'sources': fm[2].strip(), 'note': ''}; e['forms'].append(cur_form)
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
            if note: cur_form['note'] = (cur_form['note'] + ' ' + note).strip()
        else:
            e['notes'].append(l)
    return e

i_src = find(eq('Источники и степень доступа'), i_first_letter, name='Источники и степень доступа')
entries, block, letter, blet = [], None, None, None
for i in range(i_first_letter, i_src):
    l = L[i]
    if not l: continue
    if LETTER_RE.match(l):
        letter = l; continue
    if is_main_head(i):
        if block: entries.append(parse_main(block, blet))
        block, blet = [l], letter; continue
    if block is not None: block.append(l)
    else: problems.append(f'строка вне статьи: {l[:60]}')
if block: entries.append(parse_main(block, blet))

# ---------- источники, «меньше пяти», грамматика ----------

i_few = find(eq('Статьи с менее чем пятью примерами'), i_src, name='Статьи с менее чем пятью примерами')
src_lines = [l for l in L[i_src + 1:i_few] if l]
sources_intro, sources = src_lines[0], []
j = 1
while j < len(src_lines):
    code, desc = src_lines[j], src_lines[j + 1] if j + 1 < len(src_lines) else ''
    url = src_lines[j + 2] if j + 2 < len(src_lines) and src_lines[j + 2].startswith('http') else ''
    sources.append({'code': code, 'desc': desc, 'url': url}); j += 3 if url else 2

i_ghead = find(eq('Грамматика и дополнительные статьи'), i_few, name='Грамматика и дополнительные статьи')
few_text = [l for l in L[i_few + 1:i_ghead] if l]
i_g = find(eq('Вопросы на «да/нет»'), i_ghead, name='Вопросы на «да/нет»')
i_rules = find(eq('Правила и порядок слов'), i_g, name='Правила и порядок слов')
i_exs = find(eq('Примеры с разбором по словам'), i_rules, name='Примеры с разбором по словам')
i_addl = find(eq('Дополнительные словарные статьи'), i_exs, name='Дополнительные словарные статьи')

g_intro = [l for l in L[i_g + 1:i_rules] if l]
grammar = {'subtitle': g_intro[0], 'date': g_intro[1], 'intro': [], 'correction': None, 'rules': [], 'examples': [], 'sources': []}
rest = g_intro[2:]
if 'Исправление прежнего объяснения' in rest:
    p = rest.index('Исправление прежнего объяснения')
    grammar['intro'] = rest[:p]; grammar['correction'] = ' '.join(rest[p + 1:])
else:
    grammar['intro'] = rest
rl = [l for l in L[i_rules + 1:i_exs] if l]
for a in range(0, len(rl) - 1, 2):
    t = re.match(r'^(\d+)\. (.+)$', rl[a])
    if not t: problems.append(f'правило грамматики не распознано: {rl[a][:60]}'); continue
    grammar['rules'].append({'n': int(t[1]), 'title': t[2], 'text': rl[a + 1]})
el = [l for l in L[i_exs + 1:i_addl] if l]
a = 0
while a < len(el):
    m = re.match(r'^([БДA-ZА-Я]\d+)\. (.+)$', el[a])
    if not m or a + 4 >= len(el):
        problems.append(f'пример разбора не распознан: {el[a][:60]}'); a += 1; continue
    grammar['examples'].append({'id': m[1], 'dendi': m[2], 'ru': el[a + 1], 'comment': el[a + 2], 'parse': el[a + 3], 'source': el[a + 4]})
    a += 5

# ---------- дополнительные статьи и пояснительные разделы после грамматики ----------

KNOWN_SECTION = lambda l: l in ('Источники и проверка', 'Проверка и дальнейшее пополнение') or l.startswith('Новые слова из обсуждения')

def parse_suppl(lines):
    m = HEAD_RE.match(lines[0])
    fm = re.match(r'^(.+?) — (.+)$', lines[1])
    cm = re.search(r'Контекстов: (\d+)', lines[2])
    e = {'n': int(m[1]), 'title': m[2], 'suppl': True, 'letter': m[2][0].upper(),
         'forms': [{'form': fm[1] if fm else lines[1], 'sources': '', 'note': fm[2] if fm else ''}],
         'examples': [], 'addenda': [], 'clarifications': [], 'notes': [],
         'count': int(cm[1]) if cm else -1, 'label': lines[2],
         'few': 'меньше пяти' in lines[2]}
    cur = None
    for l in lines[3:]:
        exm = EX_RE.match(l)
        if cur is not None and not cur['source']:
            if SRC_LINE.match(l): cur['source'] = l
            else: e['notes'].append(l)
        elif exm:
            cur = example_from(int(exm[1]), exm[2])
            if not cur['gloss_type']:      # старый формат: только пояснение
                cur.update(gloss=cur['text'], text='', gloss_type='note')
            e['examples'].append(cur)
        elif l.startswith('Значение и ограничения. ') and not e['examples']:
            e['meaning'] = l[len('Значение и ограничения. '):]
        else:
            e['notes'].append(l)
    return e

suppl, sections, block, cur_sec = [], [], None, None
for i in range(i_addl + 1, len(L)):
    l = L[i]
    if not l: continue
    if is_suppl_head(i):
        if block: suppl.append(parse_suppl(block))
        block = [l]; cur_sec = None; continue
    if block is not None:
        last = block[-1]
        in_body = (len(block) < 3 or l.startswith('Значение и ограничения. ') or EX_RE.match(l)
                   or (SRC_LINE.match(l) and EX_RE.match(last)))
        if in_body:
            block.append(l); continue
        suppl.append(parse_suppl(block)); block = None
    if KNOWN_SECTION(l) or cur_sec is None:
        if KNOWN_SECTION(l):
            cur_sec = {'title': l, 'paras': []}
        else:
            cur_sec = {'title': '', 'paras': [l]}
        sections.append(cur_sec)
    else:
        cur_sec['paras'].append(l)
if block: suppl.append(parse_suppl(block))
for s in sections:
    if s['title'] == 'Источники и проверка':
        grammar['sources'] = s['paras']
grammar['notes'] = [s for s in sections if s['title'] != 'Источники и проверка']

data = {'meta': meta, 'entries': entries + suppl, 'sources_intro': sources_intro,
        'sources': sources, 'few': few_text, 'grammar': grammar}

# ---------- проверки ----------

main = entries
if len(main) < 150: problems.append(f'основных статей только {len(main)}')
if [e['n'] for e in main] != list(range(1, len(main) + 1)): problems.append('нумерация основных статей нарушена')
bad = [e['n'] for e in main if e['count'] != len(e['examples'])]
if bad: problems.append(f'число примеров не совпадает с заголовком в статьях {bad}')
bad = [e['n'] for e in suppl if e['count'] != len(e['examples'])]
if bad: problems.append(f'число контекстов не совпадает с заголовком в дополнительных статьях {bad}')
if [e['n'] for e in suppl] != list(range(len(main) + 1, len(main) + 1 + len(suppl))):
    problems.append('нумерация дополнительных статей нарушена: ' + str([e['n'] for e in suppl]))
nos = [(e['n'], x['k']) for e in main + suppl for x in e['examples'] if not x['source']]
nos += [(e['n'], 'доп.' + str(c['k'])) for e in main for a in e['addenda'] for c in a['contexts'] if not c['source']]
if nos: problems.append(f'примеры без строки источника {nos[:10]}')
empty = [e['n'] for e in main if not e['forms'] and not e.get('unestablished')]
if empty: problems.append(f'статьи без форм и без пометки {empty}')
for e in main + suppl:
    if e['notes']:
        problems.append(f'нераспознанные строки в статье {e["n"]} «{e["title"]}»: ' + ' | '.join(x[:70] for x in e['notes'][:3]))
# все заголовки статей во всём документе должны попасть на сайт
heads = {int(HEAD_RE.match(L[i])[1]) for i in range(len(L)) if is_main_head(i) or is_suppl_head(i)}
got = {e['n'] for e in main + suppl}
if heads != got: problems.append(f'статьи документа не попали на сайт: {sorted(heads - got)[:20]}')
tm = re.search(r'Всего (\d+) стат', meta['updated'])
if tm and int(tm[1]) != len(got): problems.append(f'в шапке документа {tm[1]} статей, распознано {len(got)}')
if not sources: problems.append('раздел источников не распознан')
if not grammar['rules'] or not grammar['examples']: problems.append('раздел грамматики не распознан')

summary = {'entries': len(main), 'suppl': len(suppl), 'examples': sum(len(e['examples']) for e in main),
           'unestablished': sum(1 for e in main if e.get('unestablished')), 'updated': meta['updated']}
print('SUMMARY', json.dumps(summary, ensure_ascii=False))
if problems:
    print('STATUS FAILED')
    for p in problems: print(' -', p)
    sys.exit(2)

# ---------- запись ----------

page = open(page_path, encoding='utf-8').read()
new_json = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
m = re.search(r'(<script type="application/json" id="data">)(.*?)(</script>)', page, re.S)
if not m: fail_now('в странице нет блока данных')
status = 'UNCHANGED' if m.group(2) == new_json else 'CHANGED'
page = page[:m.start(2)] + new_json + page[m.end(2):]
open(out, 'w', encoding='utf-8').write(page)
if site_dir:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sitegen
    sitegen.build_site(data, page, site_dir, base_url or '/')
    print('SITE', site_dir)
print('STATUS', status)
