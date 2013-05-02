import sublime
import sublime_plugin
import os
import sys
import re
import codecs

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
        #first_ten = LibraryItem.getAllUserItems('1197522', 'FUWTcdnRvb1bFy8ugDudDDhA')
        bibTexEntries = BibTexEntry.readFromFile("/Users/jan/Desktop/test.bib")
        first_ten = [LibraryItem.createFromBibTexEntry(entry, 'FUWTcdnRvb1bFy8ugDudDDhA') for entry in bibTexEntries]
        selectFrom = []
        for item in first_ten:
            selectFrom.append([item.authors, item.title])
        #BibTexEntry.writeToFile([item.bibTexEntry for item in first_ten], "/Users/jan/Desktop/test.bib")
        self.view.window().show_quick_panel(selectFrom, self.callBack)
        self.view.insert(edit, 0, "Hello, World!")

    def callBack(self, arg):
        print arg


class LibraryItem(object):
    __zoteroInstances = {}

    def __init__(self, docId, zotInstance, authors, title, bibTexEntry=None):
        """Private Constructor.
        Don't use to create instances. Use getAllUserItems or getAllGroupItems instead"""
        self.id = docId
        self.zotInstance = zotInstance
        self.authors = authors
        self.title = title
        self.__bibTexEntry = bibTexEntry

    @staticmethod
    def __initFromZotero(zotInstance, libItemDict):
        """Private Constructor.
        Don't use to create instances. Use getAllUserItems or getAllGroupItems instead"""
        return LibraryItem(
            libItemDict[u'key'],
            zotInstance,
            LibraryItem.__decodeAuthors(libItemDict[u'creators']),
            libItemDict[u'title'],
            None)

    @staticmethod
    def __decodeAuthors(cratorsDict):
        retVal = u""
        seperator = u""
        for creator in cratorsDict:
            retVal += (u"%s%s, %s" % (seperator, creator[u'lastName'], creator[u'firstName'].split()[0]))
            seperator = u'; '
        return retVal

    def __str__(self):
        return self.__unicode__().encode("ascii", "replace")

    def __unicode__(self):
        return u"LibraryItem<%s in %s>(%s: \"%s\")" % (self.id, "%s(%s)" % self.zotInstance, self.authors, self.title)

    @property
    def bibTexEntry(self):
        if self.__bibTexEntry is None:
            self.__bibTexEntry = BibTexEntry(self.__zoteroInstances[self.zotInstance].item(self.id, content='bibtex')[0])
            self.__bibTexEntry.zoteroLink(self.id, self.zotInstance[0], self.zotInstance[1])
        return self.__bibTexEntry

    @classmethod
    def __addZoteroInstance(cls, libId, libType, key):
        libId = unicode(libId)
        libType = unicode(libType)
        key = unicode(key)
        zotInstance = (libId, libType)
        if zotInstance not in cls.__zoteroInstances.keys():
            cls.__zoteroInstances[zotInstance] = zotero.Zotero(libId, libType, key)
        return zotInstance

    @classmethod
    def getAllUserItems(cls, userId, key):
        zotInstance = cls.__addZoteroInstance(userId, "user", key)
        retVal = []
        for libItemDict in cls.__zoteroInstances[zotInstance].top():
            retVal.append(cls.__initFromZotero(zotInstance, libItemDict))
        for group in cls.__zoteroInstances[zotInstance].groups():
            retVal += LibraryItem.getAllGroupItems(group[u'group_id'], key)
        return retVal

    @classmethod
    def getAllGroupItems(cls, groupId, key):
        zotInstance = cls.__addZoteroInstance(groupId, "group", key)
        retVal = []
        for libItemDict in cls.__zoteroInstances[zotInstance].top():
            retVal.append(cls.__initFromZotero(zotInstance, libItemDict))
        for group in cls.__zoteroInstances[zotInstance].groups():
            retVal += LibraryItem.getAllGroupItems(group[u'group_id'], key)
        return retVal

    @classmethod
    def createFromBibTexEntry(cls, bibTexEntry, zoteroKey):
        try:
            zoteroInstance = cls.__addZoteroInstance(bibTexEntry.zoteroLibraryId, bibTexEntry.zoteroLibraryType, zoteroKey)
            itemDict = cls.__zoteroInstances[zoteroInstance].item(bibTexEntry.zoteroKey)[0]
        except IOError:
            return LibraryItem(
                None,
                None,
                bibTexEntry.entrys.get("author", "No Author(s)"),
                bibTexEntry.entrys.get("title", "No Title"),
                bibTexEntry)
        else:
            retInstance = cls.__initFromZotero(zoteroInstance, itemDict)
            if bibTexEntry.key is not retInstance.bibTexEntry.key:
                #BibTex-Key has changed: Do Somethin to change Keys in Document
                pass
            return retInstance


class BibTexEntry(object):
    __valueInCurlyBraces = re.compile("\\{(.*)\\}", re.S)

    def __init__(self, bibTexString):
        bibTexString = unicode(bibTexString)
        bibTexEntryMatch = re.search("@(\\S+?)\\s*\\{\\s*(\\S+?)\\s*,(.*)\\}", bibTexString, re.S)
        if bibTexEntryMatch:
            self.type = bibTexEntryMatch.group(1)
            self.key = bibTexEntryMatch.group(2)
            self.entrys = {}
            for match in re.finditer("(\\S+?)\\s*=\\s*(.*?),?\\n", bibTexEntryMatch.group(3)):
                self.entrys[match.group(1)] = match.group(2)
        else:
            raise ValueError("Passed string doesn't contain a valid BiBTex-Entry")

    @property
    def bibTexString(self):
        entrysString = ""
        for key in self.entrys.keys():
            entrysString += "\t%s = %s,\n" % (key, self.entrys[key])
        return u"@%s{%s,\n%s}" % (self.type, self.key, entrysString)

    @property
    def zoteroKey(self):
        return self.__valueInCurlyBraces.search(self.entrys.get("zoterodocid", None)).group(1)

    @property
    def zoteroLibraryId(self):
        return self.__valueInCurlyBraces.search(self.entrys.get("zoterolibid", None)).group(1)

    @property
    def zoteroLibraryType(self):
        return self.__valueInCurlyBraces.search(self.entrys.get("zoterolibtype", None)).group(1)

    def zoteroLink(self, key, libId, libType):
        self.entrys["zoterodocid"] = "{%s}" % key
        self.entrys["zoterolibid"] = "{%s}" % libId
        self.entrys["zoterolibtype"] = "{%s}" % libType

    @staticmethod
    def readFromFile(filePath):
        with codecs.open(filePath, "r", "utf-8") as f:
            bibTexString = f.read()
        startIndex = 0
        braceLevel = 0
        entry = False
        retVal = []
        for i in xrange(0, len(bibTexString)):
            if entry is True:
                if bibTexString[i] == u"{":
                    braceLevel += 1
                elif bibTexString[i] == u"}":
                    braceLevel -= 1
                    if braceLevel == 0:
                        entry = False
                        retVal.append(BibTexEntry(bibTexString[startIndex:i+1]))
            elif bibTexString[i] == u"@":
                entry = True
                startIndex = i
        return retVal

    @staticmethod
    def writeToFile(bibTexEntries, filePath):
        with codecs.open(filePath, "w", "utf-8") as f:
            f.writelines([entry.bibTexString + "\n" for entry in bibTexEntries])
