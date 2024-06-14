#!/usr/bin/env bash
set -e

cd $(dirname "$0")
./build.sh

export HATCH_INDEX_USER="__token__"
authline=$(grep 'password = ' $HOME/.pypirc)
export HATCH_INDEX_AUTH=${authline#  password = }
hatch publish
