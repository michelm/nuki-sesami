#!/usr/bin/env bash
set -e

cd $(dirname "$0")
./build.sh
python3 -m twine upload --repository pypi dist/*
