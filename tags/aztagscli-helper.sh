#!/bin/bash
aztagscli=../src/aztagscli.py
dir=$1
shift 1

if [[ ! -e $aztagscli ]]; then
  echo "Cannot find aztagscli script: $aztagscli"
  exit 1
fi

if [[ ! -e $dir ]]; then
  echo Directory $dir does not exist
  exit 1
fi

excludeids=
if [[ -e $dir/exclude-ids.csv ]]; then
  excludeids="--excludeids $dir/exclude-ids.csv"
fi

tagsupport=
if [[ -e tag-support.csv ]]; then
  tagsupport="--tagsupport tag-support.csv"
fi

files=$(find $dir -name '*.txt')

echo python3 $aztagscli $tagsupport $excludeids $@ ${files}
python3 $aztagscli $tagsupport $excludeids $@ ${files}


