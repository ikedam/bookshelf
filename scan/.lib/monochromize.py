#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import logging
import os
import os.path

import PIL.Image


class Monochromize(object):

    def __init__(self, saveopts=None):
        self._Logger = logging.getLogger(self.__class__.__name__)
        if saveopts is None:
            saveopts = {}
        self._SaveOpts = saveopts

    def monochromize(self, tofile, fromfile):
        image = PIL.Image.open(fromfile)

        if image.mode == 'L':
            return False

        image = image.convert('L')

        image.save(tofile, format='jpeg', **self._SaveOpts)

        return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', dest='verbose', action='count', default=0)
    parser.add_argument('dir')
    opts = parser.parse_args()
    level = logging.INFO
    if opts.verbose:
        level = logging.DEBUG
    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s',
        level=level,
    )
    m = Monochromize()

    for dirpath, dirnames, filenames in  os.walk(opts.dir):
        for filename in filenames:
            if not filename.startswith('scan'):
                continue
            path = os.path.join(dirpath, filename)
            # basename, ext = os.path.splitext(path)
            # topath = basename + 'a' + ext
            logging.debug('Scanning %s...', path)
            if m.monochromize(path, path):
                logging.info('Convert: %s', path)
