#!/bin/bash

set -e

usage() {
  echo "Usage: $0 create|update|delete|show [<dir1> .. <dirN>]"
  echo 
  echo "Manage policy assignments contained within given sub-directories, or all sub-directories if none specified"
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

apply_policy_set_definition_assignment() {
  local action=$1
  local policy=$2
  if [[ ! -e $policy ]]; then
    echo "Directory [$policy] doesn't exist"
    exit 1
  fi
  local policy_assignment_name=$(get_setting "policy_assignment_name" $dir/azurepolicyassignment.settings)
  local policy_assignment_display_name=$(get_setting "policy_assignment_display_name" $dir/azurepolicyassignment.settings)
  local policy_assignment_enforcement_mode=$(get_setting "policy_assignment_enforcement_mode" $dir/azurepolicyassignment.settings)
  local policy_assignment_scope=$(get_setting "policy_assignment_scope" $dir/azurepolicyassignment.settings)
  local policy_set_name=$(get_setting "policy_set_name" $dir/azurepolicyassignment.settings)

  if [[ -z $policy_assignment_name || -z $policy_assignment_display_name || -z $policy_assignment_enforcement_mode || -z $policy_assignment_scope || -z $policy_set_name ]]; then
    exit 1
  fi

  if [[ $action == "create" ]]; then
    echo az policy assignment create --name "$policy_assignment_name" --display-name "$policy_assignment_display_name" --enforcement-mode "$policy_assignment_enforcement_mode" --params azurepolicyassignment.parameters.json --policy-set-definition "$policy_set_name" --scope "$policy_assignment_scope"
    az policy assignment create --name "$policy_assignment_name" --display-name "$policy_assignment_display_name" --enforcement-mode "$policy_assignment_enforcement_mode" --params azurepolicyassignment.parameters.json --policy-set-definition "$policy_set_name" --scope "$policy_assignment_scope"
  elif [[ $action == "update" ]]; then
    echo az policy assignment update --name "$policy_assignment_name" --display-name "$policy_assignment_display_name" --enforcement-mode "$policy_assignment_enforcement_mode" --params azurepolicyassignment.parameters.json --policy-set-definition "$policy_set_name" --scope "$policy_assignment_scope"
    az policy assignment update --name "$policy_assignment_name" --display-name "$policy_assignment_display_name" --enforcement-mode "$policy_assignment_enforcement_mode" --params azurepolicyassignment.parameters.json --policy-set-definition "$policy_set_name" --scope "$policy_assignment_scope"
  elif [[ $action == "delete" ]]; then
    echo az policy assignment delete --name "$policy_assignment_name" --scope "$policy_assignment_scope"
    az policy assignment delete --name "$policy_assignment_name" --scope "$policy_assignment_scope"
  elif [[ $action == "show" ]]; then
    echo az policy assignment show --name "$policy_assignment_name" --scope "$policy_assignment_scope"
    az policy assignment show --name "$policy_assignment_name" --scope "$policy_assignment_scope"
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
  apply_policy_set_definition_assignment "$action" "$dir"
done
