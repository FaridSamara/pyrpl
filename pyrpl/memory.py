###############################################################################
#    pyrpl - DSP servo controller for quantum optics with the RedPitaya
#    Copyright (C) 2014-2016  Leonhard Neuhaus  (neuhaus@spectro.jussieu.fr)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
###############################################################################

import os
from collections import OrderedDict
from shutil import copyfile
import numpy as np
import time
from PyQt4 import QtCore
from . import default_config_dir, user_config_dir
from io import StringIO
from .pyrpl_utils import time

import logging
logger = logging.getLogger(name=__name__)

# the config file is read through a yaml interface. The preferred one is
# ruamel.yaml, since it allows to preserve comments and whitespace in the
# config file through roundtrips (the config file is rewritten every time a
# parameter is changed). If ruamel.yaml is not installed, the program will
# issue a warning and use pyyaml (=yaml= instead). Comments are lost in this
#  case.
try:
    import ruamel.yaml
    #ruamel.yaml.add_implicit_resolver()
    ruamel.yaml.RoundTripDumper.add_representer(np.float64,
                lambda dumper, data: dumper.represent_float(float(data)))
    ruamel.yaml.RoundTripDumper.add_representer(complex,
                lambda dumper, data: dumper.represent_str(str(data)))
    ruamel.yaml.RoundTripDumper.add_representer(np.complex128,
                lambda dumper, data: dumper.represent_str(str(data)))
    ruamel.yaml.RoundTripDumper.add_representer(np.ndarray,
                lambda dumper, data: dumper.represent_list(list(data)))

    #http://stackoverflow.com/questions/13518819/avoid-references-in-pyyaml
    #ruamel.yaml.RoundTripDumper.ignore_aliases = lambda *args: True
    def load(f):
        return ruamel.yaml.load(f, ruamel.yaml.RoundTripLoader)
    def save(data, stream=None):
        return ruamel.yaml.dump(data, stream=stream,
                                Dumper=ruamel.yaml.RoundTripDumper,
                                default_flow_style=False)
    def isbranch(obj):
        return isinstance(obj, dict) #type is ruamel.yaml.comments.CommentedMap
except:
    logger.warning("ruamel.yaml could not be imported. Using yaml instead. Comments in config files will be lost.")
    import yaml

    # see http://stackoverflow.com/questions/13518819/avoid-references-in-pyyaml
    #yaml.Dumper.ignore_aliases = lambda *args: True # NEVER TESTED

    # ordered load and dump for yaml files. From
    # http://stackoverflow.com/questions/5121931/in-python-how-can-you-load-yaml-mappings-as-ordereddicts
    def load(stream, Loader=yaml.SafeLoader, object_pairs_hook=OrderedDict):
        class OrderedLoader(Loader):
            pass
        def construct_mapping(loader, node):
            loader.flatten_mapping(node)
            return object_pairs_hook(loader.construct_pairs(node))
        OrderedLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            construct_mapping)
        return yaml.load(stream, OrderedLoader)
    def save(data, stream=None, Dumper=yaml.SafeDumper, default_flow_style=False, **kwds):
        class OrderedDumper(Dumper):
            pass
        def _dict_representer(dumper, data):
            return dumper.represent_mapping(
                yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                data.items())
        OrderedDumper.add_representer(OrderedDict, _dict_representer)
        OrderedDumper.add_representer(np.float64,
                    lambda dumper, data: dumper.represent_float(float(data)))
        OrderedDumper.add_representer(complex,
                    lambda dumper, data: dumper.represent_str(str(data)))
        OrderedDumper.add_representer(np.complex128,
                    lambda dumper, data: dumper.represent_str(str(data)))
        OrderedDumper.add_representer(np.ndarray,
                    lambda dumper, data: dumper.represent_list(list(data)))
        return yaml.dump(data, stream, OrderedDumper,
                         default_flow_style=default_flow_style, **kwds)
    def isbranch(obj):
        return isinstance(obj, dict)
        # return type(obj) == OrderedDict

    # usage example:
    # load(stream, yaml.SafeLoader)
    # save(data, stream=f, Dumper=yaml.SafeDumper)


# two functions to locate config files
def _get_filename(filename=None):
    """ finds the correct path and name of a config file """
    # accidentally, we may pass a MemoryTree object instead of file
    if isinstance(filename, MemoryTree):
        return filename._filename
    # get extension right
    if not filename.endswith(".yml"):
        filename = filename + ".yml"
    # see if filename is found with given path, or in user_config or in default_config
    p, f = os.path.split(filename)
    for path in [p, user_config_dir, default_config_dir]:
        file = os.path.join(path, f)
        if os.path.isfile(file):
            return file
    # file not existing, place it in user_config_dir
    return os.path.join(user_config_dir, f)


def get_config_file(filename=None, source=None):
    """ returns the path to a valid, existing config file with possible source specification """
    # if None is specified, that means we do not want a persistent config file
    if filename is None:
        return filename
    # try to locate the file
    filename = _get_filename(filename)
    if os.path.isfile(filename):  # found a file
        p, f = os.path.split(filename)
        if p == default_config_dir:
            # check whether path is default_config_dir and make a copy in
            # user_config_dir in order to not alter original files
            dest = os.path.join(user_config_dir, f)
            copyfile(filename, dest)
            return dest
        else:
            return filename
    # file not existing, try to get it from source
    if source is not None:
        source = _get_filename(source)
        if os.path.isfile(source):  # success - copy the source
            logger.debug("File " + filename + " not found. New file created from source '%s'. "%source)
            copyfile(source,filename)
            return filename
    # still not returned -> create empty file
    with open(filename, mode="w"):
        pass
    logger.debug("File " + filename + " not found. New file created. ")
    return filename


class MemoryBranch(object):
    """Represents a branch of a memoryTree

    All methods are preceded by an underscore to guarantee that tab
    expansion of a memory branch only displays the available subbranches or
    leaves. A memory tree is a hierarchical structure. Nested dicts are
    interpreted as subbranches.

    Parameters
    ----------
    parent: MemoryBranch
        parent is the parent MemoryBranch
    branch: str
        branch is a string with the name of the branch to create
    defaults: list
        list of default branches that are used if requested data is not
        found in the current branch

    Class members
    -----------
    all properties without preceeding underscore are config file entries

    _data:      the raw data underlying the branch. Type depends on the
                loader and can be dict, OrderedDict or CommentedMap
    _dict:      similar to _data, but the dict contains all default
                branches
    _defaults:  list of MemoryBranch objects in order of decreasing
                priority that are used as defaults for the Branch.
                Changing the default values from the software will replace
                the default values in the current MemoryBranch but not
                alter the underlying default branch. Changing the
                default branch when it is not overridden by the current
                MemoryBranch results in an effective change in the branch.
    _keys:      same as _dict._keys()
    _update:    updates the branch with another dict
    _pop:       removes a value/subbranch from the branch
    _root:      the MemoryTree object (root) of the tree
    _parent:    the parent of the branch
    _branch:    the name of the branch
    _new_branch: creates new branch. Same as br
    _fullbranchname: returns the full path from root to the branch
    _getbranch: returns a branch by specifying its path, e.g. 'b1.c2.d3'
    _rename:    renames the branch
    _reload:    attempts to reload the data from disc
    _save:      attempts to save the data to disc

    """

    def __init__(self, parent, branch, defaults=list([])):
        self._branch = branch
        self._parent = parent
        self._defaults = defaults  # this call also updates __dict__

    @property
    def _defaults(self):
        """ defaults allows to define a list of default branches to fall back
        upon if the desired key is not found in the current branch """
        return self.__defaults

    @_defaults.setter
    def _defaults(self, value):
        if isinstance(value, list):
            self.__defaults = list(value)
        else:
            self.__defaults = [value]
        # update __dict__ with inherited values from new defaults
        dict = self._dict
        for k in self.__dict__.keys():
            if k not in dict and not k.startswith('_'):
                self.__dict__.pop(k)
        for k in dict.keys():
            # write None since this is only a
            # placeholder (__getattribute__ is overwritten below)
            self.__dict__[k] = None

    @property
    def _data(self):
        """ The raw data (OrderedDict) or Mapping of the branch """
        return self._parent._data[self._branch]

    @property
    def _dict(self):
        """ return a dict containing the memory branch data"""
        d = OrderedDict()
        for defaultdict in reversed(self._defaults):
            d.update(defaultdict._dict)
        d.update(self._data)
        return d

    def _keys(self):
        return self._dict.keys()

    def _update(self, new_dict):
        self._data.update(new_dict)
        # keep auto_completion up to date
        for k in new_dict:
            self.__dict__[k] = None
        self._save()
        # keep auto_completion up to date
        for k in new_dict:
            self.__dict__[k] = None

    def __getattribute__(self, name):
        """ implements the dot notation.
        Example: self.subbranch.leaf returns the item 'leaf' of 'subbranch' """
        if name.startswith('_'):
            return super(MemoryBranch, self).__getattribute__(name)
        else:
            # convert dot notation into dict notation
            attribute = self[name]
            # if subbranch, return MemoryBranch object
            if isbranch(attribute):
                return MemoryBranch(self, name)
            # otherwise return whatever we find in the data dict
            else:
                return attribute

    # getitem bypasses the higher-level __getattribute__ function and provides
    # direct low-level access to the underlying dictionary.
    # This is much faster, as long as no changes have been made to the config
    # file.
    def __getitem__(self, item):
        self._reload()
        try:
            return self._data[item]
        except KeyError:
            # if not in data, iterate over default branches
            for defaultbranch in self._defaults:
                try:
                    return defaultbranch._data[item]
                except KeyError:
                    pass
            raise

    def __setattr__(self, name, value):
        #logger.debug("SETATTR %s %s",  name, value)
        if name.startswith('_'):
            super(MemoryBranch, self).__setattr__(name, value)
        else:
            self._data[name] = value
            self._save()

    # creates a new entry, overriding the protection provided by dot notation
    # if the value of this entry is of type dict, it becomes a MemoryBranch
    # new values can be added to the branch in the same manner
    def __setitem__(self, item, value):
        if item in self._data:
            self.__setattr__(item, value)
        else:
            if isbranch(value):
                self._data[item] = dict(value)
            else:
                self._data[item] = value
            #logger.debug("SETITEM %s %s", item, value)
            self._save()
            # update the __dict__ for autocompletion
            self.__dict__[item] = None

    def _pop(self, name):
        """remove an item from the branch"""
        value = self._data.pop(name)
        if name in self.__dict__.keys():
            self.__dict__.pop(name)
        self._save()
        return value

    def _rename(self, name):
        self._parent[name] = self._parent._pop(self._branch)
        self._save()

    def _erase(self):
        """
        Erases the current branch
        :return:
        """
        self._parent._pop(self._branch)
        self._save()

    @property
    def _root(self):
        """ returns the parent highest in hierarchy (the MemoryTree object)"""
        parent = self
        while parent != parent._parent:
            parent = parent._parent
        return parent

    @property
    def _fullbranchname(self):
        parent = self._parent
        branchname = self._branch
        while parent != parent._parent:
            branchname = parent._branch + '.' + branchname
            parent = parent._parent
        return branchname

    def _getbranch(self, branchname, defaults=list([])):
        """ returns a Memory branch from the same MemoryTree with
        branchname.
        Example: branchname = 'level1.level2.mybranch' """
        branch = self._root
        for subbranch in branchname.split('.'):
            branch = branch.__getattribute__(subbranch)
        branch._defaults = defaults
        return branch

    def _reload(self):
        """ reload data from file"""
        self._parent._reload()

    def _save(self):
        """ write data to file"""
        self._parent._save()

    def _get_yml(self):
        """
        :return: returns the yml code for this branch
        """
        data = StringIO()
        save(self._data, data)
        return data.getvalue()

    def _set_yml(self, yml_content):
        """
        :param yml_content: sets the branch to yml_content
        :return: None
        """
        branch = load(yml_content)
        self._parent._data[self._branch] = branch
        self._save()

    def __repr__(self):
        return "MemoryBranch(" + str(self._dict.keys()) + ")"


class MemoryTree(MemoryBranch):
    """
    The highest level of a MemoryBranch construct. All attributes of this
    object that do not start with '_' are other MemoryBranch objects or
    Leaves, i.e. key - value pairs.

    Parameters
    ----------
    filename: str
        The filename of the .yml file defining the MemoryTree structure.
    """
    ##### internal load logic:
    # 1. initially, call _load() to get the data from the file
    # 2. upon each inquiry of the config data, _reload() is called to
    # ensure data integrity
    # 3. _reload assumes a delay of _loadsavedeadtime between changing the
    # config file and Pyrpl requesting the new data. That means, _reload
    # will not attempt to touch the config file more often than every
    # _loadsavedeadtime. The last interaction time with the file system is
    # saved in the variable _lastreload. If this time is far enough in the
    # past, the modification time of the config file is compared to _mtime,
    # the internal memory of the last modifiation time by pyrpl. If the two
    # don't match, the file was altered outside the scope of pyrpl and _load
    # is called to reload it.

    ##### internal save logic:

    # never reload or save more frequently than _loadsavedeadtime because
    # this is the principal cause of slowing down the code (typ. 30-200 ms)
    # for immediate saving, call _save_now, for immediate loading _load_now
    _loadsavedeadtime = 3

    # the dict containing the entire tree data (nested dict)
    _data = OrderedDict()

    def __init__(self, filename=None, source=None):
        # first, make sure filename exists
        self._filename = get_config_file(filename, source)
        if filename is None:  # simulate a config file, only store data in memory
            self._filename = filename
        else:  # normal mode of operation with an actual configfile on the disc
            self._lastsave = time()
            # make a temporary file to ensure modification of config file is atomic (double-buffering like operation...)
            self._buffer_filename = self._filename+'.tmp'
            # create a timer to postpone to frequent savings
            self._savetimer = QtCore.QTimer()
            self._savetimer.setInterval(self._loadsavedeadtime*1000)
            self._savetimer.setSingleShot(True)
            self._savetimer.timeout.connect(self._save)
        self._load()
        self._save_counter = 0 # cntr for unittest and debug purposes
        # root of the tree is also a MemoryBranch with parent self and
        # branch name ""
        super(MemoryTree, self).__init__(self, "")

    def _load(self):
        """ loads data from file """
        if self._filename is None:
            # if no file is used, just ignore this call
            return
        logger.debug("Loading config file %s", self._filename)
        # read file from disc
        with open(self._filename) as f:
            self._data = load(f)
        # store the modification time of this file version
        self._mtime = os.path.getmtime(self._filename)
        # make sure that reload timeout starts from this moment
        self._lastreload = time()
        # empty file gives _data=None
        if self._data is None:
            self._data = OrderedDict()
        # update dict of the MemoryTree object
        to_remove = []
        # remove all obsolete entries
        for name in self.__dict__:
            if not name.startswith('_') and name not in self._data:
                to_remove.append(name)
        for name in to_remove:
            self.__dict__.pop(name)
        # insert the branches into the object __dict__ for auto-completion
        self.__dict__.update(self._data)

    def _reload(self):
        """" reloads data from file if file has changed recently """
        # first check if a reload was not performed recently (speed up reasons)
        if self._filename is None:
            return
        # check whether reload timeout has expired
        if time() > self._lastreload + self._loadsavedeadtime:
            # prepare next timeout
            self._lastreload = time()
            logger.debug("Checking change time of config file...")
            if self._mtime != os.path.getmtime(self._filename):
                logger.debug("Loading because mtime %s != filetime %s",
                             self._mtime)
                self._load()
            else:
                logger.debug("... no reloading required")

    def _save(self, deadtime=None):
        logger.debug("SAVE")
        return

    def _save(self, deadtime=None):
        self._save_counter+=1  # for unittest and debug purposes
        if deadtime is None:
            deadtime = self._loadsavedeadtime
        """ writes current tree structure and data to file """
        if self._filename is None:
            return
        if self._lastsave + deadtime < time():
            self._lastsave = time()
            if self._mtime != os.path.getmtime(self._filename):
                logger.warning("Config file has recently been changed on your " +
                               "harddisk. These changes might have been " +
                               "overwritten now.")
            logger.debug("Saving config file %s", self._filename)
            copyfile(self._filename, self._filename+".bak")  # maybe this line is obsolete (see below)
            try:
                f = open(self._buffer_filename, mode='w')
                save(self._data, stream=f)
                f.flush()
                os.fsync(f.fileno())
                f.close()
                # config file writing should be atomic! I am not 100% sure the following line guarantees atomicity on windows
                # but it's already much better than letting the yaml dumper save on the final config file
                # see http://stackoverflow.com/questions/2333872/atomic-writing-to-file-with-python
                # or https://bugs.python.org/issue8828
                os.unlink(self._filename)
                os.rename(self._buffer_filename, self._filename)
            except:
                copyfile(self._filename+".bak", self._filename)
                logger.error("Error writing to file. Backup version was restored.")
                raise
            self._mtime = os.path.getmtime(self._filename)
        else:  # make sure saving will eventually occur
            if not self._savetimer.isActive():
                self._savetimer.start()

    # forces to save the config file immediately and kills the save timer
    def _save_now(self):
        # stop save timer
        if self._savetimer.isActive():
            self._savetimer.stop()
        # make sure save is done immediately by forcing negative deadtime
        self._save(deadtime=-1)
        # make sure no save timer was launched in the meantime
        if self._savetimer.isActive():
            self._savetimer.stop()

if False:
    class DummyMemoryTree(object):  # obsolete now
        """
        This class is there to emulate a MemoryTree, for users who would use RedPitaya object without Pyrpl object. The
        class is essentially deprecated by now.
        """
        @property
        def _keys(self):
            return self.keys

        def __getattribute__(self, item):
            try:
                attr = super(DummyMemoryTree, self).__getattribute__(item)
                return attr
            except AttributeError:
                return self[item]
