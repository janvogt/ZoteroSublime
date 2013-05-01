import sublime
import sublime_plugin
import os
import sys
import re

if os.name == 'nt':
    from ctypes import windll, create_unicode_buffer

def add_to_path(path):
    # Python 2.x on Windows can't properly import from non-ASCII paths, so
    # this code added the DOC 8.3 version of the lib folder to the path in
    # case the user's username includes non-ASCII characters
    if os.name == 'nt':
        buf = create_unicode_buffer(512)
        if windll.kernel32.GetShortPathNameW(path, buf, len(buf)):
            path = buf.value

    if path not in sys.path:
        sys.path.append(path)

lib_folder = os.path.join(sublime.packages_path(), 'ZoteroCite', 'lib')
add_to_path(os.path.join(lib_folder, 'pyzotero'))
add_to_path(os.path.join(lib_folder, 'feedparser'))
add_to_path(os.path.join(lib_folder, 'pytz-2013b'))
add_to_path(os.path.join(lib_folder, 'poster-0.8.1'))
add_to_path(os.path.join(lib_folder, 'ordereddict-1.1'))


from pyzotero import zotero


class InsertCitationCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        first_ten = LibraryItem.getAllUserItems('1197522', 'FUWTcdnRvb1bFy8ugDudDDhA')
        i = 1
        for item in first_ten:
            print "Eintrag %d" % i
            i += 1
            print item
            print item.bibTexKey
            print item.bibTexEntry.encode("ascii", "ignore")
            #for key in item.keys():
            #    try:
            #        print u"\t%s = '%s'" % (key, item[key])
            #    except UnicodeEncodeError:
            #        print u"\t%s = '%s'" % (key, "Unicode Error")
        self.view.insert(edit, 0, "Hello, World!")


class LibraryItem(object):
    __zoteroInstances = {}

    def __init__(self, zotInstance, libItemDict):
        """Private Constructor.
        Don't use to create instances. Use getAllUserItems or getAllGroupItems instead"""
        self.id = libItemDict[u'key']
        self.zotInstance = zotInstance
        self.authors = self.__decodeAuthors(libItemDict[u'creators'])
        self.title = libItemDict[u'title']
        self.__bibTexEntry = None
        self.__bibTexKey = None

    def __decodeAuthors(self, cratorsDict):
        retVal = u""
        seperator = u""
        for creator in cratorsDict:
            retVal += (u"%s%s, %s" % (seperator, creator[u'lastName'], creator[u'firstName'][0]))
            seperator = u'; '
        return retVal

    def __str__(self):
        return self.__unicode__().encode("ascii", "replace")

    def __unicode__(self):
        return u"LibraryItem<%s in %s>(%s: \"%s\")" % (self.id, "%s(%s)" % self.zotInstance, self.authors, self.title)

    @property
    def bibTexEntry(self):
        if self.__bibTexEntry is None:
            self.__bibTexEntry = self.__zoteroInstances[self.zotInstance].item(self.id, content='bibtex')[0]
            keyMatch = re.search("@\\w+?\\{(.*?),", self.__bibTexEntry)
            if keyMatch:
                self.__bibTexKey = keyMatch.group(1)
            else:
                raise RuntimeError("Although a bibTex-entry has been recieved, the key could not be extracted!")
        return self.__bibTexEntry

    @property
    def bibTexKey(self):
        if self.__bibTexKey is None:
            self.bibTexEntry
        return self.__bibTexKey

    @classmethod
    def getAllUserItems(cls, userId, key):
        userId = unicode(userId)
        key = unicode(key)
        zotInstance = (userId, "user")
        if zotInstance not in cls.__zoteroInstances.keys():
            cls.__zoteroInstances[zotInstance] = zotero.Zotero(userId, "user", key)
        retVal = []
        for libItemDict in cls.__zoteroInstances[zotInstance].top():
            retVal.append(LibraryItem(zotInstance, libItemDict))
        for group in cls.__zoteroInstances[zotInstance].groups():
            retVal += LibraryItem.getAllGroupItems(group[u'group_id'], key)
        return retVal

    @classmethod
    def getAllGroupItems(cls, groupId, key):
        groupId = unicode(groupId)
        key = unicode(key)
        zotInstance = (groupId, "group")
        if zotInstance not in cls.__zoteroInstances.keys():
            cls.__zoteroInstances[zotInstance] = zotero.Zotero(groupId, "group", key)
        retVal = []
        for libItemDict in cls.__zoteroInstances[zotInstance].top():
            retVal.append(LibraryItem(zotInstance, libItemDict))
        for group in cls.__zoteroInstances[zotInstance].groups():
            retVal += LibraryItem.getAllGroupItems(group[u'group_id'], key)
        return retVal
