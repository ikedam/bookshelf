#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
import os.path

def getS3Info():
    s3file = os.path.join(os.path.dirname(__file__), 's3.json')
    if not os.path.exists(s3file):
        return S3Info()

    with open(s3file, 'rb') as f:
        s3info = json.load(f)
    s3 = ConnectedS3Info(s3info)
    s3.connect()
    return s3


class S3Info(object):

    def getBucket(self, key):
        return None


class ConnectedS3Info(S3Info):

    def __init__(self, s3info):
        self._S3Info = s3info
        self._S3 = None

    def connect(self):
        import boto3
        import warnings
        warnings.resetwarnings()
        warnings.simplefilter('ignore', boto3.exceptions.PythonDeprecationWarning)
        self._S3 = boto3.resource(
            's3',
            aws_access_key_id=self._S3Info['aws_access_key_id'],
            aws_secret_access_key=self._S3Info['aws_secret_access_key'],
        )

    def getBucket(self, key):
        buckets = self._S3Info['buckets']
        if key not in buckets:
            return None
        return self._S3.Bucket(buckets[key])
