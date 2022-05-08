#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import os
import os.path
import re

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

    # 基本名 連番 . 拡張子
    FILENAME_PARSER = re.compile(r'^(.*?)(\d+)\..*?$')

    def __init__(self, whitespace, percentile=95, boldize=True, verboseBound=False):
        self._Logger = logging.getLogger(self.__class__.__name__)
        self._Whitespace = whitespace
        self._Boldize = boldize
        self._Percentile = percentile
        self._VerboseBound = verboseBound
        # 本の開く向き
        # 縦書き (右から左に開く) をデフォルトにする
        self._LTR = False
        self._preferDivide = False
        self.reset()

    def setRTL(self):
        self._RTL = False

    def setLTR(self):
        self._LTR = True

    @property
    def divideMode(self):
        return self._LTR and self._preferDivide

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
        self._boundMap = {}
        self._actualMmSizeList = []
        self._preferDivide = False
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

        # ファイル名を ベースネーム + 連番 と仮定し、ベースネームでクラスタリングする
        match = self.FILENAME_PARSER.match(name)
        if not match:
            self._Logger.warn(
                '%s: Unexpected file name pattern',
                name,
            )
            return

        basename = match.group(1)
        pagenumber = int(match.group(2))
        # 左側のページか?
        isL = (not self._LTR and pagenumber % 2 == 1) or (self._LTR and pagenumber % 2 == 0)

        if basename not in self._boundMap:
            self._boundMap[basename] = {
                'lboundList': [],
                'rboundList': [],
                'lbound': None,
                'rbound': None,
            }

        # ある程度薄い色は無視する
        image = image.point(lambda x: 255 if x > 100  else x)
        # 何らかの描画がある範囲の抽出
        bound = PIL.ImageOps.invert(image).getbbox()
        if not bound:
            # 真っ白なページ
            self._Logger.debug(
                '%s: No bounds calculated',
                name,
            )
            return

        # 縦位置についてはページの「真ん中」からの距離が一定であるとする。
        # 横位置についてはページの「外側」からの距離が一定であるとする。
        # 「外側」とは…
        # * 右開きの本 (not self._LTR) の場合
        #     * 奇数ページ(左ページ)は左から
        #     * 偶数ページ(右ページ)は右から
        # * 左開きの本 (self._LTR) の場合
        #     * 奇数ページ(右ページ)は右から
        #     * 偶数ページ(左ページ)は左から
        vertCenter = image.size[1] / 2
        if isL:
            # 左から
            relativeBound = (
                bound[0],   # x0
                bound[1] - vertCenter,  # y0
                bound[2],   # x1
                bound[3] - vertCenter,  # y1
            )
        else:
            # 右から
            # 左右を反転することにも注意。
            relativeBound = (
                image.size[0] - bound[2],   # x0
                bound[1] - vertCenter,  # y0
                image.size[0] - bound[0],   # x1
                bound[3] - vertCenter,  # y1
            )
        if self._VerboseBound:
            self._Logger.debug(
                '%s: size: %04d %04d bound: %04d %04d %04d %04d relative: %s',
                name,
                image.size[0], image.size[1],
                bound[0], bound[1], bound[2], bound[3],
                relativeBound,
            )
        if isL:
            self._boundMap[basename]['lboundList'].append(list(relativeBound) + [name])
        else:
            self._boundMap[basename]['rboundList'].append(list(relativeBound) + [name])

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
            bound[0],
            bound[1],
            bound[2],
            bound[3],
        )
        return bound

    def prepare_optimize(self):
        if not self.need_prescan():
            return

        for name, bounds in self._boundMap.iteritems():
            if self._VerboseBound:
                self._Logger.debug('%s', name)
                for idx, b in enumerate(bounds['lboundList']):
                    self._Logger.debug('%s: %.04f %.04f %.04f %.04f', b[4], *b[0:4])
                for idx, b in enumerate(bounds['rboundList']):
                    self._Logger.debug('%s: %.04f %.04f %.04f %.04f', b[4], *b[0:4])
            bounds['lbound'] = self._calculateBound(bounds['lboundList'])
            bounds['rbound'] = self._calculateBound(bounds['rboundList'])

            self._Logger.debug('left bound: %s', bounds['lbound'])
            self._Logger.debug('right bound: %s', bounds['rbound'])

            if not bounds['lbound'] or not bounds['rbound']:
                self._Logger.warn(
                    '%s: Whitespace handler is disabled. Samples might be too fewer: %s, %s',
                    name,
                    len(bounds['lboundList']),
                    len(bounds['rboundList']),
                )

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
            if self._LTR and self._preferDivide:
                self._Logger.info('Divide mode is enabled')

    def optimize(self, name, infh, outfh):
        match = self.FILENAME_PARSER.match(name)
        if match:
            basename = match.group(1)
            pagenumber = int(match.group(2))
            # 左側のページか?
            isL = (not self._LTR and pagenumber % 2 == 1) or (self._LTR and pagenumber % 2 == 0)
            if isL:
                bound = self._boundMap.get(basename, {}).get('lbound')
            else:
                bound = self._boundMap.get(basename, {}).get('rbound')
        else:
            bound = None

        image = PIL.Image.open(infh)

        if image.mode == 'L':
            if not self.is_black_image(image):
                if bound:
                    vertCenter = image.size[1] / 2
                    if isL:
                        bound = (
                            bound[0],   # x0
                            bound[1] + vertCenter,  # y0
                            bound[2],   # x1
                            bound[3] + vertCenter,  # y1
                        )
                    else:
                        bound = (
                            image.size[0] - bound[2],   # x0
                            bound[1] + vertCenter,  # y0
                            image.size[0] - bound[0],   # x1
                            bound[3] + vertCenter,  # y1
                        )
                    bound = (
                        max(0, bound[0] - int(image.size[0] * self.BOUND_MARGIN)),
                        max(0, bound[1] - int(image.size[1] * self.BOUND_MARGIN)),
                        min(image.size[0], bound[2] + int(image.size[0] * self.BOUND_MARGIN)),
                        min(image.size[1], bound[3] + int(image.size[1] * self.BOUND_MARGIN)),
                    )
                    trimmedImage = image.crop(bound)
                    cleanedImage = PIL.Image.new(image.mode, image.size, 255)
                    cleanedImage.paste(trimmedImage, bound[:2])
                    diff = PIL.ImageChops.difference(cleanedImage, image)
                    diffs = 0
                    for count, color in diff.getcolors():
                        if color >= self.BLACK_THRESHOLD:
                            diffs = diffs + count
                    if diffs < self.DIFF_THRESHOLD * image.size[0] * image.size[1]:
                        if diffs > self.DIFF_THRESHOLD_WARN  * image.size[0] * image.size[1]:
                            self._Logger.warn('%s: Many dirts (%s)', name, diffs)
                            if self._VerboseBound:
                                if not os.path.exists('dirts'):
                                    os.mkdir('dirts')
                                diff.save('dirts/%s' % name)
                        elif diffs > self.DIFF_THRESHOLD_INFO * image.size[0] * image.size[1]:
                            self._Logger.info('%s: Dirts (%s)', name, diffs)
                        if self._Whitespace == self.WHITESPACE_CLEAN:
                            image = cleanedImage
                        elif self._Whitespace == self.WHITESPACE_TRIM:
                            image = trimmedImage
                    else:
                        self._Logger.warn('%s: Too many dirts and not cleaned (%s)', name, diffs)
                        if self._VerboseBound:
                            if not os.path.exists('dirts'):
                                os.mkdir('dirts')
                            diff.save('dirts/%s' % name)

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
