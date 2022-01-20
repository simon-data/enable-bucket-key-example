#!/usr/bin/env bash

set -ex

rm -f enable-bucket-key-example-function.zip
cd package
zip -r ../enable-bucket-key-example-function.zip .
cd ..
zip -g enable-bucket-key-example-function.zip lambda_function.py
