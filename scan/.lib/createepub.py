#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import collections
import datetime
import io
import json
import logging
import os.path
import re
from xml.dom import minidom
import zipfile


"""
# workaround to make keep attribute orders
import functools

def DecorateElement__init__(func):
    @functools.wraps(func)
    def wrap(self, *args, **kwargs):
        ret = func(self, *args, **kwargs)
        self._attrs = collections.OrderedDict()
        return ret
    return wrap


def DecorateElement_get_attributes(func):
    @functools.wraps(func)
    def wrap(self, *args, **kwargs):
        ret = func(self, *args, **kwargs)
        return NoSortKeyClass(ret)
    return wrap


class NoSortKeyClass(object):
    # keys is read only and cannot be replaced
    def __init__(self, base):
        self._Base = base

    def __getattr__(self, attr):
        if attr == 'keys':
            return (lambda *args, **kwargs: NoSortClass(self._Base.keys(*args, **kwargs)))
        return getattr(self._Base, attr)

    def __getitem__(self, *args, **kwargs):
        return self._Base.__getitem__(*args, **kwargs)


class NoSortClass(object):
    # sort is read only and cannot be replaced
    def __init__(self, base):
        self._Base = base

    def __getattr__(self, attr):
        if attr == 'sort':
            return (lambda *args, **kwargs: None)
        return getattr(self._Base, attr)

    def __iter__(self, *args, **kwargs):
        return self._Base.__iter__(*args, **kwargs)

    def __next__(self, *args, **kwargs):
        return self._Base.__next__(*args, **kwargs)

minidom.Element.__init__ = DecorateElement__init__(minidom.Element.__init__)
minidom.Element._get_attributes = DecorateElement_get_attributes(minidom.Element._get_attributes)
"""


class ZipToKepubEpub(object):
    VERSION = 1559310345

    def __init__(self, optimizer):
        self._Logger = logging.getLogger(self.__class__.__name__)
        self._count = 0
        self._Optimizer = optimizer

    def __call__(self, file, toDir, opts):
        fromFile = file['path']
        filename = file['basename'] + '.kepub.epub'
        toFile = os.path.join(toDir, filename)

        if os.path.exists(toFile):
            return {
                'filename': filename,
                'path': toFile,
            }
            # 2021-11-08 新規生成中止
            toStat = os.stat(toFile)
            if toStat.st_mtime > self.VERSION and file.get('mtime', 0) > 0 and toStat.st_mtime >= file['mtime']:
                return {
                    'filename': filename,
                    'path': toFile,
                }

        # 2021-11-08 新規生成中止
        return None

        only = getattr(opts, 'only', None)
        if only and not fromFile.startswith(only):
            return None

        maxCount = getattr(opts, 'max', -1)
        if maxCount >= 0 and self._count >= maxCount:
            return None
        self._count = self._count + 1

        self._Logger.info('Converting %s -> %s', fromFile, toFile)

        if not os.path.exists(toDir):
            self._Logger.info('Creating: %s', toDir)
            os.makedirs(toDir)

        tmpFile = toFile + '.tmp'
        with zipfile.ZipFile(fromFile, 'r') as rh, zipfile.ZipFile(tmpFile, 'w') as wh:
            wh.writestr(
                'mimetype',
                'application/epub+zip',
                compress_type=zipfile.ZIP_STORED,
            )
            wh.writestr(
                'META-INF/container.xml',
                self._CreateContainer(),
            )
            fileList = []

            self._Optimizer.reset()
            if self._Optimizer.need_prescan():
                for f in sorted(rh.infolist(), key=(lambda x: x.filename)):
                    if f.filename.endswith('/'):
                        continue
                    basename = f.filename.split('/')[-1]
                    ext = os.path.splitext(basename)[1]
                    if ext.lower() not in ('.jpg', '.jpeg'):
                        continue
                    self._Optimizer.prescan(basename, io.BytesIO(rh.read(f)))
            self._Optimizer.prepare_optimize()

            metadataFile = None

            for f in sorted(rh.infolist(), key=(lambda x: x.filename)):
                if f.filename.endswith('/'):
                    continue
                basename = f.filename.split('/')[-1]
                if basename == 'metadata.json':
                    metadataFile = f
                    continue
                ext = os.path.splitext(basename)[1]
                if ext.lower() not in ('.jpg', '.jpeg'):
                    self._Logger.warn('Skipped: %s', f.filename)
                    continue
                filenameInZip = 'content/' + basename
                fileList.append(filenameInZip)
                w = io.BytesIO()
                self._Optimizer.optimize(
                    basename,
                    io.BytesIO(rh.read(f)),
                    w,
                )
                wh.writestr(
                    filenameInZip,
                    w.getvalue(),
                )

            metadata = {}
            if metadataFile is not None:
                metadata = json.loads(rh.read(metadataFile))

            wh.writestr(
                'metadata.opf',
                self._CreateMetadata(file, fileList, metadata),
            )

        os.rename(tmpFile, toFile)
        return {
            'filename': filename,
            'path': toFile,
        }

    def _CreateContainer(self):
        doc = minidom.Document()

        container = doc.createElement('container')
        container.setAttribute('version', '1.0')
        container.setAttribute('xmlns', 'urn:oasis:names:tc:opendocument:xmlns:container')
        doc.appendChild(container)

        rootfiles = doc.createElement('rootfiles')
        container.appendChild(rootfiles)

        metadata = doc.createElement('rootfile')
        metadata.setAttribute('full-path', 'metadata.opf')
        metadata.setAttribute('media-type', 'application/oebps-package+xml')
        rootfiles.appendChild(metadata)

        return doc.toprettyxml()

    def _CreateMetadata(self, file, fileList, metadataDefaults):
        author = file['author']
        title = file['title']

        if isinstance(author, str):
            author = author.decode('utf-8')
        if isinstance(title, str):
            title = title.decode('utf-8')

        doc = minidom.Document()

        package = doc.createElement('package');
        package.setAttribute('xmlns', 'http://www.idpf.org/2007/opf')
        package.setAttribute('version', '2.0')
        package.setAttribute('unique-identifier', 'calibre_id')
        doc.appendChild(package)

        metadata = doc.createElement('metadata')
        metadata.setAttribute('xmlns:dc', 'http://purl.org/dc/elements/1.1/')
        metadata.setAttribute('xmlns:opf', 'http://www.idpf.org/2007/opf')
        package.appendChild(metadata)

        dc_title = doc.createElement('dc:title')
        dc_title.appendChild(doc.createTextNode(title))
        metadata.appendChild(dc_title)

        if author:
            dc_creator = doc.createElement('dc:creator')
            dc_creator.setAttribute('opf:role' ,'aut')
            dc_creator.setAttribute('opf:file-as' ,author)
            dc_creator.appendChild(doc.createTextNode(author))
            metadata.appendChild(dc_creator)

        dc_date = doc.createElement('dc:date')
        dc_date.appendChild(doc.createTextNode(
            datetime.datetime.utcfromtimestamp(file['mtime']).strftime('%Y-%m-%dT%H:%M:%SZ')
        ))
        metadata.appendChild(dc_date)

        dc_language = doc.createElement('dc:language')
        dc_language.appendChild(doc.createTextNode(metadataDefaults.get('language', 'ja')))
        metadata.appendChild(dc_language)

        manifest = doc.createElement('manifest')
        package.appendChild(manifest)

        spine = doc.createElement('spine')
        spine.setAttribute(
            'page-progression-direction',
            metadataDefaults.get('page-progression-direction', 'rtl'),
        )
        package.appendChild(spine)

        for idx, file in enumerate(sorted(fileList), start=1):
            id = 'id{0}'.format(idx)
            item = doc.createElement('item')
            item.setAttribute('id', id)
            item.setAttribute('href', file)
            item.setAttribute('media-type', 'image/jpeg')
            if idx == 1:
                item.setAttribute('properties', 'cover-image')
            manifest.appendChild(item)

            itemref = doc.createElement('itemref')
            itemref.setAttribute('idref', id)
            spine.appendChild(itemref)

        return doc.toprettyxml(encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', dest='verbose', action='count', default=0)
    parser.add_argument('zipfile')
    opts = parser.parse_args()
    level = logging.INFO
    if opts.verbose:
        level = logging.DEBUG
    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s',
        level=level,
    )
    REG_AUTH_TITLE = re.compile(r'^(\[([^\]]+)\]\s*(.*))\.(?:zip|ZIP)$')
    m = REG_AUTH_TITLE.match(opts.zipfile)
    if not m:
        logging.error('Invalid zip file: %s', opts.zipfile)
    file =  {
        'path': opts.zipfile,
        'basename': m.group(1),
        'author': m.group(2),
        'title': m.group(3),
        'mtime': 0,
    }
    import imageoptimizer
    optimizer = imageoptimizer.ImageOptimizer(
        whitespace=imageoptimizer.ImageOptimizer.WHITESPACE_CLEAN,
    )
    copier = ZipToKepubEpub(optimizer)
    copier(file, '.', opts)
