__author__ = "news.jan.vogt@me.com"
__version__ = "0.1"

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

    def __init__(self, view, zotLibId, zotLibKey, pathToBibFile=None, noUpdate=False):
        """Initializes a library based on a Zoteros user library and an optional BibTex-file"""
        self.__instances[view.buffer_id()] = self
        self.__pathToBibFile = pathToBibFile
        self.__zoteroInstances = {}
        self.__libItems = []
        self.__rootZoteroCredentials = (zotLibId, zotLibKey)
        self.__libLock = threading.RLock()
        self.__zoteroLock = threading.RLock()
        if not noUpdate:
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
        with self.__libLock:
            self.__pathToBibFile = value

    def update(self):
        """Collect all items from Zotero and if it exists unions them with those from
        the BibTex-file. In case of matches it assumes Zoteros' version to be the correct one"""
        newItems = []
        if self.pathToBibFile is not None:
            with self.__libLock:
                bibTexEntries = self.__readFromBibFile(self.pathToBibFile)
            newItems.extend(
                [LibraryItem(
                    entry.zoteroKey,
                    None,
                    entry.author,
                    entry.title,
                    entry.year,
                    entry.abstract,
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
        with self.__libLock:
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
    def getLibraryForView(cls, view, noInitialUpdate=False):
        try:
            return cls.__instances[view.buffer_id()]
        except KeyError:
            settings = sublime.load_settings("ZoteroCite.sublime-settings")
            filename = None
            if view.file_name() is not None:
                filename = os.path.splitext(view.file_name())[0] + '.bib'
            return Library(view, settings.get("zotero_user_id"), settings.get("zotero_user_key"), filename, noInitialUpdate)

    def removeLibraryForView(self, onlyIfEmpty=True):
        if onlyIfEmpty:
            for item in self.LibraryItems:
                if item.cited:
                    return
        for key in self.__instances.keys():
            if self.__instances[key] == self:
                del self.__instances[key]
                break

    @classmethod
    def hasLibraryForView(cls, view):
        try:
            cls.__instances[view.buffer_id()]
            return True
        except KeyError:
            return False

    @staticmethod
    def hasBibFile(pathToBibFile):
        try:
            with codecs.open(pathToBibFile, "r", "utf-8"):
                return True
        except IOError:
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
    def __init__(self, docId=None, zotInstance=None, authors=None, title=None, year=None, abstract=None, bibTexEntry=None):
        if docId is None and bibTexEntry is None:
            raise ValueError("LibraryItem needs at least either a docId or a bibTexEntry")
        self.id = docId
        self.zotInstance = zotInstance
        self.authors = authors
        self.title = title
        self.year = year
        self.abstract = abstract
        self.bibTexEntry = bibTexEntry

    @property
    def cited(self):
        return self.bibTexEntry is not None

    @property
    def menuRows(self):
        retVal = []
        searchableRow = "%s (%s): %s" % (self.authors, self.year, self.title)
        if len(searchableRow) > 100:
            retVal.append(searchableRow[0:97] + "...")
        else:
            retVal.append(searchableRow)
        if len(self.abstract) > 0:
            abstractRow = ""
            for word in self.abstract.split():
                if len(abstractRow) + len(word) > 125:
                    if len(retVal) < 6:
                        retVal.append(abstractRow)
                        abstractRow = word
                    else:
                        retVal.append(abstractRow[0:122] + "...")
                        abstractRow = None
                        break
                else:
                    abstractRow += " %s" % word
            if abstractRow is not None:
                retVal.append(abstractRow)
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
        return LibraryItem(
            libItemDict[u'key'],
            zotInstance,
            LibraryItem.__decodeAuthors(libItemDict[u'creators']),
            libItemDict.get(u'title', "No Title"),
            libItemDict.get(u'date', "????"),
            libItemDict.get(u'abstractNote', "")
        )

    @staticmethod
    def __decodeAuthors(cratorsDict):
        retVal = u""
        seperator = u""
        for creator in cratorsDict:
            retVal += (u"%s%s, %s" % (seperator, creator[u'lastName'], creator[u'firstName'].split()[0][0:1]))
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
        return self.__getEntry("zoterodocid", None)

    @property
    def zoteroLibraryId(self):
        return self.__getEntry("zoterolibid", None)

    @property
    def zoteroLibraryType(self):
        return self.__getEntry("zoterolibtype", None)

    @property
    def author(self):
        return self.__getEntry("author", "No Author(s)")

    @property
    def title(self):
        return self.__getEntry("title", "No Title")

    @property
    def year(self):
        return self.__getEntry("year", "????")

    @property
    def abstract(self):
        return self.__getEntry("abstract", "")

    def __getEntry(self, entry, default=""):
        try:
            return self.__valueInCurlyBraces.search(self.entrys.get(entry, "")).group(1)
        except AttributeError:
            return default

    def zoteroLink(self, key, libId, libType):
        self.entrys["zoterodocid"] = "{%s}" % key
        self.entrys["zoterolibid"] = "{%s}" % libId
        self.entrys["zoterolibtype"] = "{%s}" % libType
