# dso-infra-azure-tags

For management of resource tags within Azure, specifically Ministry of Justice 
HMPPS Azure accounts.

Contains an aztagscli for updating tags across multiple resources.  Tags can
be inherited from resourcegroup or subscription.

Contains github action workflows for deployment of tag changes.

Contains policy definitions and related az cli commands for enforcing tagging.

The `az tag` command is used for updating resource tags
The `az resource tag` command is used for updating resource groups

## Pipelines

The  Azure AD App (Service Principal) used by this repo's pipeline is called dso-infra-azure-tags and is managed in the [dso-infra-azure-ad](https://github.com/ministryofjustice/dso-infra-azure-ad/tree/main/applications) repository

## Source

See src/ directory.  Use `pydoc aztags` for documentation on code or 
`aztagscli --help` for command line usage.

## Usage

Tag definitions are grouped by subscription under the tags/ directory.  For example
tags/NOMSProduction1/service_app_component_env_desc/ contains definitions for
`service`, `application`, `component`, `environment_name` and `description` tags.

Each directory can have:

### exclude-ids.csv

Optional list of IDs that are explicitly excluded from tag updates.  For example, if they
persistently fail to update via az cli!

### tag-support.csv

A list of resource types that support tagging.  If not present, this will be downloaded
automatically from [here](https://raw.githubusercontent.com/tfitzmac/resource-capabilities/master/tag-support.csv)

### inherit.*.txt

Pipe separated file.  Column headers should include "id" and any number of tags.x columns,
where x would be the tag name, e.g. tag.service.  The ID column can represent either a 
subscription (/subscriptions/xyz), a resource group, or a resource. The tags.x columns
should contain the associated tag value. Leave the column blank if you don't want to
set the tag for this particular resource. Use `:novalue:` if you want to set a blank
tag value.

Tags are inherited to child resources.  The most specific tag definition is used.
For example, you can define default subscription and resourcegroup tag values which are
used if a resource isn't defined.

### *.txt

Exactly the same format as the inherit files EXCEPT the tags are not inherited
to child resources.

### Example usage

```
# show tag differences across all directories
cd tags
./aztagscli-helper .
```

```
# Apply tag changes specified in NOMSProduction1/service_app_component_env_desc.
# User must enter "yes" to confirm changes.  Apply incrementally, i.e. do not
# delete any tags.
cd tags
./aztagscli-helper NOMSProduction1/service_app_component_env_desc -a
```

Remove an existing tag from all resources

```
# To remove an existing tag, first download all existing tags
cd tags
./generate-from-existing-tags.sh .

# Edit the tag files accordingly.  For example, to remove the
# resourceGroup tag from all resources, simply remove the file
rm tags.resourceGroup.txt

# Apply the changes (non-incrementally, i.e. delete missing tags)
./aztagscli-helper . -a --changetypes all
```

## Azure DSO tags

The majority of resources are not in terraform so this repo is used to apply tag
changes.  The "Azure DSO" googlesheet is used as the source data for defining
the service, application, component, environment and description for each
resource.

In particular:
- The `subscriptionOverview` tab defines default tags for subscriptions 
- The `rgstags` tab defines default tags for resource groups
- The `endpoints` tab defines tags for load balancers and app gateways
- The `environments` tab defines tags for VMs
- The `resourcetagsOverride` defines tags for individual resources

Download the subscriptionOverview, rgstags and resourcetags tabs "TSVs" into ~/Downloads
Run the `generate-from-azure-dso-sheet.sh` to update the tag files in this repo.

Terraform: Keep terraform in sync with any changes.  In particular:
- The `hmpps-fixngo-terraform` repo
- The `dso-infra-azure-fixngo` repo
- The `nomis-api-terraform-azure` repo.

## PyDoc

```
Help on module aztags:

NAME
    aztags - Manage updating of Azure tags across multiple resources and subscriptions.

DESCRIPTION
    Define desired tags in CSV or pipe separated files.  Retrieve (or load)
    list of resource types that support tagging.  Retrieve (or load) existing
    resource tags.  Calculate the difference.  Write the differences to file
    or apply the tag changes using az cli.

    If a filename describing desired start starts with "inherit", the tags are
    inherited to any child resources.
    Use ':novalue:' to represent a tag that has no value rather than a blank.
    A blank means don't set the tag for that particular ID

CLASSES
    builtins.object
        AzTags

    class AzTags(builtins.object)
     |  AzTags(change_types_str='inc', filter_ids=None, verbose=None, min_scope=None, max_scope=None)
     |
     |  Class for updating azure resource tags en-masse
     |
     |  Methods defined here:
     |
     |  __init__(self, change_types_str='inc', filter_ids=None, verbose=None, min_scope=None, max_scope=None)
     |      Initialise AzTags object
     |
     |      Parameters:
     |          change_types            Which type of tag changes to apply
     |                                  'inc' = incremental only
     |                                  'all' = all changes
     |                                  'ADD,UPDATE' = add and update etc..
     |          filter_ids:             If set, only match resources matching all
     |                                  regexs within this list of strings
     |          verbose:                Enable extra debug.
     |                                  The higher the number, the more debug
     |          min_scope:              If defined, only resource IDs that have >=
     |                                  forward slashes than this value will be
     |                                  updated.  Use to prevent resource-groups
     |                                  from being updated.
     |          max_scope:              If defined, only resource IDs that have <=
     |                                  forward slashes than this value will be
     |                                  updated.
     |
     |  add_csvs(self, filenames, separator=None)
     |      Add a list of CSVs containing resource IDs and tags
     |
     |      Parameters:
     |      filenames (list of strings): list of filenames to parse
     |      separator:                   optional CSV delimiter, auto if not set
     |
     |  calculate_tag_changes(self)
     |      Compare input CSVs with actual tags and calculate changes
     |
     |  display_existing_tags(self)
     |      Display all existing resources and tag values
     |
     |  display_tags_to_update(self)
     |      Display the planned changes to the console
     |
     |  get_existing_tags_from_az_cli(self)
     |      Use the az cli to query all resources from relevant subscriptions
     |      and their associated tags and store in an internal tag dictionary.
     |      Alternatively use get_existing_tags_from_json to load directly from
     |      json.
     |
     |  get_existing_tags_from_json(self, resource_json_str, resourcegroup_json_str, subscription_json_str)
     |      Use the provided json (in az cli resource list format) to add all
     |      resources and associated tags to the internal tag dictionary.
     |
     |  get_existing_tags_from_json_file(self, resource_json_filename, resourcegroup_json_filename, subscription_json_filename)
     |      Use the provided json files (in az cli resource list format) to
     |      add all resources and associated tags to the internal tag dictionary.
     |
     |  load_excluded_ids(self, filename)
     |      load CSV containing excluded resource IDs
     |
     |  load_supported_tags(self, filename=None)
     |      download CSV containing Azure resources that support tags
     |
     |  prune_tag_changes(self)
     |      Remove resources that have no change froms update list
     |
     |  update_all_tags(self, dryrun, max_failed_updates=10)
     |      Use az cli to implement all proposed tag changes
     |
     |  write_existing_tags_to_csv(self, filename, tags, separator=None)
     |      Create a CSV file for existing tags
     |
     |      Parameters:
     |      filename: filename to write to
     |      tags:     list of tags to write
     |      separator: CSV separator
     |
     |  ----------------------------------------------------------------------
     |  Data descriptors defined here:
     |
     |  __dict__
     |      dictionary for instance variables (if defined)
     |
     |  __weakref__
     |      list of weak references to the object (if defined)

DATA
    AZCLI_TIMEOUT_SECS = 300
    TAGVALUE_NONE = ':novalue:'
    TAG_ADD = 0
    TAG_CHANGE_STRS = ['ADD', 'UPDATE', 'KEEP', 'LEAVE', 'DEL', 'SWAP']
    TAG_CHANGE_TYPES = [0, 1, 2, 3, 4, 5]
    TAG_DEL = 4
    TAG_LEAVE = 3
    TAG_NO_UPDATE = 2
    TAG_SWAP = 5
    TAG_UPDATE = 1

FILE
    /Users/dominicrobinson/Source/dso-infra-azure-tags/src/aztags.py

```
