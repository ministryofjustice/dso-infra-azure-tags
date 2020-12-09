#!/bin/bash

set -e

usage() {
  echo "Usage: $0 create|update|delete|show [<dir1> .. <dirN>]"
  echo 
  echo "Manage policy definitions contained within given sub-directories, or all sub-directories if none specified"
}

get_setting() {
  local setting=$(grep "^$1=\"" $2 | cut -d\" -f2)
  if [[ -z $setting ]]; then
    setting=$(grep "^$1='" $2 | cut -d\' -f2)
  fi
  if [[ -z $setting ]]; then
    setting=$(grep "^$1=" $2 | cut -d= -f2)
  fi
  if [[ -z $setting ]]; then
    echo "Setting [$1] not found in $2" >&2
  fi
  echo $setting
}

apply_policy_definition() {
  local action=$1
  local policy=$2
  if [[ ! -e $policy ]]; then
    echo "Directory [$policy] doesn't exist"
    exit 1
  fi
  local policy_name=$(get_setting "policy_name" $dir/azurepolicy.settings)
  local policy_display_name=$(get_setting "policy_display_name" $dir/azurepolicy.settings)
  local policy_description=$(get_setting "policy_description" $dir/azurepolicy.settings)
  local policy_management_group=$(get_setting "policy_management_group" $dir/azurepolicy.settings)
  local policy_metadata=$(get_setting "policy_metadata" $dir/azurepolicy.settings)
  if [[ -z $policy_name || -z $policy_display_name || -z $policy_description || -z $policy_management_group || -z $policy_metadata ]]; then
    exit 1
  fi

  if [[ $action == "create" ]]; then
    echo az policy definition create --name "$policy_name" --display-name "$policy_display_name" --description "$policy_description" --rules "$policy/azurepolicy.rules.json" --params "$policy/azurepolicy.parameters.json" --mode indexed --management-group "$policy_management_group" --metadata "$policy_metadata"
    az policy definition create --name "$policy_name" --display-name "$policy_display_name" --description "$policy_description" --rules "$policy/azurepolicy.rules.json" --params "$policy/azurepolicy.parameters.json" --mode indexed --management-group "$policy_management_group" --metadata "$policy_metadata"
  elif [[ $action == "update" ]]; then
    echo az policy definition update --name "$policy_name" --display-name "$policy_display_name" --description "$policy_description" --rules "$policy/azurepolicy.rules.json" --params "$policy/azurepolicy.parameters.json" --mode indexed --management-group "$policy_management_group" --metadata "$policy_metadata"
    az policy definition update --name "$policy_name" --display-name "$policy_display_name" --description "$policy_description" --rules "$policy/azurepolicy.rules.json" --params "$policy/azurepolicy.parameters.json" --mode indexed --management-group "$policy_management_group" --metadata "$policy_metadata"
  elif [[ $action == "delete" ]]; then
    echo az policy definition delete --name "$policy_name" --management-group "$policy_management_group"
    az policy definition delete --name "$policy_name" --management-group "$policy_management_group"
  elif [[ $action == "show" ]]; then
    echo az policy definition show --name "$policy_name" --management-group "$policy_management_group"
    az policy definition show --name "$policy_name" --management-group "$policy_management_group"
  else
    echo "Unknown action [$action].  Expected create|update|delete|show"
  fi
  
}

action=$1
if [[ -z $action ]]; then
  usage
  exit 1
fi
shift

dirs=$@
if [[ -z $dirs ]]; then
  dirs=$(ls -1d -- */ | sed 's/\/$//')
fi

for dir in $dirs; do
  apply_policy_definition "$action" "$dir"
done
