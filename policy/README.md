# Setup of Azure DSO tag policy via AZ CLI

Consists of a generic `RequireTagAndRestrictValueOnResources` policy definition
to ensure a tag is defined, and the tag's value is one of a given set of values.
An initiative (or set-definition) that enforces `service`, `application` and 
`environment_name` tags on resources, and ensures the values match a 
pre-determined list.  And assignments for each of the DSO subscriptions that
uses these tags.

## Definition

A generic `Require a tag and restrict value on resources` policy definition to
ensure a tag is defined, and the tag's value is one of a given set of values.
The `az-policy-definition.sh` helper script wraps the az cli.  Example usage:

```
# ensure AZ logged in
cd definition

# show existing definitions
./az-policy-definition.sh show

# update existing definitions
./az-policy-definition.sh update
```

## Initiative 

A `DSO resource tag Initiative` initiative (or set-definition) that enforces 
`service`, `application` and `environment_name` tags on resources, and ensures 
the values match a pre-determined list.  The `az-policy-set-definition.sh` 
helper script wraps the az cli.  Example usage:


```
# ensure AZ logged in
cd set-definition

# show existing set-definitions
./az-policy-set-definition.sh show

# update existing set-definitions
./az-policy-set-definition.sh update
```

## Assignment

Assign the initiative to all relevant subscriptions.  The supported tag values
are defined in assignment/azurepolicyassignment.parameters.json.  The
`az-policy-assignment.sh` helper script wraps the az cli.  Example usage:

```
# ensure AZ logged in
cd assignment

# show existing set-definitions
./az-policy-assignment.sh show

# update existing set-definitions
./az-policy-assignment.sh update
```

