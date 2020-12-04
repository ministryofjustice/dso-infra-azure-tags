#!/bin/bash

echo "Automatically detecting subscription IDs from ../../tags/"
IDS=$(cat ../../tags/*/subscription.txt | grep -v id)

if [[ -z $IDS ]]; then
  echo "Couldn't find any subscriptions"
  exit 1
fi

for ID in $IDS; do
  sub_id=$(echo $ID | cut -d'/' -f3)
  echo "Checking $ID"
  az account set -s $sub_id
  az role assignment list --assignee 'http://dso-infra-azure-tags' --query '[*].[roleDefinitionName, id]' -o tsv
done

echo "To delete assignments, use az role assignment delete --id 'xxxx'"

