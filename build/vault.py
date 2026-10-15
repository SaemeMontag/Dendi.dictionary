"""Чтение хранилища Obsidian со словарём денди (только чтение) → данные сайта.

Читаются только заметки для читателя:
  «Введение.md», «Грамматика/*.md», «Статьи/*.md», «Примеры/*.md», «Источники/*.md».
Никогда не открываются: «Редакторская заметка.md», папка «Редакторская заметка», «AGENTS.md»,
«Проверка переноса.md», «Проверка доступа.md», папка «Перенос», указатели в корне и настройки.

Внутренние ссылки Obsidian превращаются в метки, которые страница превращает в ссылки сайта:
  ⟦w:N|текст⟧ — статья №N, ⟦p:N|текст⟧ — пример ПN, ⟦s:ID|текст⟧ — источник,
  ⟦g:ID|текст⟧ — заметка грамматики, ⟦a:about|текст⟧ — введение, ⟦u:URL|текст⟧ — внешняя ссылка.
Жирный и курсив Markdown (**…**, *…*) сохраняются как есть.
"""
import os, re

READER = ['Введение.md', 'Грамматика', 'Статьи', 'Примеры', 'Источники']

BLOCK_ID = re.compile(r'\s*\^[A-Za-z0-9-]+\s*$')
WIKI = re.compile(r'(!?)\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]')
MD_LINK = re.compile(r'(?<!!)\[([^\]]+)\]\((https?://[^)\s]+)\)')
MD_LINK_LINE = re.compile(r'^\[([^\]]+)\]\((https?://[^)\s]+)\)$')
EMBED = re.compile(r'^!\[\[Примеры/(П\d+)\]\]$')
HEAD_N = re.compile(r'^#\s+(\d+)\.\s+(.+)$')
ROMAN = re.compile(r'^#{2,4}\s+([IVXLC]+)\.\s+(.+)$')
EX_LABEL = re.compile(r'^(#{1,4}\s+)?Пример\b.*$')
REF_CODE = r'(?:NT18|NT95|AL\d+|COV|CAL|CFA|ANT|SM19|T68/72|N78|N89|G88|GYK|H|AT|AZ|RST|IH(?:-[A-Z]+)?)'
REF_TEXT = re.compile(r'^' + REF_CODE + r'\b[ ,:]')
SRC_HEADERS = ('Источники формы и дополнительные контексты:', 'Источники новой партии:',
               'Источники контекстов партии:', 'Источники формы и контекста:')
XREF_HEADER = 'Дополнительные источниковые привязки:'
LINKED_HEADS = ('Полные примеры по ссылкам исходного разбора',)
OVERVIEW = 'Варианты и значения'


class VaultError(Exception):
    pass


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read().replace('\r', '').replace('﻿', '')


def _lines(path):
    out = []
    for raw in _read(path).split('\n'):
        s = BLOCK_ID.sub('', raw).rstrip()
        if s.strip():
            out.append(s.strip())
    return out


def _stem(target):
    return os.path.basename(target.split('#')[0]).strip()


class Linker:
    """Превращает ссылки Obsidian в метки сайта."""

    def __init__(self):
        self.articles = {}   # 'Бог' → 5
        self.grammar = {}    # 'Вопросы на да и нет' → 'g1'
        self.sources = {}    # 'AL65' (имя файла) → 'src0'

    def target(self, target, text):
        t = target.split('#')[0].strip()
        folder, _, name = t.rpartition('/')
        name = name.strip()
        if folder == 'Статьи' and name in self.articles:
            return f'⟦w:{self.articles[name]}|{text}⟧'
        if folder == 'Примеры' and re.fullmatch(r'П\d+', name):
            return f'⟦p:{name[1:]}|{text}⟧'
        if folder == 'Источники' and name in self.sources:
            return f'⟦s:{self.sources[name]}|{text}⟧'
        if folder == 'Грамматика' and name in self.grammar:
            return f'⟦g:{self.grammar[name]}|{text}⟧'
        if not folder and name == 'Введение':
            return f'⟦a:about|{text}⟧'
        return text

    def inline(self, s):
        def wl(m):
            if m[1]:
                return ''
            text = (m[3] or _stem(m[2])).strip()
            return self.target(m[2], text)
        s = WIKI.sub(wl, s)
        s = MD_LINK.sub(lambda m: f'⟦u:{m[2]}|{m[1]}⟧', s)
        return s


def _blocks(lines, linker, skip_first_h1=True):
    """Markdown-строки → блоки [{'t': 'h1'|'h2'|'h3'|'p'|'li', 'x': текст}]."""
    out = []
    for i, l in enumerate(lines):
        if l.startswith('!['):
            continue
        m = re.match(r'^(#{1,6})\s+(.*)$', l)
        if m:
            lvl = len(m[1])
            if lvl == 1 and skip_first_h1 and i == 0:
                continue
            out.append({'t': 'h%d' % min(max(lvl, 2), 3), 'x': linker.inline(m[2])})
            continue
        m = re.match(r'^[-*]\s+(.*)$', l)
        if m:
            out.append({'t': 'li', 'x': linker.inline(m[1])})
            continue
        out.append({'t': 'p', 'x': linker.inline(l)})
    return out


def _source_code(alias_or_stem):
    return alias_or_stem.split(' — ')[0].strip() if ' — ' in alias_or_stem and not alias_or_stem.startswith('T68') else alias_or_stem.strip()


def build_data(vault):
    problems, warnings = [], []
    missing = [n for n in READER if not os.path.exists(os.path.join(vault, n))]
    if missing:
        raise VaultError('в хранилище нет: ' + ', '.join(missing))
    L = Linker()

    # --- номера статей (по заголовку «# N. Название») ---
    art_files = sorted(f for f in os.listdir(os.path.join(vault, 'Статьи')) if f.endswith('.md'))
    art_lines = {}
    for fn in art_files:
        ls = _lines(os.path.join(vault, 'Статьи', fn))
        m = HEAD_N.match(ls[0]) if ls else None
        if not m:
            problems.append(f'у статьи «{fn}» первая строка не вида «# N. Название»')
            continue
        n = int(m[1])
        if n in L.articles.values():
            problems.append(f'номер {n} повторяется (статья «{fn}»)')
        L.articles[fn[:-3]] = n
        art_lines[fn[:-3]] = (n, m[2].strip(), ls)

    # --- источники (порядок — по указателю) ---
    sdir = os.path.join(vault, 'Источники')
    order, aliases = [], {}
    idx = os.path.join(sdir, 'Указатель источников.md')
    if os.path.exists(idx):
        for m in WIKI.finditer(_read(idx)):
            st = _stem(m[2])
            if st not in order:
                order.append(st); aliases[st] = (m[3] or st).strip()
    rest = sorted(f[:-3] for f in os.listdir(sdir) if f.endswith('.md') and f != 'Указатель источников.md' and f[:-3] not in order)
    src_names = [s for s in order + rest if os.path.exists(os.path.join(sdir, s + '.md'))]
    rst_name = next((s for s in src_names if s.startswith('Опубликованный русский параллельный текст')), None)
    for i, s in enumerate(src_names):
        L.sources[s] = 'srcrst' if s == rst_name else f'src{i}'

    # --- грамматика (порядок — по указателю грамматики, если есть) ---
    gdir = os.path.join(vault, 'Грамматика')
    g_all = sorted(f[:-3] for f in os.listdir(gdir) if f.endswith('.md'))
    g_index = next((g for g in g_all if g.startswith('Указатель')), None)
    g_order = []
    if g_index:
        for m in WIKI.finditer(_read(os.path.join(gdir, g_index + '.md'))):
            st = _stem(m[2])
            if st in g_all and st not in g_order and st != g_index:
                g_order.append(st)
    g_names = ([g_index] if g_index else []) + g_order + [g for g in g_all if g not in g_order and g != g_index]
    for i, g in enumerate(g_names):
        L.grammar[g] = f'g{i}'

    # --- примеры ---
    examples, plinks = {}, {}
    for fn in os.listdir(os.path.join(vault, 'Примеры')):
        if not fn.endswith('.md'):
            continue
        pid = fn[:-3]
        x = {'pid': pid}
        for l in _lines(os.path.join(vault, 'Примеры', fn)):
            if l.startswith('## Статьи слов примера'):
                break
            m = MD_LINK_LINE.match(l)
            if m and m[1].startswith('Источник:'):
                x['source'] = m[1][len('Источник:'):].strip(); x['source_url'] = m[2]; continue
            if m and 'параллельный текст' in m[1]:
                x['pub_label'] = m[1]; x['pub_url'] = m[2]; x['rst'] = m[1].startswith('Синодальный'); continue
            for pre, key in (('Денди: ', 'dendi'), ('Источник: ', 'source'), ('Опубликованный русский перевод: ', 'pub'),
                             ('Авторский дословный перевод: ', 'lit'), ('Разбор по словам: ', 'parse'), ('Примечание: ', 'note')):
                if l.startswith(pre) and key not in x:
                    val = l[len(pre):]
                    if key == 'parse':
                        plinks[pid] = [[(mm[3] or _stem(mm[2])).strip(), L.articles.get(_stem(mm[2]))]
                                       for mm in WIKI.finditer(val) if mm[2].startswith('Статьи/')]
                        val = WIKI.sub(lambda mm: (mm[3] or _stem(mm[2])).strip(), val)
                    elif key in ('note', 'pub', 'lit', 'dendi', 'source'):
                        val = L.inline(val) if key == 'note' else WIKI.sub(lambda mm: (mm[3] or _stem(mm[2])).strip(), val)
                    x[key] = val
                    break
            else:
                if not l.startswith('# '):
                    x.setdefault('extra', []).append(L.inline(l))
        miss = [k for k in ('dendi', 'source', 'lit', 'parse') if not x.get(k)]
        if miss:
            problems.append(f'пример {pid}: нет полей {miss}')
        examples[pid] = x

    # --- статьи ---
    entries = []
    for name, (n, title, ls) in sorted(art_lines.items(), key=lambda kv: kv[1][0]):
        e = {'n': n, 'title': title, 'kind': 'extra', 'variants': [], 'extra_refs': [], 'linked': [], 'notes': []}
        var = None
        mode = 'pre'
        pending = []
        seen_refs = set()

        def new_var(label, form):
            v = {'label': label, 'form': form, 'notes': [], 'full': None, 'status': '', 'examples': [], 'refs': []}
            e['variants'].append(v)
            return v

        def note(text):
            if var is None:
                e['notes'].append(L.inline(text))
            elif var['examples']:
                pending.append(L.inline(text))
            else:
                var['notes'].append(L.inline(text))

        for l in ls[1:]:
            plain = re.sub(r'^#{1,6}\s+', '', l)
            if l.startswith('#') and plain.startswith(OVERVIEW):
                mode = 'overview'; continue
            if mode == 'overview':
                if l.startswith('- '):
                    continue
                mode = 'pre' if var is None else 'var'
            if re.fullmatch(r'Сводеш № (\d+)', plain):
                e['kind'] = 'swadesh'; e['swadesh'] = int(plain.split('№')[1]); continue
            if plain == 'Дополнительная лексика и грамматика.':
                e['kind'] = 'extra'; continue
            if plain.startswith('Значение и употребление: '):
                txt = L.inline(plain[len('Значение и употребление: '):])
                e['meaning'] = (e['meaning'] + ' ' + txt) if e.get('meaning') else txt; continue
            if plain.startswith('Практическое написание не установлено'):
                e['unestablished'] = plain; continue
            if plain.startswith('Научный указатель: '):
                e['sci'] = L.inline(plain[len('Научный указатель: '):]); continue
            if plain.startswith('Связанные примеры:'):
                e['related'] = L.inline(plain[len('Связанные примеры:'):].strip()); continue
            if l.startswith('#') and plain.startswith(LINKED_HEADS):
                mode = 'linked'; continue
            rm = ROMAN.match(l)
            if rm:
                if pending and var is not None: var['notes'] += pending
                pending = []
                var = new_var(rm[1], rm[2].strip()); mode = 'var'; continue
            if plain in SRC_HEADERS:
                mode = 'refs'; continue
            if plain == XREF_HEADER:
                mode = 'xrefs'; continue
            em = EMBED.match(l)
            if em:
                pid = em[1]
                if pid not in examples:
                    problems.append(f'статья {n} «{title}»: встраивание ![[Примеры/{pid}]] без заметки примера'); continue
                if mode == 'linked' or var is None:
                    if pid not in {x['pid'] for x in e['linked']}:
                        e['linked'].append(dict(examples[pid]))
                    continue
                if pid in {x['pid'] for x in var['examples']}:
                    continue
                x = dict(examples[pid]); x['k'] = len(var['examples']) + 1
                if pending: x['lead'] = pending; pending = []
                var['examples'].append(x); mode = 'var'; continue
            if EX_LABEL.match(l) or plain == 'Примеры:':
                continue
            if mode in ('refs', 'xrefs'):
                m = MD_LINK_LINE.match(l)
                if m or REF_TEXT.match(plain):
                    r = {'t': m[1] if m else plain, 'u': m[2] if m else ''}
                    key = (r['t'], r['u'])
                    target = e['extra_refs'] if (mode == 'xrefs' or var is None) else var['refs']
                    if (id(target), key) not in seen_refs:
                        seen_refs.add((id(target), key)); target.append(r)
                    continue
                mode = 'var' if var is not None else 'pre'
            fm = re.fullmatch(r'Полных примеров для этого варианта: (\d+)\.', plain)
            if fm:
                if var is None: var = new_var('', '')
                var['full'] = int(fm[1]); continue
            if plain.startswith('Полный пример с дословным разбором отсутствует'):
                if var is None: var = new_var('', '')
                var['status'] = plain; continue
            if mode == 'pre' and var is None and not re.search(r'[А-Яа-яЁё]', plain) and len(plain) < 60 and not l.startswith('#'):
                var = new_var('', plain); mode = 'var'; continue
            if var is not None and not var['form'] and not re.search(r'[А-Яа-яЁё]', plain) and len(plain) < 60 and not var['examples']:
                var['form'] = plain; continue
            note(plain if not l.startswith('#') else plain)
        if pending and var is not None:
            var['notes'] += pending
        for v in e['variants']:
            if v['full'] is not None and v['full'] != len(v['examples']):
                warnings.append(f'статья {n} «{title}», вариант {v["form"] or "—"}: заявлено полных примеров {v["full"]}, встроено {len(v["examples"])}')
        if not e['variants'] and not e.get('unestablished') and not e['linked']:
            warnings.append(f'статья {n} «{title}»: нет ни вариантов, ни пометки «написание не установлено»')
        e['letter'] = next((ch.upper().replace('Ё', 'Е') for ch in title if ch.isalpha()), '#')
        entries.append(e)

    nums = [e['n'] for e in entries]
    if nums and nums != list(range(1, len(nums) + 1)):
        gaps = sorted(set(range(1, max(nums) + 1)) - set(nums))
        warnings.append(f'номера статей идут не подряд (пропущены: {gaps[:10]})')

    # --- источники: заметки ---
    sources, rst = [], None
    for s in src_names:
        ls = _lines(os.path.join(sdir, s + '.md'))
        title = re.sub(r'^#\s+', '', ls[0]) if ls and ls[0].startswith('# ') else s
        url = ''
        body = []
        for l in ls[1:] if ls and ls[0].startswith('# ') else ls:
            m = MD_LINK_LINE.match(l)
            if m and not url and (m[1].startswith('Источник') or m[1].startswith('RST')):
                url = m[2]; continue
            body.append(l)
        rec = {'id': L.sources[s], 'code': aliases.get(s, _source_code(s)), 'title': title, 'url': url, 'blocks': _blocks(body, L, False)}
        if s == rst_name:
            rec['code'] = 'RST'; rst = rec
        else:
            sources.append(rec)

    # --- введение и грамматика ---
    intro = _blocks(_lines(os.path.join(vault, 'Введение.md')), L)
    grammar = []
    for g in g_names:
        ls = _lines(os.path.join(gdir, g + '.md'))
        title = re.sub(r'^#\s+', '', ls[0]) if ls and ls[0].startswith('# ') else g
        grammar.append({'id': L.grammar[g], 'title': title, 'index': g == g_index, 'blocks': _blocks(ls, L)})

    data = {'meta': {'intro': intro}, 'grammar': grammar, 'entries': entries, 'sources': sources,
            'rst': rst, 'plinks': plinks}
    return data, problems, warnings
