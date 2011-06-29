import os
import re

from debian import debfile
from debian import deb822

debian_version_chars = 'a-zA-Z\d.~+-'
version_re = re.compile(r'\bVersion:\s*((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*\n' % debian_version_chars)

def parseVersion( version ):
    ret = {}
    m = version_re.search( version )
    if m :
        if '-' in m.group('version'):
            ret['release'] = m.group('version').split("-")[-1]
            ret['version'] = "-".join(m.group('version').split("-")[0:-1])
            ret['native'] = False
        else:
            ret['native'] = True # Debian native package
            ret['version'] = m.group('version')
            ret['release'] = "debiannative"
        if m.group('epoch'):
            ret['epoch'] = m.group('epoch')
        else:
            ret['epoch'] = None
    return ret  
   

class PkgInfo(object):
    """Base class for Package Info"""
    def __init__(self, path):
        self.path = os.path.abspath(path)

    def getInfo(self):
        """(abstract) get the info from package file
           result: ret['type']
                   ret['sourceNVRA']
                   ret['sourcepackage']
                   ret['name']
                   ret['version']
                   ret['release']
                   ret['epoch']
                   ret['buildtime']
                   ret['size']
                   ret['files']
                       """
        raise NotImplementedError

class DscInfo(PkgInfo):
    compressions = r"(gz|bz2)"
    pkg_re = re.compile(r'\bSource:\s*(?P<pkg>.+)\s*\n')
    buildarchs_re = re.compile(r'\b:Architecture\s*(?P<buildarchs>.+)\s*\n')
    format_re = re.compile(r'\bFormat:\s*(?P<format>[0-9.]+)\s*\n')
    files_re = re.compile(r'\bFiles:\s*\n(?P<files>(([ ]+[^\n]+\n)+))')
    version_re = re.compile(r'\bVersion:\s*((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*\n' % debian_version_chars)

    def getInfo(self):
        ret={}
        ret['sourcepackage'] = 1
        ret['arch'] = 'src'
        ret['type'] = "dsc"
        ret['size'] = os.path.getsize(self.path)
        ret['buildtime'] = int(os.stat(self.path).st_ctime)
        ret['exclusivearch'] = None
        ret['excludearch'] = None

        f = file(self.path)
        content = f.read()
        fromdir = os.path.dirname(self.path)
        m = self.version_re.search(content)
        if m :
            if '-' in m.group('version'):
                ret['release'] = m.group('version').split("-")[-1]
                ret['version'] = "-".join(m.group('version').split("-")[0:-1])
                ret['native'] = False
            else:
                ret['native'] = True # Debian native package
                ret['version'] = m.group('version')
                ret['release'] = "debiannative"
            if m.group('epoch'):
                ret['epoch'] = m.group('epoch')
            else:
                ret['epoch'] = None
        m = self.pkg_re.search(content)
        if m:
            ret['name'] = m.group('pkg')
        m = self.buildarchs_re.search(content)
        if m:
            ret['buildarchs'] = m.group('buildarchs')
        m = self.format_re.search(content)
        if m:
            ret['pkgformat'] = m.group('format')
        ret['files']=[{"md5sum":"0","size":"0","path":self.path}]
        m = self.files_re.search(content)
        if m:
            #print "--------- %r" % m.group('files')
            for l in m.group('files').lstrip().rstrip().split("\n"):
                #print "--------- %r" % l
                if len(l) > 0 :
                    ss=l.lstrip().rstrip().split(" ")
                    fileinfo={}
                    fileinfo['md5sum'] = ss[0]
                    fileinfo['size'] = ss[1]
                    fileinfo['path'] = os.path.join(fromdir,ss[2])
                    ret['files'].append(fileinfo)

        f.close()
        return ret

class DebInfo(PkgInfo):
    version_re = re.compile(r'\bVersion:\s*((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*\n' % debian_version_chars)

    def getInfo(self):
        ret={}
        ret['sourcepackage'] = 0
        ret['type'] = "deb"
        ret['size'] = os.path.getsize(self.path)
        ret['buildtime'] = int(os.stat(self.path).st_ctime)
        
        deb = debfile.DebFile(self.path)
        info = deb.debcontrol()
        ret['name'] = info['Package']
        m = self.version_re.match(info ['Version'])
        if m :
            if '-' in m.group('version'):
                ret['release'] = m.group('version').split("-")[-1]
                ret['version'] = "-".join(m.group('version').split("-")[0:-1])
                ret['native'] = False
            else:
                ret['native'] = True # Debian native package
                ret['version'] = m.group('version')
                ret['release'] = "debiannative"
            if m.group('epoch'):
                ret['epoch'] = m.group('epoch')
            else:
                ret['epoch'] = None
        ret['arch'] = info ['Architecture']
        if info ['Source']:
            (self.spkgname,VR) = info ['Source'].split(" ")
            if VR:
                VR = VR.strip("(").strip(")")
                m = self.version_re.match(VR)
                if m :
                    if '-' in m.group('version'):
                        self.spkgrelease = m.group('version').split("-")[-1]
                        self.spkgversion = "-".join(m.group('version').split("-")[0:-1])
                    else:
                        self.spkgversion = m.group('version')
                        self.spkgrelease = "debiannative"
            else:
                self.spkgversion = ret['version']
                self.spkgrelease = ret['release']
        else:
            if ret['arch'] == "all":
                self.spkgname = ret['name']
        ret['sourceNVRA'] = self.spkgname + "-"
        ret['sourceNVRA'] +=  self.spkgversion + "-"
        ret['sourceNVRA'] +=  self.spkgrelease + "."
        ret['sourceNVRA'] +=  ret['arch']

        fileinfo={}
        fileinfo['size']="%d"%os.path.getsize(self.path)
        fileinfo['md5sum']="0"
        fileinfo['path']=self.path

        ret['files'] = [fileinfo]
        return ret



class DscFile(object):
    """Keeps all needed data read from a dscfile"""
    compressions = r"(gz|bz2)"
    pkg_re = re.compile(r'\bSource:\s*(?P<pkg>.+)\s*\n')
    version_re = re.compile(r'\bVersion:\s*((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*\n' % debian_version_chars)
    format_re = re.compile(r'\bFormat:\s*(?P<format>[0-9.]+)\s*\n')
    files_re = re.compile(r'\bFiles:\s*\n(?P<files>((\s+[^\n]+\n)+))')

    def __init__(self, dscfile):
        self.name = ""
        self.includefiles = []
        self.pkgformat = "1.0"
        self.release = ""
        self.version = ""
        #self.epoch = ""
        self.native = False
        self.dscfile = os.path.abspath(dscfile)

        f = file(self.dscfile)
        content = f.read()
        fromdir = os.path.dirname(os.path.abspath(dscfile))
        m = self.version_re.search(content)
        if m and not self.version:
            if '-' in m.group('version'):
                self.release = m.group('version').split("-")[-1]
                self.version = "-".join(m.group('version').split("-")[0:-1])
                self.native = False
            else:
                self.native = True # Debian native package
                self.version = m.group('version')
                self.release = "debiannative"
            if m.group('epoch'):
                self.epoch = m.group('epoch')
            else:
                self.epoch = None
        m = self.pkg_re.search(content)
        if m:
            self.name = m.group('pkg')
        m = self.format_re.search(content)
        if m:
            self.pkgformat = m.group('format')
        m = self.files_re.search(content)
        if m:
            for l in m.group('files').lstrip().rstrip().split("\n"):
                ss=l.lstrip().rstrip().split(" ")
                fileinfo={}
                fileinfo['md5sum'] = ss[0]
                fileinfo['size'] = ss[1]
                fileinfo['path'] = os.path.join(fromdir,ss[2])
                self.includefiles.append(fileinfo)
        f.close()


class DebFile(object):
    """Keeps all needed data read from a dscfile"""
    version_re = re.compile(r'((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*$' % debian_version_chars)

    def __init__(self, path):
        deb = debfile.DebFile(path)
        info = deb.debcontrol()
        self.name = info['Package']
        m = self.version_re.match(info ['Version'])
        if m :
            if '-' in m.group('version'):
                self.release = m.group('version').split("-")[-1]
                self.version = "-".join(m.group('version').split("-")[0:-1])
                self.native = False
            else:
                self.native = True # Debian native package
                self.version = m.group('version')
                self.release = "debiannative"
            if m.group('epoch'):
                self.epoch = m.group('epoch')
            else:
                self.epoch = None
        self.arch = info ['Architecture']
        if info ['Source']:
            (self.spkgname,VR) = info ['Source'].split(" ")
            if VR:
                VR = VR.strip("(").strip(")")
                m = self.version_re.match(VR)
                if m :
                    if '-' in m.group('version'):
                        self.spkgrelease = m.group('version').split("-")[-1]
                        self.spkgversion = "-".join(m.group('version').split("-")[0:-1])
                    else:
                        self.spkgversion = m.group('version')
                        self.spkgrelease = "debiannative"
            else:
                self.spkgversion = self.version
                self.spkgrelease = self.release
        else:
            if self.arch == "all":
                self.spkgname = self.name

def getDpkgStatus( fo ):
    return deb822.Packages.iter_paragraphs( fo )
