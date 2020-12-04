#!/bin/bash
set -e

# only saves the tags that are not currently defined elsewhere
# i.e. would otherwise be deleted in non-incremental mode
MODE=DEL

# save all tags, even if they are already defined
# MODE=all

dir=$1

if [[ -z "$dir" ]]; then
  echo "Usage: $0 <directory> [<tag1> .. <tagN>]"
  exit 1
fi

if [[ ! -x ./aztagscli-helper.sh ]]; then
  echo "Couldn't find aztagscli-helper.sh"
  exit 1
fi

filename=$dir/tags

shift 1
tags=$@

if [[ -z $tags ]]; then
  savetags=""
else
  savetags="--savetags $tags"

  for tag in $tags; do
    filename=${filename}.${tag}
  done
  filename=${filename}.txt
fi

./aztagscli-helper.sh $dir --changetypes "$MODE" -v --savetagsfile "$filename" $savetags

