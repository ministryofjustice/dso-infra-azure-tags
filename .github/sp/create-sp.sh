#!/bin/bash

echo "Automatically detecting subscription IDs from ../../tags/"
IDS=$(cat ../../tags/*/subscription.txt | grep -v id)

if [[ -z $IDS ]]; then
  echo "Couldn't find any subscriptions"
  exit 1
fi

SPFILE=sp
SPNAME=dso-infra-azure-tags
SECRETNAME=General-GitHub-DSOInfraAzureTags-SP
ROLE="Tag Contributor" # Contributor required for resource group tag changes 

create_sp() {
  echo az ad sp create-for-rbac -n "http://$SPNAME" --role "$ROLE" --scopes ${IDS} --sdk-auth' > ' $SPFILE
  az ad sp create-for-rbac -n "http://$SPNAME" --role "$ROLE" --scopes ${IDS} --sdk-auth > $SPFILE
}

upload_to_keyvault() {
  echo az keyvault secret set --subscription 1d95dcda-65b2-4273-81df-eb979c6b547b \
    --vault-name dso-passwords-prod \
    --name $SECRETNAME \
    --description "base64 encoded $SPNAME service principal" \
    --encoding base64 \
    --file $SPFILE
  az keyvault secret set --subscription 1d95dcda-65b2-4273-81df-eb979c6b547b \
    --vault-name dso-passwords-prod \
    --name $SECRETNAME \
    --description "base64 encoded $SPNAME service principal" \
    --encoding base64 \
    --file $SPFILE
}

upload_to_github() {
  cat $SPFILE
  echo "Please upload to github.  You can use Agoney's snazzy script"
  echo python ../../dso-useful-stuff/github-api/upsert_repo_secret.py --secret_url https://dso-passwords-prod.vault.azure.net/secrets/General-GitHub-$SECRETNAME dso-infra-azure-tags AZURE_CREDENTIALS
}

SPFILE=$(mktemp)
create_sp && upload_to_keyvault && upload_to_github
rm -f $SPFILE
