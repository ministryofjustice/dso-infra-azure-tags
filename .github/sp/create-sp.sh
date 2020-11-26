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

create_sp() {
  echo az ad sp create-for-rbac -n "http://$SPNAME" --role "Tag Contributor" --scopes ${IDS} --sdk-auth' > ' $SPFILE
  az ad sp create-for-rbac -n "http://$SPNAME" --role "Tag Contributor" --scopes ${IDS} --sdk-auth > $SPFILE
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
  echo "Please upload to github"
  #if [[ -z $GITHUB_CREDS ]]; then
  #  echo "Please set GITHUB_CREDS environment variable"
  #  echo " e.g. export GITHUB_CREDS=myusername:myPAT"
  #  exit 1
  #fi

  # TODO: should be automated.....  SEE
  # https://vaibhavsagar.com/blog/2020/05/04/github-secrets-api/

  #curl \ 
  # TODO token
  #  -H "Accept: application/vnd.github.v3+json" \
  #  https://api.github.com/repos/ministryofjustice/dso-infra-azure-tag/actions/secrets/public-key

  #curl \
  #  -u $GITHUB_CREDS \
  #  -H "Accept: application/vnd.github.v3+json" \
  #  https://api.github.com/repos/ministryofjustice/dso-infra-azure-tags/actions/secrets
}

SPFILE=$(mktemp)
create_sp && upload_to_keyvault && upload_to_github
rm -f $SPFILE
