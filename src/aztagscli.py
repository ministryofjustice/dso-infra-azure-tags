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

"""CLI for updating of Azure tags across multiple resources and subscriptions.

Define resources and associated tags in simple pipe separated files.  Retrieve
Azure resource tags using az cli.  Display summary of differences and then
optionally apply changes.  If tags are defined against resource groups or
subscriptions these are inherited by child resources.  The most specific
tag is always chosen.

Comma separated .csv, tab separted .tsv, or pipe separated .txt are supported.
CSV header must contain "id" and any number of "tags.xyz" field, where xyz is
the tag name.  Any other columns within the CSV are ignored.

Example usage:

    # dry run with plenty of debug
    aztagscli -vv -d tags1.txt tags2.txt

    # actual apply without interaction
    aztagscli -y -a tags1.txt tags2.txt
"""

import argparse
from aztags import AzTags

parser = argparse.ArgumentParser(
    description='Update Azure resource tags')

parser.add_argument('-v',
                    '--verbose',
                    action='count',
                    default=0,
                    help='Verbose output, or -vv for extra verbose')
parser.add_argument('-a', '--apply',
                    action='count',
                    help='Apply tag changes')
parser.add_argument('-d',
                    '--dryrun',
                    action='count',
                    help='Dryrun mode; if apply, print az cli commands')
parser.add_argument('-y', '--yes',
                    action='count',
                    help='No interaction')
parser.add_argument('--azresources',
                    nargs='?',
                    help=('Filename containing existing Azure resource '
                          'json file, e.g. from az resource list'))
parser.add_argument('--azrgs',
                    nargs='?',
                    help=('Filename containing existing Azure resource '
                          'group json file, e.g. from az group list'))
parser.add_argument('--azsubs',
                    nargs='?',
                    help=('Filename containing existing Azure subscription '
                          'json file, e.g. from az account list'))
parser.add_argument('--tagsupport',
                    nargs='?',
                    help=('Filename containing resources that support tags, '
                          'if not specified download automatically'))
parser.add_argument('--excludeids',
                    nargs='+',
                    help='Filename containing list of IDs to exclude')
parser.add_argument('--limit',
                    nargs='+',
                    help=('One or more RegExs.  Limit the resource IDs to '
                          'use.  ResourceGroup names will be in lower case'))
parser.add_argument('--savetagsfile',
                    nargs='?',
                    help=('Save existing tags to this file.  If --savetags '
                          'not specified, files are created for each tag. '
                          'e.g. SAVETAGSFILE.tag1.txt'))
parser.add_argument('--savetagsmode',
                    nargs='?',
                    default='DEL',
                    help=('Which type of tags to include in the save file. '
                          'all = all existing flags; '
                          'DEL = all flags which are not specified, i.e. '
                          ' would be deleted'))
parser.add_argument('--savetags',
                    nargs='+',
                    help=('Optional list of tags to include in file. '
                          'Use "all" to put all tags in single file.'))
parser.add_argument('--maxerrors',
                    type=int,
                    nargs='?',
                    default=10,
                    help='Bail out after this number of update errors')
parser.add_argument('--minscope',
                    type=int,
                    nargs='?',
                    help=('Limit update to resources IDs that have >= forward '
                          'slashes than this value.  Set to 5 to ignore '
                          'resource groups'))
parser.add_argument('--maxscope',
                    type=int,
                    nargs='?',
                    help=('Limit update to resources IDs that have <= forward '
                          'slashes than this value.  Set to 4 to limit to '
                          'resource groups'))
parser.add_argument('--changetypes',
                    nargs='?',
                    default='inc',
                    help=('Which type of tag changes to apply. '
                          'inc = incremental (add/updates only). '
                          'all = all changes.  Or any combination of '
                          'ADD UPDATE DEL, e.g. ADD,UPDATE'))
parser.add_argument('--skiptags',
                    nargs='+',
                    help='List of tags. Skip resources which have these tags.')
parser.add_argument('tagfile',
                    nargs='+',
                    help=('csv file with id and any number of tags.x, tags.y, '
                          'tags.z headers, where x, y and z are tag name'))

args = parser.parse_args()

aztags = AzTags(change_types_str=args.changetypes,
                filter_ids=args.limit,
                verbose=args.verbose,
                min_scope=args.minscope,
                max_scope=args.maxscope,
                skiptags=args.skiptags)

# figure out which resources are taggable
aztags.load_supported_tags(args.tagsupport)

# exclude IDs that are problematic, e.g. fail on az cli commands
if args.excludeids:
    for excludeids in args.excludeids:
        aztags.load_excluded_ids(excludeids)

# load the desired tag state
aztags.add_csvs(args.tagfile)

# load the existing tag state
if args.azresources or args.azrgs or args.azsubs:
    aztags.get_existing_tags_from_json_file(args.azresources,
                                            args.azrgs,
                                            args.azsubs)
else:
    aztags.get_existing_tags_from_az_cli()

# analyse the exisiing tags
tagcount = aztags.display_existing_tags()

# figure out the differences between desired and existing state
aztags.calculate_tag_changes()

# either dump the tags to file, or display + apply
if args.savetagsfile:
    if args.savetags:
        print('Writing existing tags to file')
        filename = args.savetagsfile
        if 'all' in args.savetags:
            aztags.write_existing_tags_to_csv(filename, tagcount)
        else:
            aztags.write_existing_tags_to_csv(filename, args.savetags)

    else:
        # tags are case sensitive(ish) but filenames may not be
        print('Writing existing tags [{}] to files'.format(len(tagcount)))
        taglower = {}
        for tag in tagcount:
            if tag.lower() in taglower:
                taglower[tag.lower()] += 1
                filename = (args.savetagsfile + '.' + tag + '.'
                            + str(taglower[tag.lower()]) +'.txt')
            else:
                taglower[tag.lower()] = 0
                filename = args.savetagsfile + '.' + tag + '.txt'
            aztags.write_existing_tags_to_csv(filename, [tag])
else:
    # remove resources that have no changes
    aztags.prune_tag_changes()

    # dump the proposed state change to console
    num_tags_to_update = aztags.display_tags_to_update()

    # apply the changes
    if args.apply:
        if num_tags_to_update:
            apply_changes = True
            if not args.yes:
                print()
                print('Enter yes to apply the above tag changes')
                apply_changes = input() == 'yes'
            if apply_changes:
                print()
                aztags.update_all_tags(args.dryrun, args.maxerrors)
        else:
            print()
            print('Nothing to apply.  Great success!')
