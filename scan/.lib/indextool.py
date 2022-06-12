#!/usr/bin/python
# -*- coding: utf-8 -*-

import cgi
import json
import logging
import os
import re
import sys
import urllib
import urllib2


class Indexer(object):
    AUTHOR_EXTRACTOR = re.compile(r'^\[(.*?)(?:＋|×|・|＆|[\+\]])')
    RUBY_EXTRACTOR = [
        re.compile(r"'''.*?'''(?:（|[\(])(.*?)(?:、|）|[\)])"),
        re.compile(r"\|name=\{\{ruby\|[^\|]*\|(.*?)\}\}"),
    ]
    LAST = 'ヾ'

    def __init__(self, file=None):
        if not file:
            file = os.path.join(os.path.dirname(__file__), 'author.json')
        self._File = file
        if os.path.exists(self._File):
            self._Cache = json.load(open(self._File, 'rb'))
        else:
            self._Cache = {}
        self._modified = False
        self._Logger = logging.getLogger(self.__class__.__name__)

    def __call__(self, name, is_dir=False):
        return (self._resolve_ruby(name, is_dir), name)

    def _resolve_ruby(self, name, is_dir):
        match = self.AUTHOR_EXTRACTOR.search(name)
        if match:
            author = match.group(1).replace(' ', '')
            doubt = False
        elif is_dir:
            # フォルダ名=作者名とする
            author = name
            doubt = True
            #return self.LAST
        else:
            return self.LAST

        author = author.replace(' ', '')
        cache = self._get_cache(author, doubt)
        if cache.get('ruby'):
            return cache['ruby'].encode('utf-8')
        else:
            return self.LAST

    def _get_cache(self, author, doubt):
        authorUnicode = author.decode('utf-8')
        if authorUnicode in self._Cache:
            return self._Cache[authorUnicode]

        # 未知の著者名
        if re.search(ur'^[\u3041-\u30feA-Z\x20-\x7f]*$', authorUnicode):
            # ひらがな、カタカナ、半角文字だけの構成
            # ア-ヴ → あ-ゔ
            authorUnicode = re.sub(
                ur'([\u30a2-\u30f4])',
                (lambda x: unichr(ord(x.group(0)) - 96)),
                authorUnicode,
            )
            return {
                'ruby': authorUnicode,
            }
        else:
            # インターネットから取得
            url = 'https://ja.wikipedia.org/w/api.php'
            query = {
                'format': 'json',
                'action': 'query',
                'prop': 'revisions',
                'rvprop': 'content',
                'titles': author,
            }
            url = '{0}?{1}'.format(url, urllib.urlencode(query))
            self._Logger.debug('Resolving %s by %s', author, url)
            cache = {
                'ruby': '',
                'url': url,
            }
            try:
                response = urllib2.urlopen(url)
                body = response.read()
                self._Logger.debug('Response: %s', body)
                data = json.loads(body, 'utf-8')
                pages = data['query']['pages']
                page = pages[pages.keys()[0]]
                if 'missing' in page:
                    raise Exception('Not found for key {0}'.format(author))
                content = page['revisions'][0]['*'].encode('utf-8')
                for r in self.RUBY_EXTRACTOR:
                    match = r.search(content)
                    if match:
                        break
                if not match:
                    raise Exception('Unexpected content for {0}: {1}'.format(author, content))
                cache['ruby'] = match.group(1).decode('utf-8')
            except Exception as e:
                if doubt:
                    # もともと人名か疑わしい
                    self._Logger.warn('Consider %s is not an author name', author)
                    return {}
                self._Logger.exception('Failed to resolve %s by %s', author, url)
                cache['exception'] = str(e).decode('utf-8')

        # カタカナをひらがなに変換
        cache['ruby'] = re.sub(
            ur'[\u30a1-\u30f6]',
            (lambda x: unichr(ord(x.group(0)[0]) - 0x60)),
            cache['ruby'],
        )

        self._Logger.info('Resolved: %s -> %s', author, cache['ruby'].encode('utf-8'))

        self._Cache[authorUnicode] = cache
        self._modified = True

        return cache

    def save(self):
        if not self._modified:
            return
        data = json.dumps(
            self._Cache,
            ensure_ascii=False,
            indent=4,
            sort_keys=True,
        )
        open(self._File, 'wb').write(data.encode('utf-8'))
        self._modified = False


class IndexScanner(object):
    # [著者] タイトル (巻数)
    FILENAME_PARSER = re.compile(r'^\[([^\]]+)\]\s*((.*?)\s*(\(.*?\))?)$')

    def __init__(self, indexer, extensions):
        self._Indexer = indexer
        self._Logger = logging.getLogger(self.__class__.__name__)
        self._ExtensionList = [ e.lower() for e in extensions ]
        self._Ignores = []
        file = os.path.join(os.path.dirname(__file__), 'ignores.txt')
        if os.path.exists(file):
          self._Ignores = [line.rstrip() for line in open(file).readlines()]

    def scan(self, generator, title, dir, controllerPath, opts):
        return self._scanImpl(generator, title, dir, '', controllerPath, opts)

    def _scanImpl(self, generator, title, root, relative, controllerPath, opts):
        if relative:
            dir = os.path.join(root, relative)
        else:
            dir = root

        self._Logger.debug('%s', dir)
        subdirList = []
        fileList = []
        fullFileList = []
        for entry in os.listdir(dir):
            if entry.startswith('.'):
                continue
            if relative:
                relativePath = os.path.join(relative, entry)
            else:
                relativePath = entry
            path = os.path.join(root, relativePath)
            if os.path.isdir(path):
                match = self.FILENAME_PARSER.search(entry)
                if match:
                    subdir = {
                        'filename': entry,
                        'index': self._Indexer(entry, is_dir=True),
                        'basename': entry,
                        'path': path,
                        'relative': relativePath,
                        'author': match.group(1),
                        'title': match.group(2),
                        'series': match.group(3),
                        'seq': match.group(4),
                    }
                else:
                    subdir = {
                        'filename': entry,
                        'index': self._Indexer(entry, is_dir=True),
                        'basename': entry,
                        'path': path,
                        'relative': relativePath,
                        'author': None,
                        'title': entry,
                        'series': entry,
                        'seq': None,
                    }
                subdirList.append(subdir)
            elif os.path.splitext(entry)[1].lower() in self._ExtensionList:
                stat = os.stat(path)
                basename = os.path.splitext(entry)[0]
                match = self.FILENAME_PARSER.search(basename)
                if match:
                    file = {
                        'filename': entry,
                        'index': self._Indexer(entry),
                        'basename': basename,
                        'path': path,
                        'relative': relativePath,
                        'author': match.group(1),
                        'title': match.group(2),
                        'series': match.group(3),
                        'seq': match.group(4),
                        'mtime': long(stat.st_mtime),
                    }
                else:
                    file = {
                        'filename': entry,
                        'index': self._Indexer(entry),
                        'basename': basename,
                        'path': path,
                        'relative': relativePath,
                        'author': None,
                        'title': basename,
                        'series': basename,
                        'seq': None,
                        'mtime': long(stat.st_mtime),
                    }
                fileList.append(file)

        for x in subdirList:
            if isinstance(self._Indexer, Indexer):
                x['ruby'] = x['index'][0].replace(' ', '')
        for x in fileList:
            if isinstance(self._Indexer, Indexer):
                x['ruby'] = x['index'][0].replace(' ', '')

        subdirList.sort(key=(lambda x: x['index']))
        fileList.sort(key=(lambda x: x['index']))

        newSubdirList = []
        for subdir in subdirList:
            result = self._scanImpl(
                generator,
                subdir['filename'],
                root,
                subdir['relative'],
                '../{0}'.format(controllerPath),
                opts,
            )
            if result is not None:
                fullFileList.extend([
                    {
                        'filename': os.path.join(subdir['filename'], file['filename']),
                        'index': file['index'],
                        'author': file['author'],
                        'title': file['title'],
                        'mtime': file['mtime'],
                    }
                    for file in result['fileList']
                ])
                del result['fileList']
                subdir.update(result)
                newSubdirList.append(subdir)
        subdirList = newSubdirList

        if not fileList and not subdirList:
            if os.path.basename(dir) in self._Ignores:
                return None
            self._Logger.info('No content: %s', dir)
            return None

        indexFile = os.path.join(dir, 'index.html')
        if not generator(indexFile, controllerPath, title, subdirList, fileList, opts):
            self._Logger.info('No content: %s', dir)
            return None

        fullFileList.extend([
            {
                'filename': file['filename'],
                'index': file['index'],
                'author': file['author'],
                'title': file['title'],
                'mtime': file['mtime'],
            }
            for file in fileList
        ])

        return {
            'mtime': max(
                [0]
                + [f['mtime'] for f in fileList]
                + [f['mtime'] for f in subdirList]
            ),
            'fileList': fullFileList,
        }


class IndexGenerator(object):
    def __init__(self):
        self._Logger = logging.getLogger(self.__class__.__name__)

    def __call__(self, indexFile, controllerPath, title, subdirList, fileList, opts):
        if not subdirList and not fileList:
            return False
        content = ''
        content += """
<html lang="ja">
<head>
	<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
	<title>{title}</title>
	<script src="{controllerPath}/jquery-3.2.1.js"></script>
	<!-- http://www.henryalgus.com/reading-binary-files-using-jquery-ajax/ -->
	<script src="{controllerPath}/jquery.binarytransport.js"></script>
	<script src="{controllerPath}/jszip.js"></script>
	<script src="{controllerPath}/FileSaver.js"></script>
	<script src="{controllerPath}/moment.js"></script>
	<script src="{controllerPath}/filelist.js"></script>
	<link rel="stylesheet" href="{controllerPath}/style.css" />
	<link rel="icon" href="{controllerPath}/favicon.ico" />
</head>
<body>
<ul>
""".lstrip().format(
            title=cgi.escape(title),
            controllerPath=controllerPath,
        )

        for subdir in subdirList:
            content += '<li><a href="{subdirUrl}/index.html" bookdate="{bookdate}" ruby="{ruby}">{title}</a></li>\n'.format(
                title=cgi.escape(subdir['filename']),
                ruby=cgi.escape(subdir['ruby'] or ''),
                subdirUrl=urllib.quote(subdir['filename'], ''),
                bookdate=subdir['mtime'],
            )

        for file in fileList:
            content += '<li><a href="{fileUrl}" bookdate="{bookdate}" ruby="{ruby}">{title}</a></li>\n'.format(
                title=cgi.escape(file['basename']),
                ruby=cgi.escape(file['ruby'] or ''),
                fileUrl=urllib.quote(file['filename'], ''),
                bookdate=file['mtime'],
            )

        content += """
</ul>
</body>
</html>
""".lstrip()

        if not self.isDifferent(indexFile, content):
            return True
        if opts.dryrun:
            self._Logger.info('(dryrun) UPDATE: %s', indexFile)
            self._Logger.debug('CONTENTS:\n%s', content)
            return True
        if os.path.exists(indexFile):
            os.unlink(indexFile)
        try:
            with open(indexFile, 'wb') as f:
                f.write(content)
        except Exception:
            self._Logger.exception('subdir: %r, files: %r', subdirList, fileList)
            raise
        self._Logger.info('UPDATE %s', indexFile)
        return True

    def isDifferent(self, file, content):
        if not os.path.exists(file):
            return True
        with open(file, 'rb') as f:
            return f.read() != content


class CopyingIndexGenerator(IndexGenerator):
    def __init__(self, fromdir, todir, copier):
        self._Logger = logging.getLogger(self.__class__.__name__)
        self._Fromdir = fromdir
        self._Todir = todir
        self._Copier = copier

    def __call__(self, indexFile, controllerPath, title, subdirList, fileList, opts):
        toIndexFile = os.path.join(
            self._Todir,
            os.path.relpath(indexFile, self._Fromdir),
        )
        fromDir = os.path.dirname(indexFile)
        toDir = os.path.dirname(toIndexFile)
        newFileList = []
        for file in fileList:
            updates = []
            for copier in self._Copier:
                u = copier(
                    file,
                    toDir,
                    opts,
                )
                if u is None:
                    continue
                if u:
                    updates.append(u)
            if updates:
                for u in updates:
                    newfile = dict(file)
                    newfile.update(u)
                    newFileList.append(newfile)
        return super(CopyingIndexGenerator, self).__call__(
            toIndexFile,
            controllerPath,
            title,
            subdirList,
            newFileList,
            opts,
        )
