#!/usr/bin/env bash
set -e

cd $(dirname "$0")
rm -rf dist
hatchling build
