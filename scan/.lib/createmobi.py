#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import calendar
import datetime
import io
import json
import logging
import os.path
import re
from xml.dom import minidom
import subprocess
import tempfile
import time
import zipfile


class ZipToMobi(object):
    VERSION = 1559310345
    SIZE = (758, 1024)

    def __init__(self, optimizer, skip=False, preseveEpub=False, skipMobi=False, s3Bucket=None):
        self._Logger = logging.getLogger(self.__class__.__name__)
        self._count = 0
        self._skip = skip
        self._Optimizer = optimizer
        self._PreserveEpub = preseveEpub
        self._SkipMobi = skipMobi
        self._S3Bucket = s3Bucket

        self._kindlegen = self.find_executable('kindlegen')

        self._SRCSStripper = None
        try:
            # https://www.mobileread.com/forums/showthread.php?t=96903
            # https://pypi.org/project/kindlestrip/
            import kindlestrip # type: ignore
            self._SRCSStripper = kindlestrip.SRCSStripper
        except ImportError:
            self._Logger.info('kindlestrip was not found. SRCS strip feature is disabled.')

    def find_executable(self, executable):
        if os.environ.get('PATHEXT'):
            pathexts = os.environ['PATHEXT'].split(os.pathsep)
        else:
            pathexts = []

        dirname = os.path.dirname(__file__)
        if not dirname:
            dirname = '.'
        test = self.find_executable_with_ext(os.path.join(dirname, executable), pathexts)
        if test:
            return test

        paths = os.environ['PATH'].split(os.pathsep)
        for path in paths:
            test = self.find_executable_with_ext(os.path.join(path, executable), pathexts)
            if test:
                return test

        return executable

    def find_executable_with_ext(self, test, pathexts):
        if os.path.isfile(test):
            return test
        for ext in pathexts:
            test_ext = test + ext
            if os.path.isfile(test_ext):
                return test_ext
        return None

    def __call__(self, file, toDir, opts):
        fromFile = file['path']
        filename = file['basename'] + '.mobi'
        toFile = os.path.join(toDir, filename)

        if os.path.exists(toFile):
            toStat = os.stat(toFile)
            if toStat.st_mtime > self.VERSION and file.get('mtime', 0) > 0 and toStat.st_mtime >= file['mtime']:
                return {
                    'filename': filename,
                    'path': toFile,
                }

        if self._skip:
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
            self._Logger.info('  Creating: %s', toDir)
            os.makedirs(toDir)

        epubScanStartTime = time.time()
        fd, tmpEpubFile = tempfile.mkstemp(suffix='.epub')
        os.close(fd)
        with zipfile.ZipFile(fromFile, 'r') as rh, zipfile.ZipFile(tmpEpubFile, 'w') as wh:
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
            metadataFile = None
            metadata = {}

            # self._Optimizer.reset(self.SIZE)
            self._Optimizer.reset()
            if self._Optimizer.need_prescan():
                for f in sorted(rh.infolist(), key=(lambda x: x.filename)):
                    if f.filename.endswith('/'):
                        continue
                    basename = f.filename.split('/')[-1]
                    if basename == 'metadata.json':
                        metadataFile = f
                        continue
                    ext = os.path.splitext(basename)[1]
                    if ext.lower() not in ('.jpg', '.jpeg'):
                        continue
                    self._Optimizer.prescan(basename, io.BytesIO(rh.read(f)))

            if metadataFile is not None and not metadata:
                metadata = json.loads(rh.read(metadataFile))
                if metadata.get('page-progression-direction') == 'ltr':
                    self._Optimizer.setLTR()

            self._Optimizer.prepare_optimize()

            epubGenerateStartTime = time.time()
            for f in rh.infolist():
                if f.filename.endswith('/'):
                    continue
                basename = f.filename.split('/')[-1]
                if basename == 'metadata.json':
                    metadataFile = f
                    continue
                ext = os.path.splitext(basename)[1]
                if ext.lower() not in ('.jpg', '.jpeg'):
                    self._Logger.warning('  Skipped: %s', f.filename)
                    continue
                if self._Optimizer.divideMode:
                    w = (io.BytesIO(), io.BytesIO())
                    self._Optimizer.optimize(
                        basename,
                        io.BytesIO(rh.read(f)),
                        w,
                    )
                    basenamebase = os.path.splitext(basename)[0]
                    for index in (0, 1):
                        basename = '{0}.{1}{2}'.format(basenamebase, index + 1, ext)
                        filenameInZip = 'content/' + basename
                        fileList.append(filenameInZip)
                        wh.writestr(
                            filenameInZip,
                            w[index].getvalue(),
                        )
                else:
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

            if metadataFile is not None and not metadata:
                metadata = json.loads(rh.read(metadataFile))
                if metadata.get('page-progression-direction') == 'ltr':
                    self._Optimizer.setLTR()
            self._Optimizer.report()

            wh.writestr(
                'metadata.opf',
                self._CreateMetadata(file, fileList, metadata),
            )

        mobiGenerateStartTime = time.time()
        tmpMobiFile = tmpEpubFile + '.mobi'
        tmpFileToUse = tmpEpubFile
        if os.path.isdir('/cygdrive'):
            tmpFileToUse = subprocess.check_output([
                'cygpath',
                '-w',
                tmpEpubFile,
            ]).rstrip()

        if not self._SkipMobi:
            self._Logger.debug('  Launching %s', self._kindlegen)
            cmd = [
                self._kindlegen,
                tmpFileToUse,
                '-c0',
                '-locale',
                'ja',
                '-o',
                os.path.basename(tmpMobiFile),
            ]
            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = p.communicate()
            if p.returncode != 0:
                self._Logger.error(
                    'command failed with %s: %s',
                    p.returncode,
                    cmd,
                )
                self._Logger.error('stdout from kindlegen: %s', stdout)
                self._Logger.error('stderr from kindlegen: %s', stderr)
                raise('Command failed with {0}: {1}'.format(p.returncode, cmd))

            self._Logger.debug('stdout from kindlegen: %s', stdout)
            self._Logger.debug('stderr from kindlegen: %s', stderr)

            with open(tmpMobiFile, 'rb') as fh:
                data = fh.read()
            if self._SRCSStripper:
                stripper = self._SRCSStripper(data)
                data = stripper.getResult()
            # cross-device link にならないよう別名で書き出し
            toFileTmp = toFile + '.tmp'
            with open(toFileTmp, 'wb') as fh:
                fh.write(data)

            os.rename(toFileTmp, toFile)

        if not self._PreserveEpub:
            os.unlink(tmpEpubFile)
        else:
            os.rename(tmpEpubFile, toFile + '.epub')

        mobiGenerateEndTime = time.time()

        self._Logger.info(
            '  Done took %ss (Prescan: %ss,  Epub: %ss Epub to Mobi: %ss',
            int(mobiGenerateEndTime - epubScanStartTime),
            int(epubGenerateStartTime - epubScanStartTime),
            int(mobiGenerateStartTime - epubGenerateStartTime),
            int(mobiGenerateEndTime - mobiGenerateStartTime),
        )

        if self._S3Bucket:
            self._UploadToS3(self._S3Bucket, file)

        return {
            'filename': filename,
            'path': toFile,
        }

    def _UploadToS3(self, bucket, file):
        object = bucket.Object(file['relative'])
        if not self._CheckUploadToS3(object, file):
            return
        self._Logger.info('  Uploading to s3://%s/%s...', object.bucket_name, object.key)
        startTime = time.time()
        import botocore
        retry = 0
        while True:
            try:
                object.upload_file(file['path'])
            except botocore.exceptions.ClientError as e:
                if retry < 3:
                    retry = retry + 1
                    self._Logger.warning(
                        '  Uploading to s3://%s/%s failed. Retrying...: %s',
                        object.bucket_name,
                        object.key,
                        e,
                    )
                    continue
                raise
            break
        endTime = time.time()
        self._Logger.info(
            '  Done took %ss',
            int(endTime - startTime),
        )

    def _CheckUploadToS3(self, object, file):
        self._Logger.debug('  Checking s3://%s/%s...', object.bucket_name, object.key)
        import botocore
        retry = 0
        while True:
            try:
                object.load()
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == '404':
                    self._Logger.debug('  Not found')
                    return True
                if retry < 3:
                    retry = retry + 1
                    self._Logger.warning(
                        '  Checking s3://%s/%s failed. Retrying...: %s',
                        object.bucket_name,
                        object.key,
                        e,
                    )
                    continue
                raise
            break
        s3mtime = int(calendar.timegm(object.last_modified.utctimetuple()))
        if file['mtime'] <= s3mtime:
            self._Logger.debug(
                '  S3 is newer: S3 %s > filesystem %s',
                s3mtime,
                file['mtime'],
            )
            return False
        self._Logger.info(
            '  S3 is older: S3 %s < filesystem %s',
            s3mtime,
            file['mtime'],
        )
        return True

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

        # To have show full-sized images on Kindles
        meta_fields = {
            'book-type': 'comic',
            'fixed-layout': 'true',
            # サイズの指定は必須。
            # 一方、実際には画像サイズで自動調整されるので
            # ここで指定するサイズには意味がない様子。
            'original-resolution': '{0}x{1}'.format(*self.SIZE),
        }
        for key, value in meta_fields.items():
            meta = doc.createElement('meta')
            meta.setAttribute('name', key)
            meta.setAttribute('content', value)
            metadata.appendChild(meta)

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
    parser.add_argument('-m', dest='mobi', action='store_true', default=False)
    parser.add_argument('-s', dest='s3', action='store_true', default=False)
    parser.add_argument('zipfile')
    opts = parser.parse_args()
    level = logging.INFO
    if opts.verbose:
        level = logging.DEBUG
    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s',
        level=level,
    )
    for name in ['boto3', 'botocore', 's3transfer', 'urllib3']:
        logging.getLogger(name).setLevel(logging.WARNING)
    REG_AUTH_TITLE = re.compile(r'^(\[([^\]]+)\]\s*(.*))\.(?:zip|ZIP)$')
    m = REG_AUTH_TITLE.match(os.path.basename(opts.zipfile))
    if not m:
        logging.error('Invalid zip file: %s', opts.zipfile)
    stat = os.stat(opts.zipfile)
    file =  {
        'path': opts.zipfile,
        'relative': os.path.join(m.group(2), os.path.basename(opts.zipfile)),
        'basename': m.group(1),
        'author': m.group(2),
        'title': m.group(3),
        'mtime': stat.st_mtime,
    }
    import imageoptimizer
    optimizer = imageoptimizer.ImageOptimizer(
        whitespace=imageoptimizer.ImageOptimizer.WHITESPACE_CLEAN,
        verboseBound=True,
    )
    import s3
    if opts.s3:
        s3info = s3.getS3Info()
    else:
        s3info = s3.S3Info()
    copier = ZipToMobi(
        optimizer,
        skipMobi=(not opts.mobi),
        s3Bucket=s3info.getBucket('novel'),
    )
    copier(file, '.', opts)
