# pagealigner.py

# Utility module for aligning page-level metadata predictions
# produced at the University of Illinois with HathiTrust data,
# in the form of pages concatenated in a .zip file, or
# (eventually) a file of extracted page-level features.

# This is version 1.0 of pagealigner,
# written in Python 3.3.5, in December 2014.

# It's designed to work with the first release of
# page-level metadata:
#   Ted Underwood. Page-level genre metadata for English-language
#   volumes in HathiTrust, 1700-1922.
#   http://dx.doi.org/10.6084/m9.figshare.1279201, December 2014.

# You can use the Alignment class in this module
# to create a generator that will
# align a whole list of volumes with genre predictions and then
# yield them back to you one by one. Because Alignment returns a
# generator, you can use it to iterate across a large set
# of volumes without any fear that you'll bust through
# memory limitations by loading them all at once.
#
# The generator returns a three-tuple (volumeid, successflag, volume).
# The successflag is there to tell you what went wrong, if something
# goes wrong. For instance it could say "missing data file" or
# "missing genre prediction" or "mismatched lengths."
#
# The volume is represented as a list of pages.
#
# Each page, in turn, is a twotuple, where the first element
# in the tuple is the page text (in whatever format the datafile holds)
# and the second is a genre code.
#
# USAGE:
# If your genre predictions are in a subfolder (relative to
# your main script) called /genrepredictions, and your
# data files are HathiTrust zip files in a subfolder called
# /data, this is super simple:
#
# from pagealigner import Alignment
# alignedvols = Alignment(listofvolstoget)
# for volid, successflag, volume in alignedvols:
#     if successflag != "success":
#         print(successflag + " in " + volid)
#         continue
#     for page in volume:
#         text = page[0]
#         genre = page[1]
#         if genre == genreyouwant:
#             do stuff with text
#
# If your genre predictions and data files are in other
# folders, or if your data is in a different format, you'll
# need to specify more parameters when you create
# alignedvols. See the class definition of Alignment, below.
#

from zipfile import ZipFile
from collections import namedtuple
import tarfile, json, os, glob, sys

def read_zip(filepath):
    ''' Given a path to a HathiTrust zip file, this returns
    a list of pages, each of which is a list of lines, plus
    a successflag that can be used to interpret error
    conditions. Anything other than
         successflag == 'success' is an error condition.
    '''
    pagelist = list()
    try:
        with ZipFile(file = filepath, mode='r') as zf:
            for member in zf.infolist():
                pathparts = member.filename.split("/")
                suffix = pathparts[1]
                if "_" in suffix:
                    segments = suffix.split("_")
                    page = segments[-1][0:-4]
                else:
                    page = suffix[0:-4]

                if len(page) > 0 and page[0].isdigit():
                    numericpage = True
                else:
                    numericpage = False

                if not member.filename.endswith('/') and not member.filename.endswith("_Store") and not member.filename.startswith("_") and numericpage:
                    datafile = zf.open(member, mode='r')
                    linelist = [x.decode(encoding="UTF-8") for x in datafile.readlines()]
                    pagelist.append((page, linelist))

        pagelist.sort()
        pagecount = len(pagelist)
        if pagecount > 0:
            successflag = "success"
            pagelist = [x[1] for x in pagelist]
        else:
            successflag = "missing data file"

    except IOError as e:
        successflag = "missing data file"
    except UnicodeError as e:
        successflag = "unicode error"

    return pagelist, successflag

def make_mapping(idstoget):
    ''' Creates a dictionary that maps multiple versions of a volume ID
    onto the provided original volume ID.
    '''

    iddictionary = dict()
    allids = set()
    for anid in idstoget:
        iddictionary[anid] = anid

        alternateid = anid.replace(',','.')
        iddictionary[alternateid] = anid
        allids.add(alternateid)

        alternateid = alternateid.replace('+', ':')
        alternateid = alternateid.replace('=', '/')
        iddictionary[alternateid] = anid
        allids.add(alternateid)

    return iddictionary, allids

def get_genre_index(tarpaths, volidstoget):
    '''Given a list of tarfiles and a list of volume ids to get,
    this function returns a dictionary that maps each id,
    if found, to its location in a specific tarfile. Volume IDs
    that are not found don't get added to the dictionary.

    "Location" here means a two-tuple where the first entry is
    the path to a tarfile and the second entry is the name of
    the item within the tarfile.
    '''

    pathdictionary = dict()

    # Because there are unfortunately multiple forms of ID in HathiTrust,
    # we need to tolerate a couple different ID formats. This is especially
    # necessary, frankly, because I screwed up and left some periods in
    # the miua namespace, where there should be commas ...

    # To tolerate multuple formats we'll create a mapping:

    iddictionary, allids = make_mapping(volidstoget)

    for tarpath in tarpaths:

        with tarfile.open(tarpath, 'r:gz') as tar:

            for tarinfo in tar:

                name = tarinfo.name
                pieces = name.split('/')
                thisid = pieces[-1]
                if tarinfo.isreg() and thisid.endswith('.json'):
                    thisid = thisid.replace('.json', '')
                else:
                    continue
                    # This tarinfo object is a directory, or a file like
                    # '.DS_Store,' rather than a valid JSON file.

                if thisid in allids:
                    originalid = iddictionary[thisid]
                    pathdictionary[originalid] = (tarpath, tarinfo.name)
                    # This allows us to accept a variety of ID formats
                    # in the original list, but map them all to the
                    # IDs actually used to create filenames in the
                    # tar.gz file provided

    return pathdictionary

def get_data_index(datafolder, datalocations, volidstoget):
    '''This function returns a dictionary that maps each id,
    if found, to its location in the provided datafolder.
    '''

    pathdictionary = dict()

    for thisid in volidstoget:
        expectedpath = os.path.join(datafolder, thisid + '.zip')
        if expectedpath in datalocations:
            pathdictionary[thisid] = expectedpath

    return pathdictionary

def get_genrefolder_index(folder, locations, volidstoget, suffix):
    '''This function returns a dictionary that maps each id,
    if found, to its location in the provided genrefolder.
    '''

    pathdictionary = dict()

    for thisid in volidstoget:
        expectedpath = os.path.join(folder, thisid + suffix)
        if expectedpath in locations:
            pathdictionary[thisid] = expectedpath
        else:
            alternateid = thisid.replace(',','.')
            alternateid = alternateid.replace('+', ':')
            alternateid = alternateid.replace('=', '/')
            expectedpath = os.path.join(folder, alternateid + suffix)
            if expectedpath in locations:
                pathdictionary[thisid] = expectedpath

    return pathdictionary

def read_tarfile(tarpath, filename):
    tarfound = True

    try:
        with tarfile.open(tarpath, 'r:gz') as tar:
            tardata = tar.extractfile(filename)
            somebytes = tardata.read()
            jsonstring = somebytes.decode('utf-8', 'strict')
            jobj = json.loads(jsonstring)
    except:
        tarfound = False
        jobj = dict()

    return tarfound, jobj

def read_ordinary_json(filepath):
    with open(filepath, encoding = 'utf-8') as f:
        jsonstring = f.read()

    genrefound = True

    try:
        jobj = json.loads(jsonstring)
    except:
        genrefound = False
        jobj = dict()

    return genrefound, jobj


def get_volume(tarpath, filename, datatype, datapath):
    ''' This function actually does the aligning of data pages
    with genre predictions.
    '''

    if datatype == 'ziptext':
        pagelist, successflag = read_zip(datapath)
    else:
        pagelist, successflag = [], 'missing file type'

    if successflag != 'success':
        return successflag, []

    if len(tarpath) > 1:
        genrefound, jobj = read_tarfile(tarpath, filename)
    else:
        genrefound, jobj = read_ordinary_json(filename)

    if genrefound:
        pagegenres = jobj['page_genres']
        if len(pagelist) == len(pagegenres):
            volume = list()
            numpages = len(pagelist)
            for i in range(numpages):
                page = (pagelist[i], pagegenres[str(i)])
                volume.append(page)
                # Would be more pythonic to use zip here, I guess.

            return 'success', volume
        else:
            return 'mismatched lengths', []

    else:
        return 'missing genre prediction', []


def gather_recursively(topfolder, suffix, idstoget):
    ''' This walks all the subdirectories of a top-level folder,
    looking for files that end with suffix, and that also belong
    to the list idstoget. When it finds them, it adds them to a
    dictionary that maps the volume ID to a complete filepath.

    One complication is that HathiTrust volume IDs can be provided
    in 'clean' or 'dirty' formats. We want to tolerate both. To do that
    we create a mapping that translates several versions of each ID
    to the version originally provided in idstoget.

    If the list of idstoget is empty, this function returns all files
    in the recursive walk.
    '''

    pathdictionary = dict()

    # To tolerate multuple formats we'll create a mapping:

    iddictionary, allids = make_mapping(idstoget)
    if len(idstoget) < 1:
        geteverything = True
    else:
        geteverything = False

    for directory, subdirectories, files in os.walk(topfolder):
        for afile in files:
            if afile.endswith(suffix):
                strippedid = afile.replace(suffix, '')
                if strippedid in allids or geteverything:
                    originalid = iddictionary[strippedid]
                    pathdictionary[originalid] = os.path.join(directory, afile)

    return pathdictionary

def gather_idlist(topfolder, suffix):
    ''' This walks all the subdirectories of a top-level folder,
    looking for files that end with suffix; it ads them as ids.
    '''

    idlist = list()

    for directory, subdirectories, files in os.walk(topfolder):
        for afile in files:
            if afile.endswith(suffix):
                strippedid = afile.replace(suffix, '')
                idlist.append(strippedid)

    return idlist

class Alignment:

    # By default this looks for genre prediction files in a local subfolder called /genrepredictions,
    # and data files (of whatever type) in a local subfolder called /data. You can override those
    # defaults, but if you do, you need to provide complete paths.
    #
    # By default this assumes the tar.gz files containing predictions have been decompressed. They
    # don't all have to be located in a single folder; you can have multiple prediction folders under
    # one parent.

    def __init__(self, idstoget, genrepath = 'genrepredictions', datapath = 'data', datatype = 'ziptext', tarscompressed = False):
        self.idstoget = idstoget
        self.datatype = datatype
        self.rootdir = os.path.dirname(sys.argv[0])
        self.tarscompressed = tarscompressed

        if genrepath == 'genrepredictions':
            self._genrefolder = os.path.join(self.rootdir, 'genrepredictions')
        else:
            self._genrefolder = genrepath

        if datapath == 'data':
            self._datafolder = os.path.join(self.rootdir, 'data')
        else:
            self._datafolder = datapath

        if self.tarscompressed:
            tarfiles = glob.glob(os.path.join(self._genrefolder, '*.tar.gz'))
            self.genrelocations = get_genre_index(tarfiles, idstoget)
        else:
            self.genrelocations = gather_recursively(self._genrefolder, '.json', self.idstoget)

        if self.datatype == 'ziptext':
            self._datafiles = glob.glob(os.path.join(self._datafolder, '*.zip'))
        else:
            print('Fatal: data types other than ziptext are not yet implemented.')
            sys.exit(0)

        self.datalocations = get_data_index(self._datafolder, self._datafiles, idstoget)

    def __iter__(self):

        for volid in self.idstoget:
            if volid in self.genrelocations and volid in self.datalocations:

                if self.tarscompressed:
                    tarpath, filename = self.genrelocations[volid]
                else:
                    filename = self.genrelocations[volid]
                    tarpath = ""

                datapath = self.datalocations[volid]
                successflag, volume = get_volume(tarpath, filename, self.datatype, datapath)

            elif volid in self.genrelocations:
                successflag, volume = 'missing data', []
            else:
                successflag, volume = 'genre prediction not found', []

            yield volid, successflag, volume


if __name__ == '__main__':
    # This is really just for purposes of testing. This is not designed to be
    # used as a main script; the idea is that you'll import Alignment in your
    # own script and use it as a generator to iterate across volumes, where
    # each volume contains pages zipped to genres.

    datafolder = input("Path to directory holding your data files? ")
    # This can actually be the root directory of a pairtree structure, if you want to
    # get all the data files.
    idstoget = gather_idlist(datafolder, '.zip')

    genrefolder = input("Path to directory holding uncompressed genre predictions? ")
    alignedvols = Alignment(idstoget, genrepath = genrefolder, datapath = datafolder, tarscompressed = False)

    for volid, flag, volume in alignedvols:
        print(volid + " " + flag)
        print(len(volume))





