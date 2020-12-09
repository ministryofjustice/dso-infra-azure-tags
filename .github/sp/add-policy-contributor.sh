#!/bin/bash
az role assignment create --role "Resource Policy Contributor" --assignee 'http://dso-infra-azure-tags' --scope '/providers/Microsoft.Management/managementGroups/747381f4-e81f-4a43-bf68-ced6a1e14edf'
