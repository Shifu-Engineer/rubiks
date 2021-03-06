# (c) Copyright 2017-2018 OLX

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os

import output
import load_python
from command import Command
from .bases import CommandRepositoryBase, LoaderBase


class Command_readme(Command, CommandRepositoryBase, LoaderBase):
    """generate a README.md in the root of the repository explaining this repo"""

    repotext = """
        # {reponame}

        This repository is a rubiks repository, needing the rubiks tool to generate. It generates YAML for consumption by openshift or kubernetes.

        It has {clusterinfo}. Sources can be found in `{sources}/` and the output yaml will be generated in `{output}/` ({output_layout}).{pythonpath} Files containing confidential data {confidential}.

        You can regenerate the output by running `rubiks generate` in this directory.

        See the rubiks documentation and `rubiks list_objs` and `rubiks describe` for more information on the sources.

        This readme was auto-generated and can be regenerated by running `rubiks readme` in this directory.
               """

    def populate_args(self, parser):
        pass

    def run(self, args):
        self.loader_setup()
        r = self.get_repository()
        coll = load_python.PythonFileCollection(r)

        clusters = r.get_clusters()

        clusterinfo = ''
        if len(clusters) == 0:
            clusterinfo += '1 implicit cluster'
        elif len(clusters) == 1:
            clusterinfo += '1 explicit cluster'
        else:
            clusterinfo += '{} clusters'.format(len(clusters))
        if len(clusters) > 0:
            if r.is_openshift:
                cluster_types = set(['O'])
            else:
                cluster_types = set()
                for c in clusters:
                    if r.get_cluster_info(c).is_openshift:
                        cluster_types.add('O')
                    else:
                        cluster_types.add('K')
            def render_cluster(c):
                info = r.get_cluster_info(c)
                end = ''
                if len(cluster_types) == 2:
                    if info.is_openshift:
                        end = ' (O)'
                    else:
                        end = ' (K)'
                if info.is_prod:
                    return '**' + c + '**' + end
                return '*' + c + '*' + end
            clusterinfo += ' ({})'.format(', '.join(map(render_cluster, clusters)))
            output_layout = '`{}/<cluster>/<global>.yaml` or `{}/<cluster>/<namespace>/<objects>.yaml`'
            if len(cluster_types) == 1:
                if tuple(cluster_types)[0] == 'O':
                    clusterinfo += ', all clusters configured to generate openshift-specifics'
            else:
                clusterinfo += ', clusters have mixed configuration - (O) openshift, (K) kubernetes'
        else:
            if r.is_openshift:
                clusterinfo += ", configured to generate openshift-specifics"
            output_layout = '`{}/<global>.yaml` or `{}/<namespace>/<objects>.yaml`'
        if len(clusters) > 0:
            if r.output_policybinding or all(map(lambda x: r.get_cluster_info(x).output_policybinding, clusters)):
                clusterinfo += '. RoleBindings referring to Roles will always generate PolicyBindings instead'
            else:
                pb_clusters = list(filter(lambda x: r.get_cluster_info(x).output_policybinding, clusters))
                if len(pb_clusters) > 0:
                    clusterinfo += '. RoleBindings referring to Roles will generate PolicyBindings instead in'
                    if len(pb_clusters) == 1:
                        clusterinfo += ' ' + pb_clusters[0]
                    else:
                        clusterinfo += ' ' + ', '.join(pb_clusters[:-1]) + ', and ' + pb_clusters[-1]
        else:
            if r.output_policybinding:
                clusterinfo += '. RoleBindings referring to Roles will always generate PolicyBindings instead'
        output_layout = output_layout.format(r.outputs, r.outputs)

        pythonpath = ''
        if len(r.pythonpath) != 0:
            pythonpath = ' While running, `$PYTHONPATH` will be set to search: ' + \
                ', '.join(map(lambda x: '`{}/`'.format(os.path.relpath(x, r.basepath)), r.pythonpath)) + '.'

        cf_type = coll.outputs.confidential

        if cf_type is output.ConfidentialOutput:
            confidential = 'will be written into git as any other file'
        elif cf_type is output.ConfidentialOutputHidden:
            confidential = 'will be written with confidential data censored into git'
        elif cf_type is output.ConfidentialOutputGitIgnore or cf_type is output.ConfidentialOutputSingleGitIgnore:
            confidential = 'will be .gitignored'
            if cf_type is output.ConfidentialOutputGitIgnore:
                confidential += ' (with one .gitignore per directory containing confidential files)'
            else:
                confidential += ' (with one .gitignore in `{}/.gitignore`)'.format(r.outputs)
        elif cf_type is output.ConfidentialOutputGitCrypt or cf_type is output.ConfidentialOutputSingleGitCrypt:
            confidential = 'will be set-up for git-crypt in the .gitattributes file'
            if cf_type is output.ConfidentialOutputGitCrypt:
                confidential += ' (with one .gitattributes file per directory containing confidential files)'
            else:
                confidential += ' (with one .gitattributes file in `{}/.gitattributes`)'.format(r.outputs)

        formatter = {'clusterinfo': clusterinfo, 'reponame': os.path.split(r.basepath)[1],
                     'sources': r.sources, 'output': r.outputs, 'confidential': confidential,
                     'output_layout': output_layout, 'pythonpath': pythonpath}

        text = '\n'.join(map(lambda x: x.strip(), self.repotext.strip().splitlines())) + '\n'

        with open(os.path.join(r.basepath, 'README.md'), 'w') as f:
            f.write(text.format(**formatter))
