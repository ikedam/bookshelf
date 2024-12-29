#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import contextlib
import datetime
import io
import logging
import os.path
import re
import struct
import zipfile

import PIL.Image
import PIL.ImageChops
import PIL.ImageEnhance
import PIL.ImageFilter
import PIL.ImageOps


@contextlib.contextmanager
def NewStringIO():
    fh = io.StringIO()
    try:
        yield fh
    finally:
        fh.close()


class ExthTypes(object):
    Published = 106
    Creator = 100
    Language = 524
    Direction = 527
    Records = 125
    CoverOffset = 201
    ThumbOffset = 202

    ContainerId = 542
    PrimaryWritingMode = 525
    MetadataResourceURI = 129
    MetadataRecordOffset = 131
    HasFakeCover = 203
    

class _MobiBuilder(object):

    PALM_DOC_HEADER_LENGTH = 16
    MOBI_HEADER_LENGTH = 264
    MAX_TEXT_SIZE = 4096

    def __init__(self, file):
        self._file = file
        self._now = datetime.datetime.utcfromtimestamp(
            os.stat(self._file['path']).st_mtime
        )
        self._records = [None, ]
        self._image_files = []
        self._mobiheader = ''
        self._author = self._file['author']
        self._title = self._file['title']
        self._text_length = 0
        self._text_records = 0
        self._image_records = 0
        self._fcis_record_offset = 0xFFFFFFFF
        self._flis_record_offset = 0xFFFFFFFF

        self._encoded_title = self._title.encode('utf-8')

    def add_image_file(self, filename, data):
        self._image_files.append((filename, data))

    def build(self, toFile):
        self._build_records()

        with open(toFile, 'wb') as fh:
            # 0: database name (32 bytes)
            # TODO: fh.write(struct.pack('32s', 'DUMMY'))
            fh.write(struct.pack('32s', 'VVZZSTZJIR_YX'))
            # 32: attributes (2 bytes)
            fh.write(struct.pack('>H', 0))
            # 34: file version (2 bytes)
            fh.write(struct.pack('>H', 0))
            # 36: creation date (4 bytes)
            fh.write(struct.pack(
                '>L',
                (self._now - datetime.datetime(year=1904,month=1,day=1)).total_seconds(),
            ))
            # 40: modification date (4 bytes)
            fh.write(struct.pack(
                '>L',
                (self._now - datetime.datetime(year=1904,month=1,day=1)).total_seconds(),
            ))
            # 44: last backup date (4 bytes)
            fh.write(struct.pack(
                '>L',
                (self._now - datetime.datetime(year=1904,month=1,day=1)).total_seconds(),
            ))
            # 48: modification number (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 52: application info (4 bytes): not available
            fh.write(struct.pack('>L', 0))
            # 56: sort info (4 bytes): not available
            fh.write(struct.pack('>L', 0))

            # 60: type (4 bytes)
            fh.write(struct.pack('4s', 'BOOK'))
            # 64: creator (4 bytes)
            fh.write(struct.pack('4s', 'MOBI'))

            # 68: unique id seed (4 bytes): used internally to identify record
            # TODO: fh.write(struct.pack('>L', 0))
            fh.write(struct.pack('>L', 0x30D))
            # 72: next record list id (4 bytes): Only used when in-memory on Palm OS. Always set to zero in stored files.
            fh.write(struct.pack('>L', 0))

            # 76: number of records (2 bytes)
            fh.write(struct.pack('>H', len(self._records)))

            headersize = 78 + 8 * len(self._records) + 2
            offset = headersize

            # 78: record Info list (8 bytes x redords)
            for idx, record in enumerate(self._records):
                # record data offset (4 bytes)
                fh.write(struct.pack('>L', offset))
                offset = offset + len(record)
                # record attributes (1 bytes)
                fh.write(struct.pack('>B', 0))
                # unique id (3)
                fh.write(struct.pack('>B', 0))
                fh.write(struct.pack('>H', idx * 2))
            # gap to data (2 bytes)
            fh.write(struct.pack('>H', 0))

            for record in self._records:
                fh.write(record)

    def _build_records(self):
        self._build_text_records()
        self._build_image_records()
        self._build_metadata_record()
        self._build_flis_record()
        self._build_fcis_record()
        self._build_end_of_file_record()
        self._build_record0()

    def _build_record0(self):

        # PalmDOC Header
        with NewStringIO() as fh:
            # 0: compression (2 bytes): 1 - no compression
            fh.write(struct.pack('>H', 1))
            # 2: unused (2 bytes)
            fh.write(struct.pack('>H', 0))
            # 4: text length (4 bytes)
            fh.write(struct.pack('>L', self._text_length))
            # 8: text record count (2 bytes)
            fh.write(struct.pack('>H', self._text_records))
            # 10: record size (2 bytes): always 4096
            fh.write(struct.pack('>H', self.MAX_TEXT_SIZE))
            # 12: current reading position (4 bytes)
            fh.write(struct.pack('>L', 0))
            # Length: 16

            fh.write(self._build_mobiheader())

            # book title
            title_padded = self._encoded_title + struct.pack('2s', '')
            if len(title_padded) % 4 != 0:
                title_padded += struct.pack('{0}s'.format(4 - (len(title_padded) % 4)), '')
            fh.write(title_padded)

            record0 = fh.getvalue()
            record0 += struct.pack('{0}s'.format(0x2290 - len(record0)), '')

            self._records[0] = record0

    def _build_mobiheader(self):
        _exth = self._build_exth()
        with NewStringIO() as fh:
            # 0: identifier (4 bytes)
            fh.write(struct.pack('4s', 'MOBI'))
            # 4: header length (4 bytes): including previous 4 bytes
            fh.write(struct.pack('>L', self.MOBI_HEADER_LENGTH))
            # 8: mobi type (4 bytes): 2 - mobipocket books
            fh.write(struct.pack('>L', 2))
            # 12: text encoding (4 bytes): 65001 - UTF-8
            fh.write(struct.pack('>L', 65001))
            # 16: unique id (4 bytes)
            # TODO: fh.write(struct.pack('>L', 0))
            fh.write(struct.pack('>L', 3942927897))
            # 20: file version (4 bytes)
            fh.write(struct.pack('>L', 5))
            # 24: index section number (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 28: inflection metadata section number (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 32: index names (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 36: index keys (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 40: extra index 0 (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 44: extra index 1 (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 48: extra index 2 (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 52: extra index 3 (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 56: extra index 4 (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 60: extra index 5 (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 64: first non-book text section (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 68: full name offset (4 bytes). offset in this record
            fh.write(struct.pack(
                '>L',
                self.PALM_DOC_HEADER_LENGTH + self.MOBI_HEADER_LENGTH + len(_exth)
            ))
            # 72: full name length (4 bytes)
            fh.write(struct.pack('>L', len(self._encoded_title)))
            # 76: Locale (4 bytes)
            fh.write(struct.pack('>L', 17))
            # 80: Input Language (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 84: Output Language (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 88: Min version (4 bytes)
            fh.write(struct.pack('>L', 5))
            # 92: First Image index (4 bytes)
            fh.write(struct.pack('>L', self._text_records + 1))
            # 96: Huffman Record Offset (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 100: Huffman Huffman Record Count (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 104: Huffman Table Offset (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 108: Huffman Table Length (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 112: EXTH flags (4 bytes): has EXTH record
            fh.write(struct.pack('>L', 0x40))
            # 116: 32 unknown bytes (32 bytes)
            fh.write(struct.pack('32s', ''))
            # 148: Unknown (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 152: DRM Offset (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 156: DRM Count (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 160: DRM Size (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 164: DRM Flags (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 168: Unknown (8 bytes)
            fh.write(struct.pack('8s', ''))
            # 176: First content record number (2 bytes)
            fh.write(struct.pack('>H', 1))
            # 178: Last content record number (2 bytes)
            fh.write(struct.pack('>H', self._text_records + self._image_records + 1))
            # 180: Unknown (4 bytes)
            fh.write(struct.pack('>L', 1))
            # 184: FCIS record number (4 bytes)
            fh.write(struct.pack('>L', self._fcis_record_offset))
            # 188: FCIS record count (4 bytes)
            fh.write(struct.pack('>L', 1))
            # 192: FLIS record number (4 bytes)
            fh.write(struct.pack('>L', self._flis_record_offset))
            # 196: FLIS record count (4 bytes)
            fh.write(struct.pack('>L', 1))
            # 200: Unknown (8 bytes)
            fh.write(struct.pack('8s', ''))
            # 208: SRCS record number (4 bytes): not available
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 212: SRCS record count (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 216: Compilation record number (4bytes)
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 220: Compilation record count (4bytes)
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 224: Extra record data flags (4bytes): no extra bytes
            fh.write(struct.pack('>L', 0))
            # 228: INDX Record Offset (4bytes)
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 232: Unknown (4 bytes)
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 236: Unknown (4 bytes)
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 240: Unknown (4 bytes)
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 244: Unknown (4 bytes)
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 248: Unknown (4 bytes)
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            # 252: Unknown (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 256: Unknown (4 bytes)
            fh.write(struct.pack('>L', 0))
            # 260: Unknown (4 bytes)
            fh.write(struct.pack('>L', 0))
            # Length: 264

            return fh.getvalue() + _exth

    def _build_exth(self):
        # type, data
        exthList = [
            (ExthTypes.Published, self._now.strftime('%Y-%m-%dT%H:%M:%SZ')),
            (ExthTypes.Creator, self._author),
            (ExthTypes.ContainerId, '7U6e'),
            (ExthTypes.Language, 'ja'),
            (ExthTypes.Direction, 'rtl'),
            (ExthTypes.PrimaryWritingMode, 'vertical-rl'),
            (ExthTypes.MetadataResourceURI, 'kindle:embed:005J'),
            (ExthTypes.MetadataRecordOffset, self._image_records),
            (ExthTypes.Records, self._image_records),
            (ExthTypes.CoverOffset, 0),
            (ExthTypes.ThumbOffset, 0),
            (ExthTypes.HasFakeCover, 0),
        ]

        with NewStringIO() as fh:
            for exth in exthList:
                type, data = exth[0:2]
                if isinstance(data, int):
                    data = struct.pack('>L', data)
                else:
                    data = data.encode('utf-8')
                # type (4 bytes)
                fh.write(struct.pack('>L', type))
                # length (4 bytes) including type, length
                fh.write(struct.pack('>L', len(data) + 8))
                # data
                fh.write(data)
            exthData = fh.getvalue()

        with NewStringIO() as fh:
            # 0: identifier (4 bytes)
            fh.write(struct.pack('4s', 'EXTH'))
            # 4: header length (4 bytes): including previous 4 bytes, without last paddings
            fh.write(struct.pack('>L', len(exthData) + 12))
            # 8: record counts (4 bytes)
            fh.write(struct.pack('>L', len(exthList)))
            # 12-: exth records
            fh.write(exthData)
            # padding to be 4 bytes boundary
            if len(exthData) % 4 != 0:
                fh.write(struct.pack('{0}s'.format(4 - (len(exthData) % 4)), ''))
            exth = fh.getvalue()

        return exth

    def _build_text_records(self):
        text = '<html><head><guide></guide></head><body>'
        for page in range(1, len(self._image_files) + 1):
            text += '<p align="center"><img recindex="{0:05}"/></p><mbp:pagebreak/>'.format(page)
        text += '</body></html>'

        if len(text) % 4 != 0:
            text += ' ' * (4 - len(text) % 4)

        self._text_length = len(text)
        self._text_records = 0
        while len(text) > 0:
            self._records.append(text[:self.MAX_TEXT_SIZE])
            text = text[self.MAX_TEXT_SIZE:]
            self._text_records += 1

    def _build_image_records(self):
        self._image_files.sort()
        self._image_records = len(self._image_files)
        for _, data in self._image_files:
            if len(data) % 4 != 0:
                data += '\0' * (4 - len(data) % 4)
            self._records.append(data)

    def _build_metadata_record(self):
        text = '<?xml version="1.0" encoding="utf-8"?>'
        text += (
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"'
            ' xmlns:opf="http://www.idpf.org/2007/opf" xmlns="http://www.idpf.org/2007/opf">'
        )
        text += '</metadata>'
        text += '<spine page-progression-direction="rtl">'
        text += '<itemref idref="id1"/>'
        for page in range(len(self._image_files)):
            text += '<itemref idref="id{0}" skelid="{1}"/>'.format(page + 2, page)
        text += '</spine>'

        text_length = len(text)
        base32hex_text_length = ''
        while text_length > 0:
            fig = text_length % 32
            if fig < 10:
                base32hex_text_length = chr(ord('0') + fig) + base32hex_text_length
            else:
                base32hex_text_length = chr(ord('A') + fig - 10) + base32hex_text_length
            text_length = int(text_length / 32)

        prefix = 'size={0}&version=1&type=1'.format(base32hex_text_length)

        if len(text) % 4 != 0:
            text += ' ' * (4 - len(text) % 4)

        with NewStringIO() as fh:
            fh.write(struct.pack('16s', 'RESC'))
            fh.write(prefix)
            fh.write(text)
            data = fh.getvalue()

        if len(data) % 4 != 0:
            data += '\0' * (4 - len(data) % 4)

        self._records.append(data)

    def _build_flis_record(self):
        with NewStringIO() as fh:
            fh.write(struct.pack('4s', 'FLIS'))
            fh.write(struct.pack('>L', 8))
            fh.write(struct.pack('>H', 65))
            fh.write(struct.pack('>H', 0))
            fh.write(struct.pack('>L', 0))
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            fh.write(struct.pack('>H', 1))
            fh.write(struct.pack('>H', 3))
            fh.write(struct.pack('>L', 3))
            fh.write(struct.pack('>L', 1))
            fh.write(struct.pack('>L', 0xFFFFFFFF))
            self._records.append(fh.getvalue())
        self._flis_record_offset = len(self._records)

    def _build_fcis_record(self):
        with NewStringIO() as fh:
            fh.write(struct.pack('4s', 'FCIS'))
            fh.write(struct.pack('>L', 20))
            fh.write(struct.pack('>L', 16))
            fh.write(struct.pack('>L', 1))
            fh.write(struct.pack('>L', 0))
            fh.write(struct.pack('>L', self._text_length))
            fh.write(struct.pack('>L', 0))
            fh.write(struct.pack('>L', 32))
            fh.write(struct.pack('>L', 8))
            fh.write(struct.pack('>H', 1))
            fh.write(struct.pack('>H', 1))
            fh.write(struct.pack('>L', 0))
            self._records.append(fh.getvalue())
        self._fcis_record_offset = len(self._records)

    def _build_end_of_file_record(self):
        with NewStringIO() as fh:
            fh.write(struct.pack('>B', 0xe9))
            fh.write(struct.pack('>B', 0x8e))
            fh.write(struct.pack('>B', 0x0d))
            fh.write(struct.pack('>B', 0x0a))
            self._records.append(fh.getvalue())


class ZipToMobi(object):
    # https://wiki.mobileread.com/wiki/PDB
    # https://wiki.mobileread.com/wiki/MOBI
    VERSION = 1559310345

    def __init__(self):
        self._count = 0
        self._Logger = logging.getLogger(self.__class__.__name__)

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
        builder = _MobiBuilder(file)

        with zipfile.ZipFile(fromFile, 'r') as rh:
            for f in rh.infolist():
                if f.filename.endswith('/'):
                    continue
                basename = f.filename.split('/')[-1]
                ext = os.path.splitext(basename)[1]
                if ext.lower() not in ('.jpg', '.jpeg'):
                    self._Logger.warning('Skipped: %s', f.filename)
                    continue
                image = PIL.Image.open(io.BytesIO(rh.read(f)))
                # コントラストを設定する
                #image = PIL.ImageEnhance.Contrast(image).enhance(2.0)

                if image.mode == 'L':
                    image = PIL.ImageOps.autocontrast(image)
                    # モノクロ画像の場合、ボールド処理を行う
                    # 単純な MinFilter では太くなりすぎる
                    # image = image.filter(PIL.ImageFilter.MinFilter(3))
                    # 画像を縦横 1 pixel ずらしてコピーしてボールド処理とする。
                    image = PIL.ImageChops.darker(
                        image,
                        PIL.ImageChops.offset(image, 1, 0)
                    )
                    image = PIL.ImageChops.darker(
                        image,
                        PIL.ImageChops.offset(image, 0, 1)
                    )
                w = io.BytesIO()
                image.save(w, format='jpeg')
                builder.add_image_file(basename, w.getvalue())

        builder.build(tmpFile)
        os.rename(tmpFile, toFile)
        return {
            'filename': filename,
            'path': toFile,
        }


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
    copier = ZipToMobi()
    copier(file, '.', opts)
