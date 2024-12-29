#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import json
import logging
import os
import os.path
import sys

sys.path.append(os.path.join(
    os.path.dirname(__file__),
    '../.lib'
))

NOVEL_VERSION=1606645800

import createepub
import createmobi
import imageoptimizer
import indextool
import s3


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', dest='verbose', action='count', default=0)
    parser.add_argument('-n', dest='dryrun', action='store_true')
    parser.add_argument('--mobi', dest='mobi', action='store_true')
    parser.add_argument('--max', dest='max', type=int, default=-1)
    parser.add_argument('--only', dest='only')
    parser.add_argument('--comics', dest='comics', action='store_true')
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

    s3info = s3.getS3Info()

    indexer = indextool.Indexer()
    optimizer = imageoptimizer.ImageOptimizer(
        whitespace=imageoptimizer.ImageOptimizer.WHITESPACE_CLEAN,
    )
    copier = [createepub.ZipToKepubEpub(optimizer)]
    if opts.mobi:
        copier.append(createmobi.ZipToMobi(optimizer, s3Bucket=s3info.getBucket('novel')))
    else:
        copier.append(createmobi.ZipToMobi(None, skip=True))
    for c in copier:
        c.VERSION = NOVEL_VERSION
    fileList = []
    scanner = indextool.IndexScanner(indexer, ['.zip'])
    generator = indextool.CopyingIndexGenerator(
        '../novels',
        'novels',
        copier,
    )
    result = scanner.scan(generator, '小説一覧', '../novels', '../../.lib/.js', opts)
    fileList.extend([
        {
            'filename': os.path.join('novels', file['filename']),
            'index': file['index'],
            'author': file['author'],
            'title': file['title'],
            'mtime': file['mtime'],
        }
        for file in result['fileList']
    ])

    if opts.comics:
        optimizer = imageoptimizer.ImageOptimizer(
            whitespace=imageoptimizer.ImageOptimizer.WHITESPACE_NONE,
            boldize=False,
        )
        copier = [createepub.ZipToKepubEpub(optimizer)]
        if opts.mobi:
            copier.append(createmobi.ZipToMobi(optimizer, s3Bucket=s3info.getBucket('comic')))
        else:
            copier.append(createmobi.ZipToMobi(skip=True))
        generator = indextool.CopyingIndexGenerator(
            '../zip',
            'comics',
            copier,
        )
        result = scanner.scan(generator, '漫画一覧', '../zip', '../../.lib/.js', opts)
        fileList.extend([
            {
                'filename': os.path.join('comics', file['filename']),
                'index': file['index'],
                'author': file['author'],
                'title': file['title'],
                'mtime': file['mtime'],
            }
            for file in result['fileList']
        ])

    indexer.save()
    fileList.sort(key=(lambda x: -x['mtime']))
    with open('index.json', 'wb') as f:
        f.write(json.dumps(
            fileList,
            ensure_ascii=False,
            indent=4,
            sort_keys=True,
        ).encode('utf-8'))
