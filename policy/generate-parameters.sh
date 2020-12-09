#!/bin/bash
#Auto generate from existing settings

cd ../tags
output=$(./aztagscli-helper.sh . -vvv)

echo "{"

tags=(service application environment_name)
tagfields=(serviceTagValues applicationTagValues environmentNameTagValues)
numtags=${#tags[@]}

for ((i=0; i<$numtags; i++)); do
  tag=${tags[i]}
  tagfield=${tagfields[i]}
  echo "  \"${tagfield}\": {"
  echo "    \"value\": ["
  values=$(echo "$output" | grep "  ${tag}: " | cut -d: -f2 | sort -u | cut -c2-)
  lastvalue=$(echo "${values}" | tail -1)
  for value in $values; do
    if [[ $value == $lastvalue ]]; then
      echo "      \"$value\""
    else
      echo "      \"$value\","
    fi
  done
  echo "    ]"
  if (( i+1 == $numtags )); then
    echo "  }"
  else
    echo "  },"
  fi
done
echo "}"
