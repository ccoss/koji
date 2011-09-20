import os
import re
import string
import logging
import hashlib

try:
    from debian import debfile
    from debian import deb822
except ImportError:
    try:
        from debian_bundle import debfile
        from debian_bundle import deb822
    except ImportError:
        sys.stderr.write("cant load debian module")
        sys.stderr.flush()
        sys.exit(1)

debian_version_chars = 'a-zA-Z\d.~+-'
version_re = re.compile(r'\bVersion:\s*((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*\n' % debian_version_chars)

logger = logging.getLogger('koji.hub')

def log_error(msg):
    #if hasattr(context,'req'):
    #    context.req.log_error(msg)
    #else:
    #    sys.stderr.write(msg + "\n")
    logger.error(msg)


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

def getField(  field, fields ):
    return field in fields
   
RPMSENSE_LESS = 2
RPMSENSE_GREATER = 4
RPMSENSE_EQUAL = 8

def flagToIntger( flag ):
    result = 0
    if flag:
        for f in flag:
            if f == '>':
                result |= RPMSENSE_GREATER
            if f == '<':
                result |= RPMSENSE_LESS
            if f == '=':
                result |= RPMSENSE_EQUAL
    return result

class PkgInfo(object):
    """Base class for Package Info"""

    def __init__(self, path):
        self.path = os.path.abspath(path)

    def getInfo(self,fields):
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

    def getInfo(self,fields):
        ret={}
        ret['sourcepackage'] = 1
        ret['arch'] = 'src'
        ret['type'] = "dsc"
        ret['size'] = os.path.getsize(self.path)
        ret['buildtime'] = int(os.stat(self.path).st_ctime)
        ret['exclusivearch'] = ''
        ret['excludearch'] = ''

        fd = file(self.path)
        content = fd.read()
        fromdir = os.path.dirname(self.path)

        if getField( 'version', fields ):
            version_re = re.compile(r'\bVersion:\s*((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*\n' % debian_version_chars)
            m = version_re.search(content)
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

        if getField( 'name', fields ):
            pkg_re = re.compile(r'\bSource:\s*(?P<pkg>.+)\s*\n')
            m = pkg_re.search(content)
            if m:
                ret['name'] = m.group('pkg')

        if getField( 'buildarchs', fields ):
            buildarchs_re = re.compile(r'\bArchitecture:\s*(?P<buildarchs>.+)\s*\n')
            m = buildarchs_re.search(content)
            if m:
                ret['buildarchs'] = m.group('buildarchs')

        if getField( 'pkgformat', fields ):
            format_re = re.compile(r'\bFormat:\s*(?P<format>[0-9.]+)\s*\n')
            m = format_re.search(content)
            if m:
                ret['pkgformat'] = m.group('format')

        if getField( 'files', fields ) or getField( 'filenames', fields ):
            files_re = re.compile(r'\bFiles:\s*\n(?P<files>(([ ]+[^\n]+\n)+))')
            md5 = hashlib.md5()
            md5.update(content)
            ret['files']=[{"md5sum":md5.hexdigest(),"size":ret['size'],"path":self.path}]
            m = files_re.search(content)
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
            if getField( 'filenames', fields ):
                ret['filenames'] = []
                ret['filemd5s'] = []
                ret['filesizes'] = []
                ret['fileflags'] = []
                ret['fileusername'] = []
                ret['filegroupname'] = []
                ret['filemtimes'] = []
                ret['filemodes'] = []
                for i in ret['files']:
                    ret['filenames'].append(os.path.basename(i['path']))
                    ret['filemd5s'].append(i['md5sum'])
                    ret['filesizes'].append(i['size'])
                    ret['fileflags'].append(0)
                    ret['fileusername'].append('')
                    ret['filegroupname'].append('')
                    ret['filemtimes'].append(0)
                    ret['filemodes'].append(0)

        ret['PROVIDENAME'] = []
        ret['PROVIDEFLAGS'] = []
        ret['PROVIDEVERSION'] = []

        ret['OBSOLETENAME'] = []
        ret['OBSOLETEFLAGS'] = []
        ret['OBSOLETEVERSION'] = []

        if getField( 'REQUIRENAME', fields ):
            ret['REQUIRENAME'] = []
            ret['REQUIREFLAGS'] = []
            ret['REQUIREVERSION'] = []
            builddep_re = re.compile(r'\bBuild-Depends:\s*(?P<builddep>.+)\s*\n')
            m = builddep_re.search( content )
            builddeps = ''
            if m:
                builddeps = m.group('builddep')

            buildindep_re = re.compile(r'\bBuild-Depends-Indep:\s*(?P<buildindep>.+)\s*\n')
            m = buildindep_re.search( content )
            buildindeps = None
            if m:
                buildindeps = m.group('buildindep')

            if buildindeps:
                builddeps += buildindeps
            deps = builddeps.split(', ')
            for d in deps:
                nfv = d.split(' (')
                ret['REQUIRENAME'].append( nfv[0])
                if len(nfv) > 1:
                    fv = nfv[1].strip('(').strip(')');
                    f = fv.split(' ')[0] 
                    v = fv.split(' ')[1] 
                    ret['REQUIREFLAGS'].append(flagToIntger(f))
                    ret['REQUIREVERSION'].append(v)
                else:
                    ret['REQUIREFLAGS'].append(flagToIntger(None))
                    ret['REQUIREVERSION'].append('')

        if getField( 'CONFLICTNAME', fields ):
            ret['CONFLICTNAME'] = []
            ret['CONFLICTFLAGS'] = []
            ret['CONFLICTVERSION'] = []
            buildconf_re = re.compile(r'\bBuild-Conflicts:\s*(?P<buildconf>.+)\s*\n')
            m = buildconf_re.search( content )
            buildconfs = ''
            if m:
                buildconfs = m.group('buildconf')

            buildinconf_re = re.compile(r'\bBuild-Conflicts-Indep:\s*(?P<buildinconf>.+)\s*\n')
            m = buildinconf_re.search( content )
            buildinconfs = None
            if m:
                buildinconfs = m.group('buildinconf')

            if buildinconfs:
                buildconfs += buildinconfs
            if len(buildconfs) > 0:
                confs = buildconfs.split(', ')
                for d in confs:
                    nfv = d.split(' (')
                    ret['CONFLICTNAME'].append( nfv[0])
                    if len(nfv) > 1:
                        fv = nfv[1].strip('(').strip(')');
                        f = fv.split(' ')[0] 
                        v = fv.split(' ')[1] 
                        ret['CONFLICTFLAGS'].append(flagToIntger(f))
                        ret['CONFLICTVERSION'].append(v)
                    else:
                        ret['CONFLICTFLAGS'].append(flagToIntger(None))
                        ret['CONFLICTVERSION'].append('')


        fd.close()

        ret['summary'] = ''
        ret['description'] = ''

        return ret

class DebInfo(PkgInfo):

    version_re = re.compile(r'((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*$' % debian_version_chars)

    def getInfo(self,fields):
        ret={}
        ret['sourcepackage'] = 0
        ret['type'] = "deb"
        ret['size'] = os.path.getsize(self.path)
        ret['buildtime'] = int(os.stat(self.path).st_ctime)
        
        deb = debfile.DebFile(self.path)
        info = deb.debcontrol()
        ret['name'] = info['Package']
        m = self.version_re.match(info['Version'])
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
        ret['arch'] = info['Architecture']
        self.spkgname = ''
        self.spkgversion = ''
        self.spkgrelease = ''
        if info.has_key('Source'):
            l = info['Source'].split(" ")
            self.spkgname = l[0]
            #print "mmmmmmmm %s %s" % (info['Source'],self.spkgname)
            VR = None
            if len(l) > 1:
                VR = l[1]
            #(self.spkgname,VR) = info['Source'].split(" ")
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
                #print "not VR  %s %s" % (self.spkgversion,self.spkgrelease)
        else:
            #if ret['arch'] == "all":
            self.spkgname = ret['name']
            self.spkgversion = ret['version']
            self.spkgrelease = ret['release']
        ret['sourceNVRA'] = self.spkgname + "_"
        ret['sourceNVRA'] +=  self.spkgversion + "-"
        ret['sourceNVRA'] +=  self.spkgrelease + "."
        ret['sourceNVRA'] +=  ret['arch']
        #print "sourceNVRA  %s %s" % (ret['name'],ret['sourceNVRA'])

        fileinfo={}
        fileinfo['size']="%d"%os.path.getsize(self.path)
        fileinfo['md5sum']="0"
        fileinfo['path']=self.path

        ret['files'] = [fileinfo]

        lines=info['description'].split('\n')
        ret['summary'] = lines[0]
        ret['description'] = string.join(map(lambda l: ' ' + l, lines[1:]), '\n')

        

        fret={}
        for k in fields:
            fret[k] = ret[k]
        return fret



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
