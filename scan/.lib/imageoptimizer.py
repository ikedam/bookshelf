#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import os
import os.path
import re
import shutil

import PIL.Image
import PIL.ImageChops
import PIL.ImageEnhance
import PIL.ImageFilter
import PIL.ImageOps


class ImageOptimizer(object):

    WHITESPACE_NONE = 0
    WHITESPACE_CLEAN = 1
    WHITESPACE_TRIM = 2

    # 外れ値検知の最低サンプル数
    OUTLIERS_MIN_SAMPLES = 20
    # 外れ値検知の際に無視する先頭・末尾ページ数。
    # 通常、先頭ページ/末尾ページは平均的な印刷領域の参考にならないのでスキップする。
    OUTLIERS_IGNORE_SAMPLES = 5
    # 外れ値とみなすズレ
    OUTLIERS_DETECT_MM = 2.0
    # 検出した描画範囲からの安全のために確保するマージン (mm)
    BOUND_MARGIN = 1.0
    # 汚れがあったと検知する色の閾値
    DIRT_BLACK_THRESHOLD = 30
    # 印刷と判断する色の閾値
    PRINT_BLACK_THRESHOLD = 120
    DIFF_THRESHOLD_INFO = 10.0 / 758 / 1024
    DIFF_THRESHOLD_WARN = 100.0 / 758 / 1024
    DIFF_THRESHOLD = 200.0 / 758 / 1024
    DIVIDE_OVERWRAP = 0.05
    MM_PER_INCH = 25.4

    # ボールド処理を行う dpi 数
    BOLDIZE_DPI = 200

    # 基本名 連番 . 拡張子
    FILENAME_PARSER = re.compile(r'^(.*?)(\d+)\..*?$')

    def __init__(self, whitespace, percentile=95, boldize=True, verboseBound=False, traceBound=False):
        self._Logger = logging.getLogger(self.__class__.__name__)
        self._Whitespace = whitespace
        self._Boldize = boldize
        self._Percentile = percentile
        self._VerboseBound = verboseBound
        self._TraceBound = traceBound
        # 本の開く向き
        # 縦書き (右から左に開く) をデフォルトにする
        self._LTR = False
        self._preferDivide = False
        self.reset()

    def setRTL(self):
        self._LTR = False

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
            if color < self.PRINT_BLACK_THRESHOLD:
                blacks = blacks + count
            else:
                whites = whites + count
        return whites * 10 < blacks

    def reset(self, size=None):
        self._pageInfoMap = {}
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
                image.size[0] * self.MM_PER_INCH / image.info['dpi'][0],
                image.size[1] * self.MM_PER_INCH / image.info['dpi'][1],
            ))
        # 外辺情報を使用しない
        return

    def prepare_optimize(self):
        if not self.need_prescan():
            return

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
        image = PIL.Image.open(infh)

        if image.mode == 'L' and self._Whitespace != self.WHITESPACE_NONE:
            image = self.removeDirts(image, name)

        inDivideMode = self.divideMode and isinstance(outfh, (list, tuple))

        image = self._resize(image, inDivideMode)
        # コントラストを設定する
        #image = PIL.ImageEnhance.Contrast(image).enhance(2.0)

        if image.mode == 'L':
            image = PIL.ImageOps.autocontrast(image)
            if (
                not self.is_black_image(image)
                and self._Boldize
                and 'dpi' in image.info
                and image.info['dpi'][0] <= self.BOLDIZE_DPI
            ):
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

    def removeDirts(self, image, name):
        u"""余白部のノイズを除去した画像を返す"""
        if 'dpi' not in image.info:
            self._Logger.warning('%s: no dpi information', name)
            return image

        pxPerMm = [
            image.info['dpi'][i] / self.MM_PER_INCH
            for i in range(0, 2)
        ]

        if self._VerboseBound:
            if not os.path.exists('verbose'):
                os.mkdir('verbose')

        # ある程度薄い色は無視する
        boundImage = image.point(lambda x: 255 if x > self.PRINT_BLACK_THRESHOLD  else x)
        if self._TraceBound:
            if not os.path.exists('verbose/bound'):
                os.mkdir('verbose/bound')
            boundImage.save('verbose/bound/%s' % name)
        bound = PIL.ImageOps.invert(boundImage).getbbox()
        detectBound = self.detectBound(boundImage, pxPerMm, name)

        if self._TraceBound:
            self._Logger.debug('  update bound: %s -> %s', bound, detectBound)

        if not detectBound:
            # 真っ白なページ
            self._Logger.debug('%s: White page', name)
            whitepage = PIL.Image.new(
                image.mode,
                image.size,
                255,
            )
            """
            if bound and self._VerboseBound:
                # ノイズ除去の結果白いページになった
                diff = PIL.ImageChops.difference(image, whitepage)
                if not os.path.exists('verbose/dirts'):
                    os.mkdir('verbose/dirts')
                diff.save('verbose/dirts/%s' % name)
            """
            return whitepage

        # ページの情報の集計
        # ページは xxx0000.jpg のフォーマットになっていると仮定し、
        # 偶数ページ、奇数ページで記録を取る。
        match = self.FILENAME_PARSER.match(name)
        if match:
            basename = match.group(1)
            pagenumber = int(match.group(2))
            if basename not in self._pageInfoMap:
                self._pageInfoMap[basename] = []
            self._pageInfoMap[basename].append({
                'name': name,
                'pagenumber': pagenumber,
                'bound': self.toMm(detectBound, pxPerMm),
                'boundSize': self.toMm([
                    detectBound[2] - detectBound[0],
                    detectBound[3] - detectBound[1],
                ], pxPerMm),
                'size': self.toMm(image.size, pxPerMm),
            })

        boundDiff = [
            (bound[i] - detectBound[i]) != 0
            for i in range(0, 4)
        ]
        if any(boundDiff):
            self._Logger.debug('%s: detect dirts: %s -> %s', name, bound, detectBound)

        detectBound = self.invertBound(image.size, detectBound)
        bound = [
            max(0, detectBound[i] - int(pxPerMm[i % 2] * self.BOUND_MARGIN))
            for i in range(0, 4)
        ]
        bound = self.invertBound(image.size, bound)

        trimmedImage = image.crop(bound)
        cleanedImage = PIL.Image.new(image.mode, image.size, 255)
        cleanedImage.paste(trimmedImage, bound[:2])
        diff = PIL.ImageChops.difference(cleanedImage, image)

        graydiffs = 0
        blackdiffs = 0
        for count, color in diff.getcolors():
            if color >= self.DIRT_BLACK_THRESHOLD:
                graydiffs = graydiffs + count
            if color >= self.PRINT_BLACK_THRESHOLD:
                blackdiffs = blackdiffs + count

        if self._VerboseBound:
            if graydiffs > 0:
                self._Logger.debug('%s: dirts gray %s black %s', name, graydiffs, blackdiffs)
                """
                if not os.path.exists('verbose/dirts'):
                    os.mkdir('verbose/dirts')
                diff.save('verbose/dirts/%s' % name)
                """
            if not os.path.exists('verbose/trimmed'):
                os.mkdir('verbose/trimmed')
            PIL.ImageOps.invert(trimmedImage).save('verbose/trimmed/%s' % name)

        if graydiffs > self.DIFF_THRESHOLD_WARN  * image.size[0] * image.size[1]:
            self._Logger.warning('%s: Many dirts (gray %s / black %s)', name, graydiffs, blackdiffs)
        elif graydiffs > self.DIFF_THRESHOLD_INFO * image.size[0] * image.size[1]:
            self._Logger.info('%s: Dirts (gray %s / black %s)', name, graydiffs, blackdiffs)

        if self._Whitespace == self.WHITESPACE_CLEAN:
            return cleanedImage
        elif self._Whitespace == self.WHITESPACE_TRIM:
            return trimmedImage

        return image


    def detectBound(self, image, pxPerMm, name):
        u"""画像の周辺の余白部分にあるゴミを削除した範囲を返す

        モノクロ画像である前提とする。

        * 具体的な数字はすべてチューニングパラメーターなので仮のもの。
        * 余白部分にノイズがある場合、単純計算で余白を切り取ると、
            ノイズが外辺にやってくる。
            この状態で外辺を少し「削って」再び余白を計算すると、
            余白が「増える」挙動が確認されるはずである。
        * この「削る」(Skip)処理と、「増える」ことの検知(Detect)でノイズ判定を行う。
        * 最外辺に対する処理
            * 紙の境界によるノイズで、複数辺に同時にノイズが出ることが予期される。
                このため、最外辺については特別な処理を行う。
            * 最外辺で、0.5mm 以上の余白がない場合は外辺のノイズの可能性を考慮する。
            * 余白がなかった辺について 1mm 削って再度余白チェックを行い、
                余白が 5mm 以上増えたら外辺のノイズだと判断する。
                これは複数辺に対して同時に実行する。
        * 最外辺以外
            * 各辺について、0.5mm 削り、それによって余白が 5mm 増えたらノイズだと判断する。
            * ただし、罫線の可能性を考慮し、削った部分に印刷が1%未満であることも条件とする。
        """
        # 外辺でこれだけの余白(mm)がない場合はノイズがあると判断する
        OUTER_MIN_MARGIN = 0.5
        # 外辺での削る幅(Skip)と検知の幅(Detect) (mm)
        OUTER_THRESHOLDS = (
            (1.0, 3.0),
        )
        # 「本来の印刷がある」と判断する印刷の割合
        PRINT_THRESHOLD = 0.01
        # 外辺以外での削る幅(Skip)と検知の幅(Detect) (mm)
        INNER_THRESHOLDS = (
            (0.1, 1.0),
            (0.2, 2.0),
            (0.5, 3.0),
            (1.0, 5.0),
        )

        # 何らかの描画がある範囲の抽出
        bound = PIL.ImageOps.invert(image).getbbox()
        if not bound:
            # 真っ白なページ
            return None
        bound = self.invertBound(image.size, bound)
        boundMm = self.toMm(bound, pxPerMm)
        if self._TraceBound:
            self._Logger.debug('  Initial blanks: %s', boundMm)

        # 外辺の余白が一定未満の場合、ノイズと判定する。
        outerDirtSuspect = [
            boundMm[i] < OUTER_MIN_MARGIN
            for i in range(0, 4)
        ]
        if any(outerDirtSuspect):
            self._Logger.debug(
                '%s: outer dirt suspection: %s, %s',
                name,
                outerDirtSuspect,
                boundMm,
            )
            for skip, detect in OUTER_THRESHOLDS:
                # ノイズの疑いがある外辺を狭めて再度余白チェックする
                testBoundMm = [
                    0 if not outerDirtSuspect[i] else skip
                    for i in range(0, 4)
                ]
                if self._TraceBound:
                    self._Logger.debug('  Try detect outer dirts with %s, %s, %s', skip, detect, testBoundMm)
                testBound = self.toPx(testBoundMm, pxPerMm)

                # 演算誤差による誤検出を避けるため、一度もとの範囲で切り取って、
                # その後に狭めた分で切り取る。
                trimmedImage = image.crop(self.invertBound(image.size, bound))
                testBound = self.invertBound(trimmedImage.size, testBound)
                trimmedImage = trimmedImage.crop(testBound)
                trimmedBound = PIL.ImageOps.invert(trimmedImage).getbbox()
                if not trimmedBound:
                    # 真っ白なページ
                    if self._TraceBound:
                        self._Logger.debug('  Results white page')
                    return None
                trimmedBound = self.invertBound(trimmedImage.size, trimmedBound)
                trimmedBoundMm = self.toMm(trimmedBound, pxPerMm)
                if self._TraceBound:
                    self._Logger.debug('  New blanks %s', trimmedBoundMm)
                outerDirtDetect = [
                    trimmedBoundMm[i] > detect
                    for i in range(0, 4)
                ]
                if any(outerDirtDetect):
                    self._Logger.debug(
                        '%s: Detected outer dirts: %s %s %s',
                        name,
                        outerDirtDetect,
                        boundMm,
                        trimmedBoundMm,
                    )
                    trimBoundMm = [
                        0 if not outerDirtDetect[i] else skip
                        for i in range(0, 4)
                    ]
                    trimBound = self.toPx(trimBoundMm, pxPerMm)
                    trimBound = self.invertBound(image.size, trimBound)
                    trimmedImage = image.crop(trimBound)
                    image = PIL.Image.new(image.mode, image.size, 255)
                    image.paste(trimmedImage, trimBound[:2])
                    break

        # 左辺、上辺、右辺、下辺のそれぞれについてノイズテストを行って幅を狭める
        for target in range(0, 4):
            if self._TraceBound:
                self._Logger.debug('Detecting dirts in direction %s', target)
            while True:
                # 更新がある間繰り返す。
                updated = False

                # 現時点の何らかの描画がある範囲の抽出
                bound = PIL.ImageOps.invert(image).getbbox()
                if not bound:
                    # 真っ白なページ
                    # ここに来る前に return していないとおかしい
                    self._Logger.warning('%s: Unexpected white page', name)
                    return None
                # 印刷量検知
                if target == 0:
                    testPrint = image.crop((bound[0], bound[1], bound[0] + 1, bound[3]))
                elif target == 1:
                    testPrint = image.crop((bound[0], bound[1], bound[2], bound[1] + 1))
                elif target == 2:
                    testPrint = image.crop((bound[2] - 1, bound[1], bound[2], bound[3]))
                else:
                    testPrint = image.crop((bound[0], bound[3] - 1, bound[2], bound[3]))

                points = 0
                blacks = 0
                for count, color in PIL.ImageOps.invert(testPrint).getcolors():
                    points = points + count
                    if color >= self.DIRT_BLACK_THRESHOLD:
                        blacks = blacks + count

                if self._TraceBound:
                    self._Logger.debug('  blacks / points = %s / %s (%.3f)', blacks, points, (float(blacks) / points))

                bound = self.invertBound(image.size, bound)
                boundMm = self.toMm(bound, pxPerMm)

                for skip, detect in INNER_THRESHOLDS:
                    if self._TraceBound:
                        self._Logger.debug(' Try detect with skip=%s detect=%s', skip, detect)
                    testBoundMm = [0] * 4
                    testBoundMm[target] = skip
                    testBound = self.toPx(testBoundMm, pxPerMm)

                    # 演算誤差による誤検出を避けるため、一度もとの範囲で切り取って、
                    # その後に狭めた分で切り取る。
                    trimmedImage = image.crop(self.invertBound(image.size, bound))
                    testBound = self.invertBound(trimmedImage.size, testBound)
                    trimmedImage = trimmedImage.crop(testBound)
                    trimmedBound = PIL.ImageOps.invert(trimmedImage).getbbox()
                    if not trimmedBound:
                        # 真っ白なページ
                        if self._TraceBound:
                            self._Logger.debug('  Results white page')
                        return None
                    trimmedBound = self.invertBound(trimmedImage.size, trimmedBound)
                    trimmedBoundMm = self.toMm(trimmedBound, pxPerMm)
                    if self._TraceBound:
                        self._Logger.debug('  New blanks %s', trimmedBoundMm)

                    if trimmedBoundMm[target] > detect:
                        # 汚れと判定
                        self._Logger.debug('%s (%s): detect dirt: %s', name, target, trimmedBound)

                        if blacks > points * PRINT_THRESHOLD:
                            # 一定以上の印刷があるのでノイズではないと判定
                            self._Logger.info(
                                '%s: Doubt dirt in direction %s, but ignored as much prints: %s / %s',
                                name,
                                target,
                                blacks,
                                points,
                            )
                            break

                        image = PIL.Image.new(image.mode, image.size, 255)
                        image.paste(
                            trimmedImage,
                            (
                                bound[0] + testBound[0],
                                bound[1] + testBound[1],
                            ),
                        )
                        updated = True
                        break
                    elif trimmedBoundMm[target] > 0.5:
                        self._Logger.debug(
                            '%s (%s): detected but not dirt with skip %s: %s',
                            name,
                            target,
                            skip,
                            trimmedBoundMm,
                        )

                if updated:
                    continue
                break

        return PIL.ImageOps.invert(image).getbbox()

    def invertBound(self, size, bound):
        return [
            bound[0],
            bound[1],
            size[0] - bound[2],
            size[1] - bound[3],
        ]

    def toMm(self, metrics, pxPerMm):
        return [
            m / pxPerMm[i % 2]
            for i, m in enumerate(metrics)
        ]

    def toPx(self, metrics, pxPerMm):
        return [
            int(m * pxPerMm[i % 2])
            for i, m in enumerate(metrics)
        ]

    def report(self):
        u"""スキャン結果から外れデータを報告する"""
        # 左側のページの決定
        if self._LTR:
            lPage = 0
            rPage = 1
        else:
            lPage = 1
            rPage = 0

        for name, pageInfos in self._pageInfoMap.items():
            if len(pageInfos) < self.OUTLIERS_MIN_SAMPLES * 2:
                # サンプル数が少なすぎるので処理対象外とする
                self._Logger.debug('%s: too few samples, report skipped (%s)', name, len(pageInfos))
                continue
            expectedBoundSizeList = []
            expectedBoundList = []
            for i in range(2):
                expectedBoundSizeList.append(self._calculateSizeFromSamples([
                    info['boundSize'] for info in pageInfos if info['pagenumber'] % 2 == i
                ]))
                # 領域については以下のように扱う:
                # X座標: 外側からの距離を基準に扱う。
                #     つまり左側ページは左からの距離を、右側ページは右側からの距離。
                #     つまり右側ページの際は左右を反転させて利用する
                # Y座標: ページの中心からの距離を基準に扱う。
                expectedBoundList.append(self._calculateBoundFromSamples([
                    self._normalizeBound(info['size'], info['bound'], i == lPage)
                    for info in pageInfos if info['pagenumber'] % 2 == i
                ]))

            self._Logger.debug('expected bound size: %s', expectedBoundSizeList)
            self._Logger.debug('expected bound: %s', expectedBoundList)

            for info in pageInfos:
                p = info['pagenumber'] % 2
                expectedBoundSize = expectedBoundSizeList[p]
                expectedBound = self._denormalizeBound(info['size'], expectedBoundList[p], p == lPage)
                bound = self.invertBound(info['size'], info['bound'])
                expectedBound = self.invertBound(info['size'], expectedBound)
                if bound and self._VerboseBound:
                    self._Logger.debug('%s: size      : %s', info['name'], info['size'])
                    self._Logger.debug('%s: bound size: %s', info['name'], info['boundSize'])
                    self._Logger.debug('%s:   expected: %s', info['name'], expectedBoundSize)
                    self._Logger.debug('%s: bound     : %s', info['name'], info['bound'])
                    self._Logger.debug('%s:   expected: %s', info['name'], expectedBound)
                withWarn = False
                for i, mark in ((0, 'width'), (1, 'height')):
                    if info['boundSize'][i] - expectedBoundSize[i] > self.OUTLIERS_DETECT_MM:
                        self._Logger.warning(
                            '%s: print %s is larger than other pages: %.1fmm',
                            info['name'],
                            mark,
                            info['boundSize'][i] - expectedBoundSize[i],
                        )
                        withWarn = True
                for i, mark in ((0, 'left'), (1, 'top'), (2, 'right'), (3, 'bottom')):
                    if expectedBound[i] - bound[i] > self.OUTLIERS_DETECT_MM:
                        self._Logger.warning(
                            '%s: %s bound is outer than other pages: %.1fmm',
                            info['name'],
                            mark,
                            expectedBound[i] - bound[i],
                        )
                        withWarn = True
                if withWarn:
                    if os.path.exists('verbose/trimmed/%s' % info['name']):
                        if not os.path.exists('verbose/warn'):
                            os.mkdir('verbose/warn')
                        shutil.copy(
                            'verbose/trimmed/%s' % info['name'],
                            'verbose/warn/%s' % info['name'],
                        )

    def _calculateSizeFromSamples(self, valueList):
        u"""サンプルから想定されるサイズを算定する"""
        start = self.OUTLIERS_IGNORE_SAMPLES
        end = len(valueList) - self.OUTLIERS_IGNORE_SAMPLES
        result = []
        for i in range(2):
            values = [v[i] for v in valueList[start:end]]
            # 包含範囲が広い大きい値を採用する。なので昇順ソート。
            values.sort()
            result.append(values[len(values) * self._Percentile // 100])
        return result

    def _calculateBoundFromSamples(self, valueList):
        u"""サンプルから想定される領域を算定する"""
        start = self.OUTLIERS_IGNORE_SAMPLES
        end = len(valueList) - self.OUTLIERS_IGNORE_SAMPLES
        result = []
        for i in range(4):
            values = [v[i] for v in valueList[start:end]]
            # left, top はより外側の値 = 小さい値を採用する。なので降順ソート。
            # right, bottom はより外側の値 = 大きい値を採用する。なので昇順ソート。
            values.sort(reverse=(i < 2))
            result.append(values[len(values) * self._Percentile // 100])
        return result

    def _normalizeBound(self, size, bound, isL):
        vCenter = size[1] / 2
        if isL:
            return [
                bound[0],
                bound[1] - vCenter,
                bound[2],
                bound[3] - vCenter,
            ]
        else:
            return [
                size[0] - bound[2],
                bound[1] - vCenter,
                size[0] - bound[0],
                bound[3] - vCenter,
            ]

    def _denormalizeBound(self, size, bound, isL):
        vCenter = size[1] / 2
        if isL:
            return [
                bound[0],
                bound[1] + vCenter,
                bound[2],
                bound[3] + vCenter,
            ]
        else:
            return [
                size[0] - bound[2],
                bound[1] + vCenter,
                size[0] - bound[0],
                bound[3] + vCenter,
            ]


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('file')
    opts = parser.parse_args()
    level = logging.DEBUG
    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s',
        level=level,
    )

    optimizer = ImageOptimizer(
        whitespace=ImageOptimizer.WHITESPACE_CLEAN,
        verboseBound=True,
        traceBound=True,
    )

    with open(opts.file, 'rb') as infh:
        import io
        optimizer.optimize(
            os.path.basename(opts.file),
            infh,
            io.BytesIO(),
        )
