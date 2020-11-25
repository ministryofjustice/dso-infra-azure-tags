#!/bin/bash

basedir=$(dirname $0)
output=$(python3 ${basedir}/../aztagscli.py --azresources ${basedir}/azresources.json --azrgs ${basedir}/azrgs.json --azsubs ${basedir}/azsubs.json ${basedir}/test1.csv ${basedir}/test2.csv -vvv --dryrun -a -y)

if [[ ! -z $1 ]]; then
  if [[ ! -e $1 ]]; then
    echo "Expected output file [$1] doesn't exist"
    exit 1
  fi
  expected=$(cat $1)
  if [[ "$output" != "$expected" ]]; then
    tmpfile=$(mktemp)
    echo "$output" > $tmpfile
    diff $tmpfile $1 || true
    rm -f $tmpfile
    echo "FAILED - differences in expected output"
    exit 1
  else
    echo "OK"
  fi
else
  echo "$output"
fi
