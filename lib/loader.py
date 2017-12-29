# (c) Copyright 2017 OLX

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os

DEV = True
VERBOSE = False
DEBUG = False

class LoaderBaseException(Exception):
    pass


class LoaderLoopException(LoaderBaseException):
    pass


class LoaderNotInSourcesException(LoaderBaseException):
    pass


class LoaderArgumentError(LoaderBaseException):
    pass


class LoaderFileNameError(LoaderBaseException):
    pass


class LoaderCompileException(LoaderBaseException):
    pass


class LoaderImportError(LoaderBaseException):
    pass


class Path(object):
    def __init__(self, path, repository):
        self.repository = repository
        self.rootdir = repository.basepath
        self.srcsdir = repository.sources

        self.full_path = os.path.realpath(path)
        self.src_rel_path = os.path.relpath(self.full_path, self.srcsdir)
        if not self.in_sources():
            raise LoaderNotInSourcesException('{} is not in sources directory {}'.format(
                                              self.full_path, self.srcsdir))

        self.full_dir = os.path.split(self.full_path)[0]
        self.src_rel_dir = os.path.split(self.src_rel_path)[0]

        self.filename = os.path.split(self.full_path)[1]
        if '.' in self.filename:
            self.basename, self.extension = self.filename.rsplit('.', 1)
        else:
            self.basename = self.filename
            self.extension = None

    def in_sources(self):
        return not self.src_rel_path.startswith('..')

    def dot_path(self):
        return '.'.join(self.src_rel_dir.split(os.path.sep)) + '.' + self.basename

    def rel_path(self, path):
        assert not path.startswith('/')
        return self.__class__(os.path.join(self.full_dir, path), self.repository)

    def replace_extension(self, new_ext):
        return self.__class__(os.path.join(self.full_dir, self.basename + '.' + new_ext), self.repository)

    def exists(self):
        return os.path.exists(self.full_path)

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.full_path == other.full_path

    def __repr__(self):
        return '<{}: {}>'.format(self.__class__.__name__, self.full_path)

    def __str__(self):
        return self.full_path


class Loader(object):
    def __init__(self, repository):
        self.files = {}
        self.deps = {}
        self.repository = repository

    def root(self):
        return self.repository.basepath

    def sources(self):
        return self.repository.sources

    def debug(self, level, text):
        if VERBOSE:
            if level in (0, 1):
                print(text, file=sys.stderr)
        if DEBUG:
            indent = ' ' * level
            print('{}-> {}'.format(indent, text), file=sys.stderr)

    def finish(self):
        self.debug(3, 'calling finish()')
        for f in self.files.values():
            if hasattr(f, 'finish'):
                f.finish()
        if hasattr(self, 'finishers'):
            for sf in self.finishers:
                if hasattr(self, sf) and getattr(self, sf) is not None and hasattr(getattr(self, sf), 'finish'):
                    getattr(self, sf).finish()

    def import_check(self, py_context, name, valid_exts=None):
        try:
            npath = py_context.path.rel_path(name)
        except AssertionError as e:
            raise LoaderImportError('path imports must be relative {} -> {}'.format(
                                    py_context.src_rel_path, name))
        if valid_exts is not None:
            if npath.extension not in valid_exts:
                raise LoaderImportError('expected file extension in ({}), got .{}'.format(
                                        ', '.join(valid_exts), npath.extension))

        if not npath.exists():
            raise LoaderImportError('file {} -> {} imported from {} does not exist'.format(
                                    npath.src_rel_path, npath.full_path, py_context.src_rel_path))

        return npath

    def import_symbols(self, name, i_path, b_path, basename, i_module, b_module, exports):
        self.debug(2, 'importing {} ({}) into {}: {}'.format(i_path, name, b_path, repr(exports)))
        try:
            if len(exports) == 0:
                # import <i_module>
                b_module.__dict__[basename] = i_module

            elif len(exports) == 1 and exports[0] == '*':
                # from <i_module> import *
                for sym in i_module.__dict__:
                    if sym == '__builtins__':
                        # this is magic, we don't try and be clever
                        continue
                    b_module.__dict__[sym] = i_module.__dict__[sym]

            else:
                # from <i_module> import <foo>, <bar>
                for sym in exports:
                    assert sym != '*'
                    if isinstance(sym, tuple) and len(sym) == 2:
                        # <foo> as <f>
                        b_module.__dict__[sym[1]] = i_module.__dict__[sym[0]]
                    else:
                        b_module.__dict__[sym] = i_module.__dict__[sym]

        except AssertionError as e:
            raise LoaderImportError("'*' is only allowed as the only export importing {] -> {} from {}".format(
                name, i_path.src_rel_path, b_path.src_rel_path))

        except KeyError as e:
            raise LoaderImportError('symbols not found importing {} -> {} from {}: {}'.format(
                name, i_path.src_rel_path, b_path.src_rel_path, e))

    def add_dep(self, s_path, d_path=None):
        if s_path.src_rel_path not in self.deps:
            self.deps[s_path.src_rel_path] = set()
        if d_path is not None:
            self.debug(2, '{} depends on {}'.format(s_path, d_path))
            self.deps[s_path.src_rel_path].add(d_path.src_rel_path)
            self.check_deps()

    def get_or_add_file(self, f_path, comp_context_obj, args):
        if f_path.full_path in self.files:
            return self.files[f_path.full_path]
        return self.add_file(f_path, comp_context_obj(*args))

    def add_file(self, f_path, comp_context):
        self.add_dep(f_path)
        assert f_path.full_path not in self.files
        self.files[f_path.full_path] = comp_context
        return comp_context

    def check_deps(self):
        checked = set()

        def _rec_check_deps(k, prev):
            if prev is None:
                prev = set()
            for nk in self.deps[k]:
                if nk in prev:
                    raise LoaderLoopException('Loop detected: {} imports {}'.format(nk, k))
                nprev = set((nk,))
                nprev.update(prev)
                _rec_check_deps(nk, nprev)
                checked.add(nk)

        for k in self.deps:
            if k not in checked:
                _rec_check_deps(k, None)
