#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

import PIL.Image
import PIL.ImageChops
import PIL.ImageEnhance
import PIL.ImageFilter
import PIL.ImageOps


class ImageOptimizer(object):

    WHITESPACE_NONE = 0
    WHITESPACE_CLEAN = 1
    WHITESPACE_TRIM = 2

    BOUND_LOWER = 100
    BOUND_MARGIN = 0.002
    IGNORE_SAMPLES = 5
    BLACK_THRESHOLD = 30
    DIFF_THRESHOLD_INFO = 10.0 / 758 / 1024
    DIFF_THRESHOLD_WARN = 100.0 / 758 / 1024
    DIFF_THRESHOLD = 200.0 / 758 / 1024
    DIVIDE_OVERWRAP = 0.05

    def __init__(self, whitespace, percentile=95, boldize=True, verboseBound=False, allowDivide=False):
        self._Logger = logging.getLogger(self.__class__.__name__)
        self._Whitespace = whitespace
        self._Boldize = boldize
        self._Percentile = percentile
        self._VerboseBound = verboseBound
        self._allowDivide = allowDivide
        self._preferDivide = False
        self.reset()

    def setAllowDivide(self, allowDivide):
        self._allowDivide = allowDivide

    @property
    def divideMode(self):
        return self._allowDivide and self._preferDivide

    def is_black_image(self, image):
        if image.mode != 'L':
            return False

        # gets [(count, color)]
        whites = 0
        blacks = 0
        for count, color in image.getcolors():
            if color < self.BLACK_THRESHOLD:
                blacks = blacks + count
            else:
                whites = whites + count
        return whites * 10 < blacks

    def reset(self, size=None):
        self._lboundList = []
        self._rboundList = []
        self._lbound = None
        self._rbound = None
        self._actualMmSizeList = []
        self._preferDivide = False
        self._page = 0
        self._size = size

    def need_prescan(self):
        return (
            self._Whitespace == self.WHITESPACE_CLEAN
            or self._Whitespace == self.WHITESPACE_TRIM
        )

    def _resize(self, image, inDivideMode=False):
        if not self._size:
            return image

        size = (self._size[0], self._size[1])
        if inDivideMode:
            # 一部重複させる
            size = (
                size[1],
                int(size[0] * 2 / (1 + self.DIVIDE_OVERWRAP))
            )

        image.thumbnail(self._size, PIL.Image.LANCZOS)
        base_image = image
        image = PIL.Image.new(
            base_image.mode,
            size,
            255 if image.mode == 'L' else (255, 255, 255),
        )
        image.paste(base_image, (
            int((size[0] - base_image.width) / 2),
            int((size[1] - base_image.height) / 2),
        ))
        return image

    def prescan(self, name, fh):
        if not self.need_prescan():
            return
        self._page = self._page + 1
        image = PIL.Image.open(fh)
        if 'dpi' in image.info:
            self._actualMmSizeList.append((
                image.size[0] * 25.4 / image.info['dpi'][0],
                image.size[1] * 25.4 / image.info['dpi'][1],
            ))
        if image.mode != 'L':
            return
        if self.is_black_image(image):
            return

        image = image.point(lambda x: 255 if x > 100  else x)
        bound = PIL.ImageOps.invert(image).getbbox()
        if bound:
            actualBound = bound
            bound = (
              float(actualBound[0]) / image.size[0],
              float(actualBound[1]) / image.size[1],
              float(actualBound[2]) / image.size[0],
              float(actualBound[3]) / image.size[1],
            )
            if self._VerboseBound:
                self._Logger.debug(
                    '%s: size: %04d %04d bound: %04d %04d %04d %04d scaled: %s',
                    name,
                    image.size[0], image.size[1],
                    actualBound[0], actualBound[1], actualBound[2], actualBound[3],
                    bound,
                )
            if self._page % 2 == 1:
                self._lboundList.append(list(bound) + [name])
            else:
                self._rboundList.append(list(bound) + [name])

    def _calculateBound(self, boundList):
        size = len(boundList)

        if size < self.BOUND_LOWER:
            return None

        start = self.IGNORE_SAMPLES
        end = size - self.IGNORE_SAMPLES
        lefts = [b[0] for b in boundList[start:end]]
        tops = [b[1] for b in boundList[start:end]]
        rights = [b[2] for b in boundList[start:end]]
        bottoms = [b[3] for b in boundList[start:end]]

        lefts.sort(reverse=True)
        tops.sort(reverse=True)
        rights.sort()
        bottoms.sort()

        bound = (
            lefts[len(lefts) * self._Percentile // 100],
            tops[len(tops) * self._Percentile // 100],
            rights[len(rights) * self._Percentile // 100],
            bottoms[len(bottoms) * self._Percentile // 100],
        )
        bound = (
            max(0, bound[0] - self.BOUND_MARGIN),
            max(0, bound[1] - self.BOUND_MARGIN),
            bound[2] + self.BOUND_MARGIN,
            bound[3] + self.BOUND_MARGIN,
        )
        return bound

    def prepare_optimize(self):
        if not self.need_prescan():
            return

        if self._VerboseBound:
            for idx, b in enumerate(self._lboundList):
                self._Logger.debug('%s: %.04f %.04f %.04f %.04f', b[4], *b[0:4])
            for idx, b in enumerate(self._rboundList):
                self._Logger.debug('%s: %.04f %.04f %.04f %.04f', b[4], *b[0:4])
        lbound = self._calculateBound(self._lboundList)
        rbound = self._calculateBound(self._rboundList)

        if not lbound or not rbound:
            self._Logger.warn(
                'Whitespace handler is disabled. Samples might be too fewer: %s, %s',
                len(self._lboundList),
                len(self._rboundList),
            )
            return

        self._lbound = lbound
        self._rbound = rbound
        self._Logger.debug('left bound: %s', self._lbound)
        self._Logger.debug('right bound: %s', self._rbound)

        if self._actualMmSizeList:
            widths = [s[0] for s in self._actualMmSizeList]
            heights = [s[1] for s in self._actualMmSizeList]
            widths.sort()
            heights.sort()
            width = widths[len(widths) * self._Percentile // 100]
            height = heights[len(heights) * self._Percentile // 100]
            self._Logger.debug('size in mm: %s, %s', width, height)
            # Kindle paperwhite の画面サイズ(実測)
            # 横: 91mm
            # 縦: 123mm
            # 60%未満に縮小される場合、分割対象にする。
            self._preferDivide = (
                91 < 0.6 * width
                or 123 < 0.6 * height
            )
            if self._allowDivide and self._preferDivide:
                self._Logger.info('Divide mode is enabled')

    def optimize(self, name, infh, outfh):
        self._page = self._page + 1
        if self._page % 2 == 1:
            bound = self._lbound
        else:
            bound = self._rbound

        image = PIL.Image.open(infh)

        if image.mode == 'L':
            if not self.is_black_image(image):
                if bound:
                    scaledBound = (
                        int(bound[0] * image.size[0]),
                        int(bound[1] * image.size[1]),
                        int(bound[2] * image.size[0]),
                        int(bound[3] * image.size[1]),
                    )
                    trimmedImage = image.crop(scaledBound)
                    cleanedImage = PIL.Image.new(image.mode, image.size, 255)
                    cleanedImage.paste(trimmedImage, scaledBound[:2])
                    diff = PIL.ImageChops.difference(cleanedImage, image)
                    diffs = 0
                    for count, color in diff.getcolors():
                        if color >= self.BLACK_THRESHOLD:
                            diffs = diffs + count
                    if diffs < self.DIFF_THRESHOLD * image.size[0] * image.size[1]:
                        if diffs > self.DIFF_THRESHOLD_WARN  * image.size[0] * image.size[1]:
                            self._Logger.warn('%s: Many dirts (%s)', name, diffs)
                        elif diffs > self.DIFF_THRESHOLD_INFO * image.size[0] * image.size[1]:
                            self._Logger.info('%s: Dirts (%s)', name, diffs)
                        if self._Whitespace == self.WHITESPACE_CLEAN:
                            image = cleanedImage
                        elif self._Whitespace == self.WHITESPACE_TRIM:
                            image = trimmedImage
                    else:
                        self._Logger.warn('%s: Too many dirts and not cleaned (%s)', name, diffs)

        inDivideMode = self.divideMode and isinstance(outfh, (list, tuple))

        image = self._resize(image, inDivideMode)
        # コントラストを設定する
        #image = PIL.ImageEnhance.Contrast(image).enhance(2.0)

        if image.mode == 'L':
            image = PIL.ImageOps.autocontrast(image)
            if not self.is_black_image(image) and self._Boldize:
                # モノクロ画像の場合、ボールド処理を行う
                # 単純な MinFilter では太くなりすぎる
                # image = image.filter(PIL.ImageFilter.MinFilter(3))
                # 画像を縦横 1 pixel ずらしてコピーしてボールド処理とする。
                width, height = image.size
                offset = 1
                offsetImage = PIL.Image.new(image.mode, image.size, 255)
                offsetImage.paste(image, (offset, 0))
                image = PIL.ImageChops.darker(image, offsetImage)
                offsetImage = PIL.Image.new(image.mode, image.size, 255)
                offsetImage.paste(image, (0, offset))
                image = PIL.ImageChops.darker(image, offsetImage)

        if inDivideMode:
            image = image.rotate(90, expand=True)
            width = int(image.size[0] * (1 + self.DIVIDE_OVERWRAP) / 2)
            imageL = PIL.Image.new(
                image.mode,
                (width, image.size[1]),
                255 if image.mode == 'L' else (255, 255, 255),
            )
            imageL.paste(
                image.crop((0, 0, width, image.size[1])),
                (0, 0),
            )
            imageR = PIL.Image.new(
                image.mode,
                (width, image.size[1]),
                255 if image.mode == 'L' else (255, 255, 255),
            )
            imageR.paste(
                image.crop((image.size[0] - width, 0, image.size[0], image.size[1])),
                (0, 0),
            )
            imageL.save(outfh[0], format='jpeg')
            imageR.save(outfh[1], format='jpeg')
            return

        image.save(outfh, format='jpeg')
