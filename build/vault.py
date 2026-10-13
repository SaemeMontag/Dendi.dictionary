"""Чтение хранилища Obsidian со словарём денди (только чтение).

Читаются только заметки для читателя: «Введение.md», «Грамматика/*.md», «Статьи/*.md»,
«Примеры/*.md», «Источники/*.md» (порядок источников — по «Источники/Указатель источников.md»).
Редакторская заметка, служебные заметки, папка «Перенос» и настройки не открываются вовсе.

Результат — последовательность строк (текст, ссылка) в том же виде, что и выгрузка
Google-документа, плюс ссылки слов из пословных разборов на статьи.
"""
import os, re

BLOCK_ID = re.compile(r'\s*\^[A-Za-z0-9-]+\s*$')
MD_LINK_LINE = re.compile(r'^\[([^\]]+)\]\(([^)\s]+)\)$')
WIKI = re.compile(r'\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]')
MD_LINK = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
EMBED = re.compile(r'^!\[\[Примеры/(П\d+)\]\]$')
EX_HEAD = re.compile(r'^Пример \d+ \(П\d+\) — ')
LINKED_HEAD = 'Полные примеры по ссылкам исходного разбора'


class VaultError(Exception):
    pass


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read().replace('\r', '').replace('﻿', '')


def _plain(line):
    """Markdown-строка → (текст, ссылка всей строки)."""
    line = BLOCK_ID.sub('', line).strip()
    m = MD_LINK_LINE.match(line)
    if m:
        return m[1].strip(), m[2]
    line = WIKI.sub(lambda m: (m[2] or os.path.basename(m[1])).strip(), line)
    line = MD_LINK.sub(lambda m: m[1], line)
    line = re.sub(r'^#{1,6}\s+', '', line)
    return line.strip(), ''


def _lines(path):
    out = []
    for raw in _read(path).split('\n'):
        if not raw.strip():
            continue
        out.append((raw.strip(), _plain(raw)))
    return out


def load(vault):
    need = ['Введение.md', 'Грамматика', 'Статьи', 'Примеры', 'Источники']
    missing = [n for n in need if not os.path.exists(os.path.join(vault, n))]
    if missing:
        raise VaultError('в хранилище нет: ' + ', '.join(missing))

    # примеры
    examples, plinks_raw = {}, {}
    for fn in os.listdir(os.path.join(vault, 'Примеры')):
        if not fn.endswith('.md'):
            continue
        pid = fn[:-3]
        body = []
        for raw, (text, url) in _lines(os.path.join(vault, 'Примеры', fn)):
            if raw.startswith('#') and _plain(raw)[0] == pid:
                continue
            if raw.startswith('## Статьи слов примера'):
                break
            if raw.startswith('Разбор по словам:'):
                plinks_raw[pid] = [((m[2] or os.path.basename(m[1])).strip(), m[1]) for m in WIKI.finditer(raw)]
            body.append((text, url))
        examples[pid] = body

    # статьи: номер из заголовка «# N. Название»
    arts = []
    title_to_n = {}
    for fn in os.listdir(os.path.join(vault, 'Статьи')):
        if not fn.endswith('.md'):
            continue
        ls = _lines(os.path.join(vault, 'Статьи', fn))
        if not ls:
            raise VaultError(f'пустая статья: {fn}')
        head = ls[0][1][0]
        m = re.match(r'^(\d+)\. ', head)
        if not ls[0][0].startswith('# ') or not m:
            raise VaultError(f'у статьи «{fn}» первая строка не вида «# N. Название»')
        arts.append((int(m[1]), fn, ls))
        title_to_n['Статьи/' + fn[:-3]] = int(m[1])
    arts.sort(key=lambda a: a[0])

    # статья: встраивание сразу после «Пример k (Пx) — …» раскрывается как обычный пример;
    # встраивание без такого заголовка — как «Пример по ссылке (Пx)»
    entry_lines = []
    for n, fn, ls in arts:
        prev_ex_head = None
        for raw, (text, url) in ls:
            em = EMBED.match(BLOCK_ID.sub('', raw).strip())
            if em:
                pid = em[1]
                if pid not in examples:
                    raise VaultError(f'в статье «{fn}» встраивание ![[Примеры/{pid}]] ведёт на несуществующую заметку')
                if prev_ex_head and f'({pid})' in prev_ex_head:
                    entry_lines += examples[pid]
                else:
                    entry_lines += [(f'Пример по ссылке ({pid})', '')] + examples[pid]
                prev_ex_head = None
                continue
            if raw.startswith('![['):
                raise VaultError(f'в статье «{fn}» встраивание не из папки «Примеры»: {raw[:60]}')
            prev_ex_head = text if EX_HEAD.match(text) else None
            entry_lines.append((text, url))

    # грамматика
    gram = []
    for fn in sorted(os.listdir(os.path.join(vault, 'Грамматика'))):
        if fn.endswith('.md'):
            gram += [p for _, p in _lines(os.path.join(vault, 'Грамматика', fn))]

    # источники в порядке указателя
    src_dir = os.path.join(vault, 'Источники')
    order = []
    idx = os.path.join(src_dir, 'Указатель источников.md')
    if os.path.exists(idx):
        order = [os.path.basename(m[1]) + '.md' for m in WIKI.finditer(_read(idx))]
    rest = sorted(f for f in os.listdir(src_dir) if f.endswith('.md') and f not in order and f != 'Указатель источников.md')
    srcs = []
    for fn in order + rest:
        p = os.path.join(src_dir, fn)
        if os.path.exists(p):
            srcs += [x for _, x in _lines(p)]

    intro = [p for _, p in _lines(os.path.join(vault, 'Введение.md'))]

    lines = [('Денди — русско-дендийский словарь и грамматика', ''),
             ('Редакторский раздел (в хранилище — отдельная заметка, не читается)', '')]
    lines += intro + gram + [('Словарные статьи', '')] + entry_lines
    lines += [('Источники и границы их использования', '')] + srcs

    plinks = {}
    for pid, pairs in plinks_raw.items():
        plinks[pid] = [[alias, title_to_n.get(target)] for alias, target in pairs]
    return lines, {'plinks': plinks}
