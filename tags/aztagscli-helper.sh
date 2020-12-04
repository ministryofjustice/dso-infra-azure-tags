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

get_file() {
  local dir=$1
  local file=$2
  while [[ $dir != '.' ]]; do
    if [[ -e $dir/$file ]]; then
      echo $dir/$file
      return
    fi
    dir=$(dirname $dir)
  done
  if [[ -e ./$file ]]; then
    echo $file
  fi
}

excludeids=$(find "$dir" -name exclude-ids.csv)
if [[ ! -z $excludeids ]]; then
  excludeids="--excludeids $excludeids"
fi

tagsupport=$(get_file "$dir" tag-support.csv)
if [[ ! -z $tagsupport ]]; then
  tagsupport="--tagsupport $tagsupport"
fi

files=$(find $dir -name '*.txt')

echo python3 $aztagscli $tagsupport $excludeids $@ -- ${files}
python3 $aztagscli $tagsupport $excludeids $@ -- ${files}
