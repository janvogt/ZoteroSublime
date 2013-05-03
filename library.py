import sublime
import os
import sys
import re
import codecs
import threading

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


class Library(object):
    __instances = {}

    def __init__(self, view, zotLibId, zotLibKey, pathToBibFile=None):
        """Initializes a library based on a Zoteros user library and an optional BibTex-file"""
        self.__instances[view.buffer_id()] = self
        self.__pathToBibFile = pathToBibFile
        self.__zoteroInstances = {}
        self.__libItems = []
        self.__rootZoteroCredentials = (zotLibId, zotLibKey)
        self.__libLock = threading.RLock()
        self.__zoteroLock = threading.RLock()
        self.update()

    @property
    def LibraryItems(self):
        with self.__libLock:
            return list(self.__libItems)

    @property
    def pathToBibFile(self):
        return self.__pathToBibFile

    @pathToBibFile.setter
    def pathToBibFile(self, value):
        if self.__pathToBibFile is not None:
            raise NotImplementedError
        else:
            self.__pathToBibFile = value

    def update(self):
        """Collect all items from Zotero and if it exists unions them with those from
        the BibTex-file. In case of matches it assumes Zoteros' version to be the correct one"""
        newItems = []
        if self.pathToBibFile is not None:
            bibTexEntries = self.__readFromBibFile(self.pathToBibFile)
            newItems.extend(
                [LibraryItem(
                    entry.zoteroKey,
                    None,
                    entry.author,
                    entry.title,
                    entry
                ) for entry in bibTexEntries]
            )
        newItems.extend(self.__getAllUserItems(*self.__rootZoteroCredentials))
        with self.__libLock:
            for item in newItems:
                if item in self.__libItems:
                    index = self.__libItems.index(item)
                    if self.__libItems[index].cited:
                        if item.bibTexEntry is None:
                            item.bibTexEntry = self.__bibTexEntryForLibItem(item)
                        #The cited one has a bibTexEntry
                        if self.__libItems[index].bibTexEntry.key != item.bibTexEntry.key:
                            print "Warning: Citekey %s changed to %s" % (self.__libItems[index].bibTexEntry.key, item.bibTexEntry.key)
                            raise NotImplementedError
                            # Do sth. like replace the old keys
                    self.__libItems[index] = item
                else:
                    self.__libItems.append(item)

    def save(self):
        if self.pathToBibFile is not None:
            self.__writeToBibFile([item.bibTexEntry for item in self.LibraryItems if item.cited], self.pathToBibFile)
            return True
        else:
            return False

    def cite(self, libItem):
        if libItem.bibTexEntry is None:
            libItem.bibTexEntry = self.__bibTexEntryForLibItem(libItem)
        return libItem.bibTexEntry.key

    @classmethod
    def getLibraryForView(cls, view):
        try:
            return cls.__instances[view.buffer_id()]
        except KeyError:
            settings = sublime.load_settings("ZoteroCite.sublime-settings")
            filename = None
            if view.file_name() is not None:
                filename = os.path.splitext(view.file_name())[0] + '.bib'
            return Library(view, settings.get("zotero_user_id"), settings.get("zotero_user_key"), filename)

    @classmethod
    def hasLibraryForView(cls, view):
        try:
            cls.__instances[view.buffer_id()]
            return True
        except KeyError:
            return False

    def __bibTexEntryForLibItem(self, libItem):
        """creates an corresponding BibTexEntry for the given Library Item. If it is not possible to
        retrieve a new one None is returned"""
        with self.__zoteroLock:
            try:
                bibTexEntry = BibTexEntry(self.__zoteroInstances[libItem.zotInstance].item(libItem.id, content='bibtex')[0])
            except AttributeError:
                return libItem.bibTexEntry
            else:
                bibTexEntry.zoteroLink(libItem.id, libItem.zotInstance[0], libItem.zotInstance[1])
                return bibTexEntry

    def __addZoteroInstance(self, libId, libType, key=None):
        zotInstanceIdentifier = (libId, libType)
        if zotInstanceIdentifier not in self.__zoteroInstances.keys():
            self.__zoteroInstances[zotInstanceIdentifier] = zotero.Zotero(libId, libType, key)
        return zotInstanceIdentifier

    def __getAllUserItems(self, userId, key):
        zotInstanceIdentifier = self.__addZoteroInstance(userId, "user", key)
        retVal = []
        with self.__zoteroLock:
            libItems = self.__zoteroInstances[zotInstanceIdentifier].top()
        for libItemDict in libItems:
            retVal.append(LibraryItem.initFromZotero(zotInstanceIdentifier, libItemDict))
        with self.__zoteroLock:
            groups = self.__zoteroInstances[zotInstanceIdentifier].groups()
        for group in groups:
            retVal += self.__getAllGroupItems(group[u'group_id'], key)
        return retVal

    def __getAllGroupItems(self, groupId, key):
        zotInstanceIdentifier = self.__addZoteroInstance(groupId, "group", key)
        retVal = []
        with self.__zoteroLock:
            libItems = self.__zoteroInstances[zotInstanceIdentifier].top()
        for libItemDict in libItems:
            retVal.append(LibraryItem.initFromZotero(zotInstanceIdentifier, libItemDict))
        with self.__zoteroLock:
            groups = self.__zoteroInstances[zotInstanceIdentifier].groups()
        for group in groups:
            retVal += self.__getAllGroupItems(group[u'group_id'], key)
        return retVal

    @staticmethod
    def __readFromBibFile(filePath):
        retVal = []
        try:
            with codecs.open(filePath, "r", "utf-8") as f:
                bibTexString = f.read()
        except IOError:
            return retVal
        startIndex = 0
        braceLevel = 0
        entry = False
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
    def __writeToBibFile(bibTexEntries, filePath):
        with codecs.open(filePath, "w", "utf-8") as f:
            f.writelines([entry.bibTexString + "\n" for entry in bibTexEntries])


class LibraryItem(object):
    def __init__(self, docId, zotInstance, authors, title, bibTexEntry=None):
        self.id = docId
        self.zotInstance = zotInstance
        self.authors = authors
        self.title = title
        self.bibTexEntry = bibTexEntry

    @property
    def cited(self):
        return self.bibTexEntry is not None

    @property
    def menuRows(self):
        retVal = [self.authors, self.title]
        if self.id is None:
            retVal.append("Entry from local .bib-file")
        return retVal

    def __str__(self):
        return self.__unicode__().encode("ascii", "replace")

    def __unicode__(self):
        return u"LibraryItem<%s in %s>(%s: \"%s\")" % (self.id, "%s(%s)" % self.zotInstance, self.authors, self.title)

    def __eq__(self, other):
        if self.id is not None and other.id is not None:
            return self.id == other.id
        else:
            try:
                return self.bibTexEntry.key == other.bibTexEntry.key
            except AttributeError:
                return False

    def __ne__(self, other):
        return not self.__eq__(other)

    @staticmethod
    def initFromZotero(zotInstance, libItemDict):
        try:
            return LibraryItem(
                libItemDict[u'key'],
                zotInstance,
                LibraryItem.__decodeAuthors(libItemDict[u'creators']),
                libItemDict[u'title'])
        except TypeError as T:
            print "TypeError: %s" % type(libItemDict)
            print libItemDict
            raise T

    @staticmethod
    def __decodeAuthors(cratorsDict):
        retVal = u""
        seperator = u""
        for creator in cratorsDict:
            retVal += (u"%s%s, %s" % (seperator, creator[u'lastName'], creator[u'firstName'].split()[0]))
            seperator = u'; '
        return retVal


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
        try:
            return self.__valueInCurlyBraces.search(self.entrys.get("zoterodocid", "")).group(1)
        except AttributeError:
            return None

    @property
    def zoteroLibraryId(self):
        try:
            return self.__valueInCurlyBraces.search(self.entrys.get("zoterolibid", "")).group(1)
        except AttributeError:
            return None

    @property
    def zoteroLibraryType(self):
        try:
            return self.__valueInCurlyBraces.search(self.entrys.get("zoterolibtype", "")).group(1)
        except AttributeError:
            return None

    @property
    def author(self):
        try:
            return self.__valueInCurlyBraces.search(self.entrys.get("author", "")).group(1)
        except AttributeError:
            return "No Author(s)"

    @property
    def title(self):
        try:
            return self.__valueInCurlyBraces.search(self.entrys.get("title", "")).group(1)
        except AttributeError:
            return "No Title"

    def zoteroLink(self, key, libId, libType):
        self.entrys["zoterodocid"] = "{%s}" % key
        self.entrys["zoterolibid"] = "{%s}" % libId
        self.entrys["zoterolibtype"] = "{%s}" % libType
