"""Сборка статического сайта для GitHub Pages: полноценный index.html, страницы слов, карта сайта."""
import os, re, json, html, datetime

SITE_NAME = 'Словарь денди'
SITE_DESC = ('Русско-дендийский словарь: 207 значений списка Сводеша и служебные слова языка денди '
             '(сонгай северного Бенина) — письменные варианты с источниками, примеры употребления, грамматика.')
RESET = (':root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
         'body{margin:0}img{max-width:100%}[hidden]{display:none!important}')
ALPHA = 'АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЭЮЯ'

e_ = lambda s: html.escape(str(s or ''), quote=True)


def plural(n, a, b, c):
    m10, m100 = n % 10, n % 100
    return a if m10 == 1 and m100 != 11 else b if 2 <= m10 <= 4 and not 12 <= m100 <= 14 else c


def src_ids(sources):
    ids = {}
    for i, s in enumerate(sources):
        for c in re.split(r'[ /—]+', s['code']):
            if re.fullmatch(r'[A-Z0-9]+', c):
                ids[c] = f'src{i}'
        if s['code'].startswith('T68'): ids['T68/72'] = f'src{i}'
        if s['code'].startswith('RST'): ids['RST'] = f'src{i}'
    return ids


def link_src(text, ids, prefix):
    t = e_(text)
    return re.sub(r'\b(T68/72|NT18|NT95|AL65|AL64|COV|CAL|CFA|ANT|SM19|N78|N89|G88|GYK|RST|AT|AZ|H)\b',
                  lambda m: f'<a class="code" href="{prefix}#{ids[m[1]]}">{m[1]}</a>' if m[1] in ids else m[1], t)


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
      <a href="{prefix}#dendi">Денди → русский</a>
      <a href="{prefix}#grammar">Грамматика</a>
      <a href="{prefix}#sources">Источники</a>
      <a href="{prefix}#about">Как пользоваться</a>
    </nav>
  </div>
  <div class="weave" aria-hidden="true"></div>
</header>
'''


def entry_desc(e):
    if e.get('unestablished'):
        return f'{e["title"]} на языке денди: практическое написание пока не установлено. Научные указатели для сверки — в словаре денди.'
    forms = ', '.join(dict.fromkeys(f['form'] for f in e['forms']))
    n = len(e['examples'])
    word = 'контекст' if e['suppl'] else 'пример'
    return f'{e["title"]} на языке денди: {forms}. {n} {plural(n, word, word + "а", word + "ов")} употребления с источниками.'[:300]


def entry_html(e, ids, prev, nxt):
    p = '../'
    if e['suppl']:
        meta = f'<span>№ {e["n"]}</span><span>{e_(e.get("label"))}</span>'
    else:
        tag = ''
        if e.get('unestablished'): tag = '<span class="tag warn">написание не установлено</span>'
        elif e.get('few'): tag = f'<span class="tag warn">примеров: {e["count"]}</span>'
        meta = f'<span>№ {e["n"]}</span><span>Сводеш № {e["swadesh"]}</span><span>Примеров: {e["count"]}</span>{tag}'
    parts = [f'<div class="crumbs"><a href="{p}">Словник</a><span>›</span><a href="{p}#l{ALPHA.index(e["letter"]) if e["letter"] in ALPHA else 0}">{e_(e["letter"])}</a></div>',
             f'<div class="entry-head"><h1>{e_(e["title"])}</h1><div class="meta">{meta}</div></div>']
    if e.get('unestablished'):
        parts.append(f'<div class="box warn"><span class="label">Написание не установлено</span>{e_(e["unestablished"])}</div>')
    if e['forms']:
        lis = ''.join(f'<li><span class="fw" lang="ddn">{e_(f["form"])}</span><span class="fs">{link_src(f["sources"], ids, p) if f["sources"] else ""}</span>'
                      + (f'<span class="fn">{e_(f["note"])}</span>' if f['note'] else '') + '</li>' for f in e['forms'])
        parts.append(f'<section class="stack"><span class="label">{"Форма" if e["suppl"] else "Письменные варианты"}</span><ul class="forms">{lis}</ul></section>')
    if e.get('meaning'):
        parts.append(f'<div class="box"><span class="label">Значение и ограничения</span>{e_(e["meaning"])}</div>')
    if e['examples']:
        lis = []
        for x in e['examples']:
            body = ''
            if x['text']: body += f'<span class="dt" lang="ddn">{e_(x["text"])}</span>'
            if x['gloss']:
                gt = ''
                if x['text']: gt = f'<span class="gt">{"Рус. параллельный контекст" if x["gloss_type"] == "rst" else "Пояснение"}</span>'
                body += f'<span class="gl">{gt}{e_(x["gloss"])}</span>'
            body += f'<span class="src">{link_src(x["source"], ids, p)}</span>'
            lis.append(f'<li><span class="k">{x["k"]})</span><div class="body">{body}</div></li>')
        parts.append(f'<section class="stack"><span class="label">{"Контексты" if e["suppl"] else "Примеры"} · {len(e["examples"])}</span><ol class="ex">{"".join(lis)}</ol></section>')
    if e.get('index_sci') or e.get('index_extra'):
        s = '<section class="stack small"><span class="label">Указатели для сверки</span>'
        if e.get('index_sci'): s += f'<p><span class="muted">Научный указатель.</span> {link_src(e["index_sci"], ids, p)}</p>'
        if e.get('index_extra'): s += f'<p><span class="muted">Дополнительный указатель.</span> {link_src(e["index_extra"], ids, p)}</p>'
        parts.append(s + '</section>')
    parts.append(f'<p><a href="{p}#w{e["n"]}">Открыть статью в интерактивном словаре с поиском →</a></p>')
    pager = ''
    if prev: pager += f'<a href="{prev["n"]}.html"><small>← предыдущая</small>{e_(prev["title"])}</a>'
    if nxt: pager += f'<a class="next" href="{nxt["n"]}.html"><small>следующая →</small>{e_(nxt["title"])}</a>'
    parts.append(f'<nav class="pager">{pager}</nav>')
    return '<article class="stack" style="gap:22px">' + '\n'.join(parts) + '</article>'


def sort_key(e):
    return (e['suppl'], e['title'].lower().replace('ё', 'е'))


def static_index(entries):
    letters = [L for L in ALPHA if any(e['letter'] == L for e in entries)]
    out = ['<div class="stack"><h1>Русско-дендийский словарь</h1>',
           f'<p class="lead">{e_(SITE_DESC)}</p><div class="letters">']
    for L in letters:
        items = ''.join(
            f'<li><a href="w/{e["n"]}.html">{e_(e["title"])}</a>'
            + ('<span class="none">—</span>' if e.get('unestablished') else f'<span class="f" lang="ddn">{e_(", ".join(f["form"] for f in e["forms"][:2]))}</span>')
            + '</li>' for e in sorted([e for e in entries if e['letter'] == L], key=sort_key))
        out.append(f'<section class="lgroup"><div class="L">{L}</div><ul class="wl">{items}</ul></section>')
    out.append('</div></div>')
    return ''.join(out)


def build_site(data, page, site_dir, base):
    entries = data['entries']
    ids = src_ids(data['sources'])
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
    keep = set()
    for i, e in enumerate(entries):
        prev = entries[i - 1] if i > 0 else None
        nxt = entries[i + 1] if i + 1 < len(entries) else None
        first = e['forms'][0]['form'] if e['forms'] else ''
        title = f'{e["title"]} — {first} · {SITE_NAME}' if first else f'{e["title"]} · {SITE_NAME}'
        url = f'{base}w/{e["n"]}.html'
        term = {'@context': 'https://schema.org', '@type': 'DefinedTerm', 'name': e['title'],
                'description': entry_desc(e), 'url': url,
                'inDefinedTermSet': {'@type': 'DefinedTermSet', 'name': SITE_NAME, 'url': base}}
        if e['forms']:
            term['alternateName'] = list(dict.fromkeys(f['form'] for f in e['forms']))
        doc = (head(title, entry_desc(e), url, '../assets/site.css', fonts,
                    extra=f'<script type="application/ld+json">{json.dumps(term, ensure_ascii=False)}</script>')
               + header('../')
               + f'<main class="wrap"><div class="page">{entry_html(e, ids, prev, nxt)}</div></main>\n'
               + '<footer><div class="wrap">Свод не является нормативным словарём языка. '
               + f'{e_(data["meta"]["updated"])}</div></footer>\n</body>\n</html>\n')
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
