"""Сборка статического сайта для GitHub Pages: полноценный index.html, страницы слов, карта сайта."""
import os, re, json, html, datetime

SITE_NAME = 'Словарь денди'
SITE_DESC = ('Русско-дендийский словарь: базовая лексика списка Сводеша и дополнительные слова языка денди '
             '(сонгай северного Бенина) — варианты письма с источниками, полные примеры с переводом и разбором, грамматика.')
RESET = (':root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
         'body{margin:0}img{max-width:100%}[hidden]{display:none!important}')
ALPHA = 'АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЭЮЯ'

e_ = lambda s: html.escape(str(s or ''), quote=True)


def plural(n, a, b, c):
    m10, m100 = n % 10, n % 100
    return a if m10 == 1 and m100 != 11 else b if 2 <= m10 <= 4 and not 12 <= m100 <= 14 else c


def src_ids(sources, rst=None):
    ids = {}
    for s in sources:
        for c in re.split(r'\s+[—/]\s+|\s*/\s*|\s+', s['code']):
            if re.fullmatch(r'[A-Z][A-Z0-9-]*', c) and c not in ids:
                ids[c] = s['id']
        if s['code'].startswith('T68'): ids['T68/72'] = s['id']
    if rst: ids['RST'] = rst['id']
    return ids


MARK = re.compile(r'⟦([a-z]):([^|⟧]*)\|([^⟧]*)⟧')


def _fmt(t):
    t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
    return re.sub(r'(^|[^*\w])\*(?!\s)(.+?)\*(?!\w)', r'\1<i>\2</i>', t)


def link_src(text, ids, prefix):
    """Текст с метками ⟦…⟧ → HTML для страницы слова (prefix — путь к корню сайта, например '../')."""
    codes = sorted(ids, key=len, reverse=True)
    code_re = re.compile(r'(?<![\wА-Яа-яЁё-])(' + '|'.join(re.escape(c) for c in codes) + r')(?![\wА-Яа-яЁё-])') if codes else None

    def plain(t):
        t = e_(t)
        t = re.sub(r'П(\d+)', lambda m: f'<a class="pid" href="{prefix}#p{m[1]}">П{m[1]}</a>', t)
        if code_re:
            t = code_re.sub(lambda m: f'<a class="code" href="{prefix}#{ids[m[1]]}">{m[1]}</a>', t)
        return _fmt(t)
    out, last = '', 0
    for m in MARK.finditer(text or ''):
        out += plain(text[last:m.start()]); last = m.end()
        k, ref, t = m[1], m[2], _fmt(e_(m[3]))
        href = {'w': f'{ref}.html', 'p': f'{prefix}#p{ref}', 's': f'{prefix}#{ref}', 'g': f'{prefix}#gr-{ref}',
                'a': f'{prefix}#about'}.get(k)
        if k == 'u':
            out += f'<a href="{e_(ref)}" target="_blank" rel="noopener">{t}</a>'
        elif href:
            out += f'<a href="{e_(href)}">{t}</a>'
        else:
            out += t
    return out + plain((text or '')[last:])


def head(title, desc, canonical, css_href, fonts_href, inline_css='', extra=''):
    return f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e_(title)}</title>
<meta name="description" content="{e_(desc)}">
<link rel="canonical" href="{e_(canonical)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{e_(title)}">
<meta property="og:description" content="{e_(desc)}">
<meta property="og:url" content="{e_(canonical)}">
<meta property="og:locale" content="ru_RU">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{e_(fonts_href)}">
<style>{RESET}</style>
{f'<link rel="stylesheet" href="{css_href}">' if css_href else ''}{inline_css}
{extra}
</head>
<body>
'''


def header(prefix):
    return f'''<header class="top">
  <div class="wrap">
    <div class="brand"><a href="{prefix}"><span class="name">Денди</span></a><span class="sub">Русско-дендийский словарь · сонгай северного Бенина</span></div>
    <nav class="main">
      <a href="{prefix}#home">Словник</a>
      <a href="{prefix}#parse">Перевод фразы</a>
      <a href="{prefix}#dendi">Денди → русский</a>
      <a href="{prefix}#examples">Примеры</a>
      <a href="{prefix}#grammar">Грамматика</a>
      <a href="{prefix}#sources">Источники</a>
      <a href="{prefix}#about">Как пользоваться</a>
      <a href="{prefix}#contacts">Контакты</a>
    </nav>
  </div>
  <div class="weave" aria-hidden="true"></div>
</header>
'''


def variant_forms(v):
    return [re.sub(r'\s*\(.*?\)\s*', ' ', f).strip() for f in re.split(r'[;,]\s+', v['form']) if f.strip()]


def all_forms(e):
    return list(dict.fromkeys(f for v in e['variants'] for f in variant_forms(v)))


def examples_of(e):
    return [x for v in e['variants'] for x in v['examples']] + list(e.get('linked', []))


def entry_desc(e):
    if not e['variants']:
        return f'{e["title"]} на языке денди: практическое написание пока не установлено. Научные указатели для сверки — в словаре денди.'
    n = len({x['pid'] for x in examples_of(e)})
    tail = f'{n} {plural(n, "полный пример", "полных примера", "полных примеров")} с переводом и разбором.' if n else 'Варианты письма с источниками.'
    return f'{e["title"]} на языке денди: {", ".join(all_forms(e))}. {tail}'[:300]


def ext(text, url):
    return f'<a href="{e_(url)}" target="_blank" rel="noopener">{e_(text)}</a>' if url else e_(text)


def chips(p, links=None, prefix=''):
    items = []
    for seg in re.split(r';\s*', p.rstrip('.')):
        m = re.match(r'^(.+?) — (.+)$', seg)
        if m: items.append([m[1], m[2]])
        elif items: items[-1][1] += '; ' + seg
        else: items.append(['', seg])
    lk = {w: n for w, n in (links or []) if n}
    def word(w):
        if not w: return ''
        inner = f'<a href="{prefix}{lk[w]}.html">{e_(w)}</a>' if w in lk else e_(w)
        return f'<span class="gw" lang="ddn">{inner}</span>'
    return '<div class="gloss">' + ''.join(
        '<span>' + word(w) + f'<span class="gg">{e_(g)}</span></span>' for w, g in items) + '</div>'


def ex_card(x, ids, p, pid_entries, here, plinks=None, linked=False):
    rst_tag = ' <span class="tag info">Синодальный</span>' if x.get('rst') else ''
    if x.get('pub'):
        pub_html = e_(x['pub'])
        if x.get('pub_url'):
            lab = 'текст' if x.get('rst') else e_(x.get('pub_label') or 'текст')
            pub_html += f' <a class="small" href="{e_(x["pub_url"])}" target="_blank" rel="noopener">{lab}</a>'
    else:
        pub_html = ''
    others = [o for o in pid_entries.get(x['pid'], []) if o is not here]
    lead = ''.join(f'<p class="small">{link_src(t, ids, p)}</p>' for t in (x.get('lead') or []))
    tag = e_(x['pid']) if linked else f'Пример {x["k"]} · {e_(x["pid"])}'
    s = (lead + f'<article class="exc"><div class="exh"><span class="pidtag">{tag}</span>'
         f'<span class="src">{ext(x["source"], x.get("source_url"))}</span></div>'
         f'<p class="dsent" lang="ddn">{e_(x["dendi"])}</p><dl class="exf">'
         + (f'<dt>Опубликованный перевод{rst_tag}</dt><dd>{pub_html}</dd>' if pub_html else '')
         + f'<dt>Дословный перевод</dt><dd>{e_(x["lit"])}</dd>'
         f'<dt>Разбор по словам</dt><dd>{chips(x["parse"], (plinks or {}).get(x["pid"]))}</dd>')
    if x.get('note'): s += f'<dt>Примечание</dt><dd>{link_src(x["note"], ids, p)}</dd>'
    if x.get('extra'): s += '<dt>Дополнительно</dt><dd>' + '<br>'.join(link_src(t, ids, p) for t in x['extra']) + '</dd>'
    s += '</dl>'
    if others:
        s += f'<p class="small muted">Этот пример есть и в {plural(len(others), "статье", "статьях", "статьях")}: ' + ', '.join(
            f'<a href="{o["n"]}.html">{e_(o["title"])}</a>' for o in others) + '</p>'
    return s + '</article>'


def ref_list(refs):
    return '<ul class="refs">' + ''.join(f'<li>{ext(r["t"], r["u"])}</li>' for r in refs) + '</ul>'


def entry_html(e, ids, prev, nxt, pid_entries, plinks=None):
    p = '../'
    n_ex = len({x['pid'] for x in examples_of(e)})
    meta = f'<span>№ {e["n"]}</span>' + (f'<span>Сводеш № {e["swadesh"]}</span>' if e['kind'] == 'swadesh' else '<span class="tag info">дополнительная лексика</span>')
    if len(e['variants']) > 1:
        meta += f'<span>{len(e["variants"])} {plural(len(e["variants"]), "вариант", "варианта", "вариантов")}</span>'
    meta += f'<span>{n_ex} {plural(n_ex, "полный пример", "полных примера", "полных примеров")}</span>' if n_ex else '<span>полных примеров пока нет</span>'
    lhref = f'{p}#l{ALPHA.index(e["letter"])}' if e['letter'] in ALPHA else p
    parts = [f'<div class="crumbs"><a href="{p}">Словник</a><span>›</span><a href="{lhref}">{e_(e["letter"])}</a></div>',
             f'<div class="entry-head"><h1>{e_(e["title"])}</h1><div class="meta">{meta}</div></div>']
    if e.get('unestablished'):
        parts.append(f'<div class="box warn"><span class="label">Написание не установлено</span>{e_(e["unestablished"])}</div>')
    if len(e.get('overview') or []) > 1:
        lis = ''.join('<li>' + (f'<a href="#v-{e_(o["label"])}"><span class="vl">{e_(o["label"])}</span> <span class="dn" lang="ddn">{e_(o["form"])}</span></a>' if o.get('anchor') else (f'<span class="vl">{e_(o["label"])}</span> ' if o['label'] else '') + f'<span class="dn" lang="ddn">{e_(o["form"])}</span>')
                      + (f' — {link_src(o["note"], ids, p)}' if o['note'] else '') + '</li>' for o in e['overview'])
        parts.append(f'<nav class="box ovl" aria-label="Варианты"><span class="label">Варианты и значения</span><ul>{lis}</ul></nav>')
    if e.get('meaning'):
        parts.append(f'<div class="box"><span class="label">Значение и употребление</span>{link_src(e["meaning"], ids, p)}</div>')
    parts += [f'<p>{link_src(t, ids, p)}</p>' for t in e.get('notes', [])]
    for v in e['variants']:
        s = '<section class="variant"' + (f' id="v-{e_(v["label"])}"' if v['label'] else '') + '><div class="vh">' + (f'<span class="vl">{v["label"]}</span>' if v['label'] else '') + f'<span class="vf" lang="ddn">{e_(v["form"])}</span></div>'
        s += ''.join(f'<p>{link_src(n, ids, p)}</p>' for n in v['notes'])
        if v['examples']:
            s += '<div class="exs">' + ''.join(ex_card(x, ids, p, pid_entries, e, plinks) for x in v['examples']) + '</div>'
        else:
            s += f'<p class="small muted">{e_(v["status"] or "Полного примера с дословным разбором пока нет.")}</p>'
        if v['refs']:
            s += f'<div class="stack" style="gap:4px"><span class="label">Источники формы и дополнительные контексты · {len(v["refs"])}</span>{ref_list(v["refs"])}</div>'
        parts.append(s + '</section>')
    if e.get('linked'):
        parts.append('<section class="variant"><div class="vh"><span class="vf" style="font-family:var(--f-display);font-size:1.15rem">Другие полные примеры с этим словом</span></div>'
                     '<p class="small muted">Примеры, в разборе которых есть ссылка на эту статью.</p><div class="exs">'
                     + ''.join(ex_card(x, ids, p, pid_entries, e, plinks, linked=True) for x in e['linked']) + '</div></section>')
    if e.get('related'):
        parts.append(f'<p class="small"><span class="muted">Связанные примеры:</span> {link_src(e["related"], ids, p)}</p>')
    if e['extra_refs']:
        parts.append(f'<section class="stack" style="gap:4px"><span class="label">Дополнительные источниковые привязки</span>{ref_list(e["extra_refs"])}</section>')
    if e.get('sci'):
        parts.append(f'<section class="stack small"><span class="label">Для сверки</span><p><span class="muted">Научный указатель.</span> {link_src(e["sci"], ids, p)}</p></section>')
    parts.append(f'<p><a href="{p}#w{e["n"]}">Открыть статью в интерактивном словаре с поиском →</a></p>')
    pager = ''
    if prev: pager += f'<a href="{prev["n"]}.html"><small>← предыдущая</small>{e_(prev["title"])}</a>'
    if nxt: pager += f'<a class="next" href="{nxt["n"]}.html"><small>следующая →</small>{e_(nxt["title"])}</a>'
    parts.append(f'<nav class="pager">{pager}</nav>')
    return '<article class="stack" style="gap:22px">' + '\n'.join(parts) + '</article>'


def static_index(entries):
    letters = [L for L in ALPHA if any(e['letter'] == L for e in entries)]
    letters += sorted({e['letter'] for e in entries} - set(ALPHA))  # заголовки на другую букву (COVID-19)
    out = ['<div class="stack"><h1>Русско-дендийский словарь</h1>', f'<p class="lead">{e_(SITE_DESC)}</p><div class="letters">']
    for L in letters:
        items = ''.join(
            f'<li><a href="w/{e["n"]}.html">{e_(e["title"])}</a>'
            + (f'<span class="f" lang="ddn">{e_(", ".join(v["form"] for v in e["variants"][:2]))}</span>' if e['variants'] else '<span class="none">—</span>')
            + '</li>' for e in entries if e['letter'] == L)
        out.append(f'<section class="lgroup"><div class="L">{L}</div><ul class="wl">{items}</ul></section>')
    out.append('</div></div>')
    return ''.join(out)


def build_site(data, page, site_dir, base):
    entries = data['entries']
    ids = src_ids(data['sources'], data.get('rst'))
    style = re.search(r'<style>(.*?)</style>', page, re.S).group(1)
    fonts = re.search(r'<link rel="stylesheet" href="(https://fonts\.googleapis\.com[^"]+)">', page).group(1)
    os.makedirs(os.path.join(site_dir, 'assets'), exist_ok=True)
    os.makedirs(os.path.join(site_dir, 'w'), exist_ok=True)
    open(os.path.join(site_dir, 'assets', 'site.css'), 'w', encoding='utf-8').write(style.strip() + '\n')

    # главная страница: фрагмент приложения + заголовок + статический словник для поисковиков
    body = page
    body = re.sub(r'<title>.*?</title>\s*', '', body, count=1, flags=re.S)
    body = re.sub(r'<link rel="preconnect"[^>]*>\s*', '', body)
    body = re.sub(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com[^"]+">\s*', '', body, count=1)
    body = re.sub(r'<style>.*?</style>\s*', '', body, count=1, flags=re.S)
    body = body.replace('<div id="view" class="page"></div>', f'<div id="view" class="page">{static_index(entries)}</div>', 1)
    ld = {'@context': 'https://schema.org', '@type': 'DefinedTermSet', 'name': SITE_NAME,
          'description': SITE_DESC, 'inLanguage': ['ru', 'ddn'], 'url': base}
    idx = head(f'{SITE_NAME} — русско-дендийский словарь', SITE_DESC, base, 'assets/site.css', fonts,
               extra=f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>')
    open(os.path.join(site_dir, 'index.html'), 'w', encoding='utf-8').write(idx + body + '\n</body>\n</html>\n')

    # страницы слов
    pid_entries = {}
    for e in entries:
        for x in examples_of(e):
            lst = pid_entries.setdefault(x['pid'], [])
            if e not in lst: lst.append(e)
    keep = set()
    for i, e in enumerate(entries):
        prev = entries[i - 1] if i > 0 else None
        nxt = entries[i + 1] if i + 1 < len(entries) else None
        first = e['variants'][0]['form'] if e['variants'] else ''
        title = f'{e["title"]} — {first} · {SITE_NAME}' if first else f'{e["title"]} · {SITE_NAME}'
        url = f'{base}w/{e["n"]}.html'
        term = {'@context': 'https://schema.org', '@type': 'DefinedTerm', 'name': e['title'],
                'description': entry_desc(e), 'url': url,
                'inDefinedTermSet': {'@type': 'DefinedTermSet', 'name': SITE_NAME, 'url': base}}
        if e['variants']:
            term['alternateName'] = all_forms(e)
        doc = (head(title, entry_desc(e), url, '../assets/site.css', fonts,
                    extra=f'<script type="application/ld+json">{json.dumps(term, ensure_ascii=False)}</script>')
               + header('../')
               + f'<main class="wrap"><div class="page">{entry_html(e, ids, prev, nxt, pid_entries, data.get('plinks'))}</div></main>\n'
               + '<footer><div class="wrap">Свод не является нормативным словарём языка.'
               + (f' Данные документа на {e_(data.get("built"))}.' if data.get('built') else '')
               + '</div></footer>\n</body>\n</html>\n')
        name = f'{e["n"]}.html'; keep.add(name)
        open(os.path.join(site_dir, 'w', name), 'w', encoding='utf-8').write(doc)
    for f in os.listdir(os.path.join(site_dir, 'w')):
        if f.endswith('.html') and f not in keep:
            os.remove(os.path.join(site_dir, 'w', f))

    today = datetime.date.today().isoformat()
    urls = [base] + [f'{base}w/{e["n"]}.html' for e in entries]
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sm += ''.join(f'  <url><loc>{e_(u)}</loc><lastmod>{today}</lastmod></url>\n' for u in urls) + '</urlset>\n'
    open(os.path.join(site_dir, 'sitemap.xml'), 'w', encoding='utf-8').write(sm)
    open(os.path.join(site_dir, 'robots.txt'), 'w', encoding='utf-8').write(f'User-agent: *\nAllow: /\n\nSitemap: {base}sitemap.xml\n')
    open(os.path.join(site_dir, '.nojekyll'), 'w').close()
