# dso-infra-azure-tags

For management of resource tags within Azure, specifically Ministry of Justice 
HMPPS Azure accounts.

Contains an aztagscli for updating tags across multiple resources.  Tags can
be inherited from resourcegroup or subscription.

Contains github action workflows for deployment of tag changes.

## Source

See src/ directory.  Use `pydoc aztags` for documentation on code or 
`aztagscli --help` for command line usage.

## Resources 

List of resource types that support tags is downloaded from 
[here](https://raw.githubusercontent.com/tfitzmac/resource-capabilities/master/tag-support.csv)

## Tag Changes

Desired tags are defined under tags/ directory. 





