#Copyright (c) 2020 Ministry Of Justice

#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:

#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.

#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.

"""Manage updating of Azure tags across multiple resources and subscriptions.

Define desired tags in CSV or pipe separated files.  Retrieve (or load)
list of resource types that support tagging.  Retrieve (or load) existing
resource tags.  Calculate the difference.  Write the differences to file
or apply the tag changes using az cli.

If a filename describing desired start starts with "inherit", the tags are
inherited to any child resources.
Use ':novalue:' to represent a tag that has no value rather than a blank.
A blank means don't set the tag for that particular ID
"""

import pandas
import json
import subprocess
import urllib.request
import csv
import re
import os
import time

# timout AZ CLI commands after this
AZCLI_TIMEOUT_SECS = 300

# use this to represent an empty tag value.
TAGVALUE_NONE = ':novalue:'

# the tag change_type required
# TAG_ADD       resource is defined in tag files but missing a specified tag
# TAG_UPDATE    resource is defined but has different tag to the specified one
# TAG_NO_UPDATE resource is defined and has tag matching the specified one
# TAG_LEAVE     resource is defined and has a tag which isn't specified
# TAG_DEL       same as TAG_LEAVE except remove this tag during the apply
# TAG_SWAP      resource has a tag name that clashes (Service versus service)

TAG_ADD = 0
TAG_UPDATE = 1
TAG_NO_UPDATE = 2
TAG_LEAVE = 3
TAG_DEL = 4
TAG_SWAP = 5
TAG_CHANGE_TYPES = [TAG_ADD, TAG_UPDATE, TAG_NO_UPDATE,
                    TAG_LEAVE, TAG_DEL, TAG_SWAP]
TAG_CHANGE_STRS = ['ADD', 'UPDATE', 'KEEP', 'LEAVE', 'DEL', 'SWAP']

class AzTags:
    ''' Class for updating azure resource tags en-masse '''

    def __init__(self,
                 change_types_str='inc',
                 filter_ids=None,
                 verbose=None,
                 min_scope=None,
                 max_scope=None,
                 skiptags=None):
        """ Initialise AzTags object

        Parameters:
            change_types            Which type of tag changes to apply
                                    'inc' = incremental only
                                    'all' = all changes
                                    'ADD,UPDATE' = add and update etc..
            filter_ids:             If set, only match resources matching all
                                    regexs within this list of strings
            verbose:                Enable extra debug.
                                    The higher the number, the more debug
            min_scope:              If defined, only resource IDs that have >=
                                    forward slashes than this value will be
                                    updated.  Use to prevent resource-groups
                                    from being updated.
            max_scope:              If defined, only resource IDs that have <=
                                    forward slashes than this value will be
                                    updated.
            skiptags:               List of tags. Skip resources which have
                                    these tags.
        """

        (ok, change_types) = self.__str_to_change_types(change_types_str)
        if not ok:
            raise Exception('Bad changetype argument: {}'.format(change_types))

        # list of tag change types to apply, e.g. TAG_ADD
        self.__change_types = change_types

        # level of verbosity (1,2,3 etc...)
        self.__verbose = verbose

        # limits which resources to update (scope = number of / in ID)
        self.__min_scope = min_scope
        self.__max_scope = max_scope

        # dictionary of resources that support tags (downloaded from github)
        # [providerName/resourceType] = Boolean
        self.__supported_tags = {}

        # list of explicitly excluded IDs
        # [id] = Boolean
        self.__excluded_ids = {}

        # optional list of regexes to filter resource IDs by
        # uses the case_sensitive_id for matching, i.e. resourcegroup name in
        # lower case
        self.__filter_ids = filter_ids

        # annoyingly resourcegroup name isn't case sensitive.  This provides a
        # mapping between a case_sensitive_id (where resourcegroup) is changed
        # to lowercase, and the original ID as stored in Azure
        self.__case_sensitive_ids = {}

        # dictionary of existing resources types [resource_id] = type
        self.__resource_ids_type = {}

        # dictionary of resources that aren't taggable
        # [resource_id] = (verbose-level, reason)
        self.__not_taggable_resources = {}

        # dictionary of existing values [resource_id][tag] = tagvalue
        # NOTE resource_id are converted to lowercase as resource group names
        # are not case sensitive.
        self.__tag_dict = {}

        # dictionary of tags to update
        # [sub_id][resource_id][tag] = [ (change_type, value, oldvalue) ]
        self.__resources_to_update = {}

        # dictionary of resource scoping [id] = scope
        # tracks whether resources are defined at resource, rg or sub level
        self.__resources_scope = {}

        # for pretty output
        self.__max_existing_tag_strlen = 0
        self.__max_tag_strlen = 0
        self.__max_tagvalue_strlen = 0

        # list of parsed CSV as a pandas dataframe
        self.__dfs = []

        # all CSVs combined into single pandas dataframe
        self.__combined_df = None

        # List of tags. Skip resources which have these tags.
        self.__skiptags = skiptags

    def __get_tag_change_str(self, change_type):
        ''' return string representing the tag change type '''
        return TAG_CHANGE_STRS[change_type]

    def __str_to_change_type(self, change_type_str):
        ''' convert a string into a change type '''
        for tag in TAG_CHANGE_TYPES:
            if change_type_str.upper() == TAG_CHANGE_STRS[tag]:
                return tag
        return None

    def __str_to_change_types(self, change_types_str):
        ''' convert a comma separate string into a list of change types '''
        if not change_types_str:
            return (False, 'at least one change type must be specified')
        if change_types_str.lower() == 'all':
            return (True, [TAG_ADD, TAG_UPDATE, TAG_NO_UPDATE,
                           TAG_DEL, TAG_SWAP])
        elif change_types_str.lower() == 'inc':
            return (True, [TAG_ADD, TAG_UPDATE, TAG_NO_UPDATE,
                           TAG_LEAVE, TAG_SWAP])
        else:
            change_types = []
            change_type_strs = change_types_str.split(',')
            for change_type_str in change_type_strs:
                change_type = self.__str_to_change_type(change_type_str)
                if change_type is None:
                    return (False, 'unknown type {}'.format(change_type_str))
                elif change_type in change_types:
                    return (False, 'duplicate type {}'.format(change_type_str))
                change_types += [change_type]
            if change_types:
                return (True, change_types)
            else:
                return (False, 'no change types defined')

    def load_supported_tags(self, filename=None):
        ''' download CSV containing Azure resources that support tags '''
        if filename:
            f = open(filename, 'r')
            text = f.read()
        else:
            url = ('https://raw.githubusercontent.com'
                   '/tfitzmac/resource-capabilities/master/tag-support.csv')
            print('Downloading tag-support from {}'.format(url))
            response = urllib.request.urlopen(url)
            data = response.read()      # a `bytes` object
            text = data.decode('utf-8')

        header = True
        for row in csv.reader(text.splitlines(), delimiter=','):
            if header:
                if (row[0] != 'providerName' or row[1] != 'resourceType'
                        or row[2] != 'supportsTags'):
                    raise Exception(
                        'Unexpected columns in tags-support.csv {}'.
                        format(row))
                header = False
            else:
                key = row[0] + '/' + row[1]
                is_supported = row[2].lower() == 'true'
                self.__supported_tags[key.lower()] = is_supported

    def load_excluded_ids(self, filename):
        ''' load CSV containing excluded resource IDs '''
        print('Parsing exclude file {}'.format(filename))
        f = open(filename, 'r')
        text = f.read()
        header = True
        for row in csv.reader(text.splitlines(), delimiter=','):
            if header:
                if row[0] != 'id':
                    raise Exception(
                        'Unexpected columns in filename {}'.
                        format(row))
                header = False
            else:
                case_sensitive_id = self.__get_case_sensitive_id(row[0])
                self.__excluded_ids[case_sensitive_id] = True

    def __add_printable_id(self, case_sensitive_id, print_id):
        ''' associate a case_sensitive_id with original ID '''
        if case_sensitive_id not in self.__case_sensitive_ids:
            self.__case_sensitive_ids[case_sensitive_id] = print_id

    def __get_printable_id(self, case_sensitive_id):
        ''' return original ID as referenced in Azure data '''
        if case_sensitive_id in self.__case_sensitive_ids:
            return self.__case_sensitive_ids[case_sensitive_id]
        else:
            return case_sensitive_id

    def __add_resource_id_type(self, case_sensitive_id, resourcetype):
        ''' associate resource type with resource id '''
        self.__resource_ids_type[case_sensitive_id] = resourcetype.lower()

    def __is_resource_id_filtered_out(self, resource_id):
        ''' check if resource_id matches configured RegExes '''
        if self.__filter_ids:
            for regex in self.__filter_ids:
                if not re.search(regex, resource_id):
                    return True
        return False

    def __is_resource_taggable(self, case_sensitive_id):
        """ check whether given resource id supports tagging
        Return (taggable, verbose_level_reason)
        Where:
            taggable: true/false depending on whether resource taggable
            verbose_level: level of verbosity to display this
            reason: why it can't be tagged
        """

        print_id = self.__get_printable_id(case_sensitive_id)

        scope = self.__get_resource_scope(case_sensitive_id)
        if self.__min_scope and scope < self.__min_scope:
            return (False, 4, 'SKIPPING resource less than minscope')
        if self.__max_scope and scope > self.__max_scope:
            return (False, 4, 'SKIPPING resource exceeds maxscope')

        if case_sensitive_id in self.__excluded_ids:
            return (False, 2, 'SKIPPING excluded resource')
        if print_id in self.__excluded_ids:
            return (False, 2, 'SKIPPING excluded resource')

        if self.__is_resource_id_filtered_out(case_sensitive_id):
            return (False, 3, 'SKIPPING filtered out resource')

        if self.__get_resource_scope(case_sensitive_id) == 2:
            return (False, 2, 'SKIPPING subscription resource ID')

        if self.__skiptags:
            for tag in self.__skiptags:
                if tag in self.__tag_dict[case_sensitive_id]:
                    return (False, 2, ('SKIPPING resource has one or more'
                                       ' skipped tags'))

        if not case_sensitive_id in self.__resource_ids_type:
            return (False, None, 'WARNING ignoring resource with unknown type')

        resource_type = self.__resource_ids_type[case_sensitive_id]
        if not resource_type:
            return (False, None, 'WARNING ignoring resource with bad type')

        provider_resource = resource_type
        if not provider_resource in self.__supported_tags:
            return (False, None, ('WARNING ignoring resource as type not '
                                  'found in supported tag CSV [{}]').format(
                                      provider_resource))

        return (self.__supported_tags[provider_resource], 2,
                'SKIPPING untaggable resource')

    def __get_sub_id(self, resource_id):
        ''' extract a subscription id from a resource id '''
        if not resource_id.startswith('/subscriptions/'):
            raise Exception(
                ('badly formatted resource ID.  '
                 '[{}] should start with /subscription/').format(resource_id))
        resource_id_components = resource_id.split('/')
        if len(resource_id_components[2]) != 36:
            raise Exception(
                ('badly formatted resource ID.  '
                 '[{}] is an invalid subscription id').format(resource_id))
        return resource_id_components[2]

    def __get_sub_id_list(self, resource_id_list):
        ''' extract a list of subscription ids from a list of resource ids '''
        return [self.__get_sub_id(resource_id)
                for resource_id in resource_id_list]

    def __get_case_sensitive_id(self, resource_id):
        ''' return an ID with lowercase resourcegroup name '''
        resource_id_components = resource_id.split('/')
        if len(resource_id_components) >= 5:
            resource_id_components[4] = resource_id_components[4].lower()
        return '/'.join(resource_id_components)

    def __get_case_sensitive_id_list(self, resource_id_list):
        ''' extract a list of lowercase ids from a list of resource ids '''
        return [self.__get_case_sensitive_id(resource_id)
                for resource_id in resource_id_list]

    def __detect_separator(self, filename):
        ''' auto detect separator based in file extension '''
        if filename[-4:] == '.txt':
            return '|'
        elif filename[-4:] == '.tsv':
            return '\t'
        elif filename[-4:] == '.csv':
            return ','
        return None

    def __parse_csv(self, filename, separator=None):
        ''' parse a CSV containing resource IDs and associated tags '''
        if not separator:
            separator = self.__detect_separator(filename)
            if not separator:
                separator = '|'

        # read as strings (otherwise 'True' may be represented as Boolean)
        df = pandas.read_csv(filename, sep=separator, dtype=str)

        # extract all column headers starting with tags.
        headers = df.columns.values
        tags = [header for header in headers if header.startswith('tags.')]

        # check expected column headers exist
        if 'id' not in headers:
            raise Exception(
                'badly formatted CSV.  Could not find id in CSV header {}'.
                format(headers))
        if 'x_sub_id' in headers or 'x_case_sensitive_id' in headers:
            raise Exception(
                'reserved column heading present in csv {}'.format(headers))

        # add subscription id as separate field for pivot
        df['x_sub_id'] = self.__get_sub_id_list(df['id'])

        # add a lowercase ID as resource group name not case sensitive
        df['x_case_sensitive_id'] = self.__get_case_sensitive_id_list(df['id'])

        # Determine whether tag inheritence should be used
        df.inherit = False
        if os.path.basename(filename).lower().startswith('inherit'):
            df.inherit = True

        if self.__verbose:
            print('  Parsed {}; inherit={}; {} id(s); {} tag type(s)'.format(
                filename, df.inherit, len(df['id']), len(tags)))

        return df

    def add_csvs(self, filenames, separator=None):
        """Add a list of CSVs containing resource IDs and tags

        Parameters:
        filenames (list of strings): list of filenames to parse
        separator:                   optional CSV delimiter, auto if not set
        """

        print('Parsing {} tag file(s)'.format(len(filenames)))
        self.__dfs += [self.__parse_csv(f, separator) for f in filenames]
        self.__combined_df = pandas.concat(self.__dfs)

    def __get_subs_pivot(self, df):
        """Extract unique subscription IDs and tags from a pandas dataframe

        Parameters:
        df: A pandas dataframe containing parsed CSV of IDs and tags

        Returns:
        List of tag values
        A pandas pivot table indexed on sub_id
        """

        # extract all column values starting with tags.
        tags = [
            column[5:] for column in df.columns.values.tolist()
            if column.startswith('tags.')
        ]

        # pivot to find unique subscription IDs within the dataframe
        subspivot = pandas.pivot_table(df,
                                       index=['x_sub_id'],
                                       values='x_case_sensitive_id',
                                       aggfunc='count')
        return (tags, subspivot)

    def __add_resource_to_tagdict(self, case_sensitive_id):
        ''' add given resource to the what's currently in Azure dictionary '''
        if case_sensitive_id not in self.__tag_dict:
            self.__tag_dict[case_sensitive_id] = {}

    def __add_tag_to_tagdict(self, case_sensitive_id, tag, value):
        ''' add given tag to the what's currently in Azure dictionary '''
        # ignore Azure internal tags
        if tag.startswith('hidden-') or tag.startswith('link:'):
            return
        self.__tag_dict[case_sensitive_id][tag] = value
        if (len(tag) < 30 and len(tag) > self.__max_existing_tag_strlen):
            self.__max_existing_tag_strlen = len(tag)

    def __add_existing_resources(self, az_resources_json,
                                 is_subscription=False):
        """Parse az cli JSON and add to the what's currently in Azure dict

        Parameters:
        az_resource_json: json output from az cmd such as az resource list
        is_subscription:  is the resource_json for subscriptions
        """

        for resource in az_resources_json:
            if 'id' not in resource:
                raise Exception(
                    'resource json has no "id" {}'.format(resource))

            if is_subscription:
                resource_id = '/subscriptions/' + resource['id']
            else:
                resource_id = resource['id']
            case_sensitive_id = self.__get_case_sensitive_id(resource_id)

            # provide lookup between this case sensitive id (resource group
            # name all lower case) and the orignal id
            self.__add_printable_id(case_sensitive_id, resource_id)

            # store the associated resource type.  For checking if the
            # resource actually supports tagging
            if not is_subscription:
                if 'type' not in resource:
                    raise Exception(
                        'resource json has no "type" {}'.format(resource))
                self.__add_resource_id_type(case_sensitive_id, resource['type'])

            # add the resource and all tags into our dictionary
            self.__add_resource_to_tagdict(case_sensitive_id)
            if 'tags' in resource and resource['tags']:
                for tag in resource['tags']:
                    self.__add_tag_to_tagdict(case_sensitive_id,
                                              tag,
                                              resource['tags'][tag])

    def __az_account_set(self, sub_id):
        ''' Use az cli to set the default account '''
        if self.__verbose:
            print('  Executing: az account set -s {}'.format(sub_id))
        subprocess.run(['az', 'account', 'set', '-s', sub_id],
                       check=True, timeout=AZCLI_TIMEOUT_SECS)

    def get_existing_tags_from_az_cli(self):
        """Use the az cli to query all resources from relevant subscriptions
        and their associated tags and store in an internal tag dictionary.
        Alternatively use get_existing_tags_from_json to load directly from
        json.
        """

        print('Retrieving azure resources')
        subspivot = self.__get_subs_pivot(self.__combined_df)[1]
        for sub_id in subspivot.index.values:
            self.__az_account_set(sub_id)

            if self.__verbose:
                print('  Executing: az resource list')
            cli_output = subprocess.run(['az', 'resource', 'list'],
                                        stdout=subprocess.PIPE,
                                        timeout=AZCLI_TIMEOUT_SECS,
                                        check=True).stdout.decode()
            az_json = json.loads(cli_output)
            self.__add_existing_resources(az_json)

            if self.__verbose:
                print('  Executing: az group list')
            cli_output = subprocess.run(['az', 'group', 'list'],
                                        stdout=subprocess.PIPE,
                                        timeout=AZCLI_TIMEOUT_SECS,
                                        check=True).stdout.decode()
            az_json = json.loads(cli_output)
            self.__add_existing_resources(az_json)

            if self.__verbose:
                print('  Executing: az account show')
            cli_output = subprocess.run(['az', 'account', 'show'],
                                        stdout=subprocess.PIPE,
                                        timeout=AZCLI_TIMEOUT_SECS,
                                        check=True).stdout.decode()
            az_json = json.loads('[' + cli_output + ']')
            self.__add_existing_resources(az_json,
                                          is_subscription=True)

    def get_existing_tags_from_json(self, resource_json_str,
                                    resourcegroup_json_str,
                                    subscription_json_str):
        """Use the provided json (in az cli resource list format) to add all
        resources and associated tags to the internal tag dictionary.
        """
        print('Loading azure resources')
        if resource_json_str:
            resources_json = json.loads(resource_json_str)
            self.__add_existing_resources(resources_json)
        if resourcegroup_json_str:
            resourcegroup_json = json.loads(resourcegroup_json_str)
            self.__add_existing_resources(resourcegroup_json)
        if subscription_json_str:
            subscription_json = json.loads(subscription_json_str)
            self.__add_existing_resources(subscription_json,
                                          is_subscription=True)

    def get_existing_tags_from_json_file(self, resource_json_filename,
                                         resourcegroup_json_filename,
                                         subscription_json_filename):
        """Use the provided json files (in az cli resource list format) to
        add all resources and associated tags to the internal tag dictionary.
        """
        resource_json_file = open(resource_json_filename, 'r')
        resource_json_str = resource_json_file.read()
        resourcegroup_json_file = open(resourcegroup_json_filename, 'r')
        resourcegroup_json_str = resourcegroup_json_file.read()
        subscription_json_file = open(subscription_json_filename, 'r')
        subscription_json_str = subscription_json_file.read()
        self.get_existing_tags_from_json(resource_json_str,
                                         resourcegroup_json_str,
                                         subscription_json_str)

    def __get_resource_scope(self, resource_id):
        """ Return a value that represents how specific a resource_id is.  Use
        the number of forward slashes as the value.  Always use the tag defined
        at the most specific level, i.e. a tag defined at a resource level takes
        precendence over an inherited tag at resource group level
        """
        return resource_id.count('/')

    def __get_scope_str(self, scope):
        ''' Return display string for scope '''
        if scope == 2:
            return 'sub'
        elif scope == 4:
            return 'rg'
        else:
            return str(scope)

    def __update_resource_scope(self, resource_id, scope, tag):
        """ Check whether given resource/tag has already been scoped
        at a more specific level.  If not, update the scope level
        i.e. a tag definition at resource level takes precedence over a
        tag definition at resource group

        Parameters:
        resource_id: the resource, resource group or subscription id
        scope:       is the tag defined at resource, rg, or sub level
        tag:         the name of the tag

        Returns:
        True:        The scope was updated
        False:       A more specific scope already defined
        """

        # If there's no existing scope, or the passed in scope is
        # greater >= existing scope, update the scope associated
        # with the resource_id.  Otherwise do nothing
        if resource_id not in self.__resources_scope:
            self.__resources_scope[resource_id] = {tag: scope}
        elif tag not in self.__resources_scope[resource_id]:
            self.__resources_scope[resource_id][tag] = scope
        else:
            if scope < self.__resources_scope[resource_id][tag]:
                return False
            elif scope == self.__resources_scope[resource_id][tag]:
                raise Exception(
                    'resource defined multiple times [{}] scope={} tags.{}'.
                    format(resource_id, self.__get_scope_str(scope), tag))
            self.__resources_scope[resource_id][tag] = scope
        return True

    def __add_to_resources_to_update(self, resource_id, tag,
                                     change_type, tagvalue, existing_tagvalue):
        """ Add the resource/tag/tagvalue to the resource update list.

        Parameters:
        resource_id:  the resource, resource group or subscription id
        tag:          the name of the tag
        change_type:  TAG_ADD etc...
        tagvalue:     the value to assign to the tag
        existing_tagvalue: the current value of the tag in Azure, or
                           None if it isn't currently set
        """
        sub_id = self.__get_sub_id(resource_id)
        if sub_id not in self.__resources_to_update:
            self.__resources_to_update[sub_id] = {
                resource_id: {
                    tag: (change_type, tagvalue, existing_tagvalue)
                }
            }
        elif resource_id not in self.__resources_to_update[sub_id]:
            self.__resources_to_update[sub_id][resource_id] = {
                tag: (change_type, tagvalue, existing_tagvalue)
            }
        else:
            self.__resources_to_update[sub_id][resource_id][tag] = (
                change_type, tagvalue, existing_tagvalue)

    def __calculate_tag_changes_in_resource(self, resource_id, scope, tag,
                                            tagvalue):
        """ Check whether any changes required for given resource and tag.

        Parameters:
        resource_id: the resource, resource group or subscription id
        scope:       whether tag is defined at sub, rg or resource level
        tag:         the name of the tag
        tagvalue:    the value to assign to the tag
        """

        # check if resource actual exists
        if resource_id not in self.__tag_dict:
            self.__not_taggable_resources[resource_id] = (
                None, 'WARNING: Resource does not exist')
            return

        # and does it support tagging?
        (taggable, verbose, reason) = self.__is_resource_taggable(resource_id)
        if not taggable:
            self.__not_taggable_resources[resource_id] = (verbose, reason)
            return

        # calculate max string sizes for pretty output
        if len(tag) < 30 and len(tag) > self.__max_tag_strlen:
            self.__max_tag_strlen = len(tag)
        if len(tagvalue) < 30 and len(tagvalue) > self.__max_tagvalue_strlen:
            self.__max_tagvalue_strlen = len(tagvalue)

        if self.__update_resource_scope(resource_id, scope, tag):
            change_type = TAG_ADD
            old_tagvalue = None
            if tag in self.__tag_dict[resource_id]:
                actual_tagvalue = self.__get_actual_tagvalue(tagvalue)
                if actual_tagvalue != self.__tag_dict[resource_id][tag]:
                    change_type = TAG_UPDATE
                    old_tagvalue = self.__tag_dict[resource_id][tag]
                else:
                    change_type = TAG_NO_UPDATE
            if change_type in self.__change_types:
                self.__add_to_resources_to_update(
                    resource_id, tag, change_type, tagvalue, old_tagvalue)
            else:
                self.__add_to_resources_to_update(
                    resource_id, tag, TAG_LEAVE, tagvalue, None)

    def __calculate_tag_changes_in_resource_children(self, resource_id,
                                                     scope, tag, tagvalue):
        ''' Calculate tag changes required for child resources '''
        resource_id_slash = resource_id + '/'
        for dict_resource_id in self.__tag_dict:
            if dict_resource_id.startswith(resource_id_slash):
                self.__calculate_tag_changes_in_resource(
                    dict_resource_id, scope, tag, tagvalue)

    def __calculate_tag_changes_in_resource_id(self, resource_id, tag,
                                               tagvalue, inherit):
        ''' Calculate tag changes for resource and child resources '''
        # 'scope' keeps track of how specific the tag definition is for
        # inherited tags.  The more slashes in the resource id, the
        # more specific it is (i.e. prefer a resource definition over an
        # inherited resource group definition)
        scope = self.__get_resource_scope(resource_id)
        self.__calculate_tag_changes_in_resource(
            resource_id, scope, tag, tagvalue)

        if inherit:
            self.__calculate_tag_changes_in_resource_children(
                resource_id, scope, tag, tagvalue)

    def __calculate_tag_changes_in_sub(self, df, sub_id, tag):
        """ Check whether any changes required for resources belonging to the
        given subscription.  Compare the input CSVs with the actual resources
        and add discrepencies into the update list
        """

        # pivot indexed on resource_id with the given tag values as a columns
        tagpivot = pandas.pivot_table(
            df[df.x_sub_id == sub_id],
            index='x_case_sensitive_id',
            columns='tags.' + tag,
            values='x_sub_id',
            aggfunc='count')

        # extract all possible tagvalues
        tagvalues = tagpivot.columns.values

        # extract pivot data, count of IDs for each tagvalue
        tagvalues_idcount = tagpivot.to_numpy()

        # iterate through all the possible tag values and resource ids
        j = 0
        for tagvalue in tagvalues:
            i = 0
            resource_ids = tagpivot[tagvalue].index.tolist()
            for resource_id in resource_ids:
                if tagvalues_idcount[i][j] >= 1:
                    self.__calculate_tag_changes_in_resource_id(
                        resource_id, tag, tagvalue, df.inherit)
                i += 1
            j += 1

    def __add_deleted_tags_to_update(self, sub_id, resource_id):
        ''' Figure out which tags can be deleted '''
        lowercase_tags = {} # [lowercase_tag] = tag
        update_dict = self.__resources_to_update[sub_id][resource_id]

        # Double-check the user hasn't specified the same tag twice
        for tag in update_dict:
            if tag.lower() in lowercase_tags:
                raise Exception(
                    'Resource has duplicate tags defined [{} {}] [{}]'.format(
                        lowercase_tags[tag.lower()], tag, resource_id))
            lowercase_tags[tag.lower()] = tag

        deltype = TAG_LEAVE
        if TAG_DEL in self.__change_types:
            deltype = TAG_DEL
        for tag in self.__tag_dict[resource_id]:
            if tag not in update_dict:
                if tag.lower() in lowercase_tags:
                    changetype = TAG_SWAP
                else:
                    changetype = deltype
                tagvalue = self.__tag_dict[resource_id][tag]
                self.__resources_to_update[sub_id][resource_id][tag] = (
                    changetype, tagvalue, None)

    def calculate_tag_changes(self):
        ''' Compare input CSVs with actual tags and calculate changes '''
        for df in self.__dfs:
            # pull out the unique subscription ID
            (tags, subspivot) = self.__get_subs_pivot(df)

            # iterate through all subscriptions
            for sub_id in subspivot.index.values:
                for tag in tags:
                    self.__calculate_tag_changes_in_sub(df, sub_id, tag)

        # now all the tags have been added, we can calculate the ones no
        # longer required if running in by resource mode
        for sub_id in self.__resources_to_update:
            for resource_id in self.__resources_to_update[sub_id]:
                self.__add_deleted_tags_to_update(sub_id, resource_id)

    def prune_tag_changes(self):
        ''' Remove resources that have no change froms update list '''
        orig = self.__resources_to_update.copy()
        self.__resources_to_update = {}

        actionable_changes = [TAG_ADD, TAG_UPDATE, TAG_DEL, TAG_SWAP]

        for sub_id in orig:
            for resource_id in orig[sub_id]:
                any_update = False
                for tag in orig[sub_id][resource_id]:
                    if orig[sub_id][resource_id][tag][0] in actionable_changes:
                        any_update = True
                if any_update:
                    for tag in orig[sub_id][resource_id]:
                        (change_type, tagvalue, existing_tagvalue) = orig[
                            sub_id][resource_id][tag]
                        self.__add_to_resources_to_update(
                            resource_id, tag, change_type, tagvalue,
                            existing_tagvalue)

    def __get_actual_tagvalue(self, csv_tagvalue):
        ''' convert a tagvalue read from CSV file (checks for :novalue:) '''
        if csv_tagvalue == TAGVALUE_NONE:
            return ''
        return csv_tagvalue

    def __get_csv_tagvalue(self, actual_tagvalue):
        ''' convert a tagvalue to format written to CSV file '''
        if actual_tagvalue:
            return actual_tagvalue
        return TAGVALUE_NONE

    def __get_tag_change_type(self, resource_id, tag):
        ''' return associated tag change type, TAG_ADD etc '''
        sub_id = self.__get_sub_id(resource_id)
        if sub_id not in self.__resources_to_update:
            return None
        if resource_id not in self.__resources_to_update[sub_id]:
            return None
        if tag not in self.__resources_to_update[sub_id][resource_id]:
            return None
        return self.__resources_to_update[sub_id][resource_id][tag][0]

    def __get_tagvalue_for_csv(self, resource_id, tag):
        ''' return tag value to add to CSV '''
        if resource_id not in self.__tag_dict:
            return None
        if tag not in self.__tag_dict[resource_id]:
            return None
        value = self.__get_csv_tagvalue(self.__tag_dict[resource_id][tag])
        tag_change = self.__get_tag_change_type(resource_id, tag)
        if not tag_change or tag_change in self.__change_types:
            return value
        return None

    def write_existing_tags_to_csv(self, filename, tags, separator=None):
        """ Create a CSV file for existing tags

        Parameters:
        filename: filename to write to
        tags:     list of tags to write
        separator: CSV separator
        """

        if not separator:
            separator = self.__detect_separator(filename)
            if not separator:
                separator = '|'
        f = None
        header = 'id'
        for tag in tags:
            header += '{}tags.{}'.format(separator, tag)

        for resource_id in self.__tag_dict:
            values = {}
            for tag in tags:
                value = self.__get_tagvalue_for_csv(resource_id, tag)
                if value:
                    values[tag] = value
            if values:
                line = self.__get_printable_id(resource_id)
                for tag in tags:
                    line += separator
                    if tag in values:
                        line += values[tag]
                if not f:
                    print('Creating {}'.format(filename))
                    f = open(filename, 'w')
                    f.write(header + os.linesep)
                f.write(line + os.linesep)

    def display_existing_tags(self):
        ''' Display all existing resources and tag values '''
        if self.__verbose:
            print('EXISTING TAGS')
        tagcount = {}
        for resource_id in self.__tag_dict:
            if self.__is_resource_taggable(resource_id)[0]:
                print_id = self.__get_printable_id(resource_id)

                if self.__verbose > 1:
                    print('  RESOURCE {}'.format(print_id))
                for tag in self.__tag_dict[resource_id]:
                    if tag in tagcount:
                        tagcount[tag] += 1
                    else:
                        tagcount[tag] = 1
                    if self.__verbose > 1:
                        print('  {}: {}'.format(
                            tag.rjust(self.__max_existing_tag_strlen),
                            self.__tag_dict[resource_id][tag]))
        if self.__verbose:
            for tag in tagcount:
                print('  TAG tags.{}: {} id(s)'.format(
                    tag.ljust(self.__max_existing_tag_strlen),
                    tagcount[tag]))
        return tagcount

    def __display_not_taggable_resources(self):
        ''' Display list of resources that aren't taggable '''
        for resource_id in self.__not_taggable_resources:
            (verbose, reason) = self.__not_taggable_resources[resource_id]
            print_id = self.__get_printable_id(resource_id)
            if not verbose or self.__verbose >= verbose:
                print('{}: {}'.format(reason, print_id))

    def display_tags_to_update(self):
        ''' Display the planned changes to the console '''
        self.__display_not_taggable_resources()

        total_id_count = 0
        total = [0 for i in TAG_CHANGE_TYPES]
        for sub_id in self.__resources_to_update:
            id_count = len(self.__resources_to_update[sub_id])
            sub_total = [0 for i in TAG_CHANGE_TYPES]

            print('SUB /subscriptions/{}'.format(sub_id))

            for resource_id in self.__resources_to_update[sub_id]:
                printed_id = False

                for tag in self.__resources_to_update[sub_id][resource_id]:
                    (change, value, oldvalue) = self.__resources_to_update[
                        sub_id][resource_id][tag]

                    scopedebug = ''
                    if tag in self.__resources_scope[resource_id]:
                        scope = self.__resources_scope[resource_id][tag]
                        scopedebug = '[' + self.__get_scope_str(scope) + ']'

                    fromstr = ''
                    if oldvalue:
                        fromstr = ' [from {}]'.format(
                            self.__get_actual_tagvalue(oldvalue))

                    sub_total[change] += 1
                    if self.__verbose or change != TAG_NO_UPDATE:
                        if not printed_id:
                            printed_id = True
                            print_id = self.__get_printable_id(resource_id)
                            print('  ID {}'.format(print_id[51:]))

                        print('    {} {} tags.{}: {}{}'.format(
                            self.__get_tag_change_str(change).ljust(6),
                            scopedebug.ljust(5),
                            tag.ljust(self.__max_tag_strlen),
                            self.__get_actual_tagvalue(value), fromstr))

            total_id_count += id_count
            for i in TAG_CHANGE_TYPES:
                total[i] += sub_total[i]

            debug = ''
            for i in TAG_CHANGE_TYPES:
                if sub_total[i]:
                    debug += '; {} tag(s) to {}'.format(
                        sub_total[i], self.__get_tag_change_str(i).lower())

            print('  SUMMARY {:>4} id(s) to update{}'.format(id_count, debug))

        debug = ''
        for i in TAG_CHANGE_TYPES:
            if total[i]:
                debug += '; {} tag(s) to {}'.format(
                    total[i], self.__get_tag_change_str(i).lower())

        print('TOTAL: {} id(s) skipped; {} id(s) to update{}'.format(
            len(self.__not_taggable_resources), total_id_count, debug))
        return total_id_count

    def __get_az_resource_tag_cmdline(self, resource_id, taglist,
                                      incremental_mode):
        ''' Get cmdline for updating tags using 'az resource tag' '''
        cmdline = ['az', 'resource', 'tag']
        if incremental_mode:
            cmdline += ['--is-incremental']
        cmdline += ['--ids', resource_id, '--tags']
        if taglist:
            cmdline += taglist
        else:
            cmdline += ['']
        return cmdline

    def __get_az_tag_cmdline(self, resource_id, taglist, incremental_mode):
        ''' Get cmdline for updating tags using 'az tag' '''
        cmdline = ['az', 'tag', 'update', '--operation']
        if incremental_mode:
            cmdline += ['Merge']
        else:
            cmdline += ['Replace']
        cmdline += ['--resource-id', resource_id, '--tags']
        if taglist:
            cmdline += taglist
        else:
            cmdline += ['']
        return cmdline

    def __az_update_tag(self, case_sensitive_id, taglist, incremental_mode,
                        dryrun, debugprefix=''):
        ''' Update tags for the given resource '''
        resource_id = self.__case_sensitive_ids[case_sensitive_id]

        # use "az tag" for resources and "az resource tag" for resource groups"
        # Because "az tag" will tag all child resources under a resource group
        # but not the actual resource group itself.
        if resource_id.count('/') > 5:
            cmdline = self.__get_az_tag_cmdline(resource_id, taglist,
                                                incremental_mode)
        else:
            cmdline = self.__get_az_resource_tag_cmdline(resource_id, taglist,
                                                         incremental_mode)
        print('[{}] {}'.format(debugprefix, ' '.join(cmdline)))
        if dryrun:
            return True
        isok = False
        try:
            if self.__verbose > 2:
                subprocess.run(cmdline,
                               timeout=AZCLI_TIMEOUT_SECS, check=True)
            else:
                subprocess.run(cmdline,
                               stdout=subprocess.PIPE,
                               timeout=AZCLI_TIMEOUT_SECS,
                               check=True).stdout.decode()
            isok = True
        except subprocess.CalledProcessError:
            pass
        return isok

    def __does_resource_have_tag_swaps(self, sub_id, resource_id):
        ''' return True if a tag name has changed case for given resource '''
        update_dict = self.__resources_to_update[sub_id][resource_id]
        for tag in update_dict:
            if update_dict[tag][0] == TAG_SWAP:
                return True
        return False

    def __get_update_tag_list_for_resource(self, sub_id, resource_id,
                                           change_types, with_duplicates=True):
        ''' Get list of tags for given resource to feed into az cli '''
        update_dict = self.__resources_to_update[sub_id][resource_id]

        # check for duplicate tag names
        lowercase_tags = {} # [lowercase] = count
        for tag in update_dict:
            if tag.lower() in lowercase_tags:
                lowercase_tags[tag.lower()] += 1
            else:
                lowercase_tags[tag.lower()] = 1

        # form list of tags to pass into az cli
        taglist = []
        for tag in update_dict:
            if with_duplicates or lowercase_tags[tag.lower()] == 1:
                change_type = update_dict[tag][0]
                value = update_dict[tag][1]
                if value == TAGVALUE_NONE:
                    value = ''
                if change_type in change_types:
                    taglist.append('{}={}'.format(tag, value))
        return taglist

    def __update_tag_by_resource(self, sub_id, case_sensitive_id,
                                 dryrun, debugprefix=''):
        ''' Update tags for given resource '''
        incremental_mode = True
        # check if a tag name's casing has changed, e.g. "env" to "ENV"
        # if so, we must update in two parts.  Firstly all changes apart
        # from the tag with the casing change.  And then add the casing change
        if self.__does_resource_have_tag_swaps(sub_id, case_sensitive_id):
            change_types = [TAG_ADD, TAG_UPDATE, TAG_NO_UPDATE,
                            TAG_LEAVE, TAG_DEL]
            taglist = self.__get_update_tag_list_for_resource(
                sub_id, case_sensitive_id, change_types, False)
            self.__az_update_tag(case_sensitive_id, taglist,
                                 False, dryrun, debugprefix)
            # Sometimes if you re-add the new tags too quick the tag
            # casing change doesn't apply.  Sleep a bit to try and avoid this
            if not dryrun:
                time.sleep(10)

            change_types = [TAG_ADD, TAG_UPDATE, TAG_LEAVE]
            if TAG_DEL in self.__change_types:
                incremental_mode = False
                change_types += [TAG_NO_UPDATE]
        else:
            change_types = [TAG_ADD, TAG_UPDATE]
            if TAG_DEL in self.__change_types:
                incremental_mode = False
                change_types += [TAG_NO_UPDATE, TAG_LEAVE]
        taglist = self.__get_update_tag_list_for_resource(
            sub_id, case_sensitive_id, change_types, True)
        return self.__az_update_tag(case_sensitive_id, taglist,
                                    incremental_mode, dryrun, debugprefix)

    def update_all_tags(self, dryrun, max_failed_updates=10):
        ''' Use az cli to implement all proposed tag changes '''
        # count total amount of resource IDs update
        n = 0
        for sub_id in self.__resources_to_update:
            n += len(self.__resources_to_update[sub_id])

        i = 1
        failed_ids = []
        for sub_id in self.__resources_to_update:
            if self.__resources_to_update[sub_id]:
                print('Updating tags for subscription {}'.format(sub_id))
                if not dryrun:
                    self.__az_account_set(sub_id)
                for resource_id in self.__resources_to_update[sub_id]:
                    debugprefix = '{}/{}'.format(i, n)
                    if not self.__update_tag_by_resource(sub_id, resource_id,
                                                         dryrun, debugprefix):
                        failed_ids += [resource_id]
                        if len(failed_ids) >= max_failed_updates:
                            break
                    i += 1
            if len(failed_ids) >= max_failed_updates:
                break
        if failed_ids:
            print('{} FAILED IDs'.format(len(failed_ids)))
            for case_sensitive_id in failed_ids:
                resource_id = self.__case_sensitive_ids[case_sensitive_id]
                print('{}'.format(resource_id))
            raise Exception('{} failed update(s)'.format(len(failed_ids)))

