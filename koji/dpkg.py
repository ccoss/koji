import os
import re
import string
import logging
import hashlib
import glob
import tarfile
import gzip
import time
from email.utils import parsedate

try:
    from debian import debfile
    from debian import deb822
    from debian.changelog import *
except ImportError:
    try:
        from debian_bundle import debfile
        from debian_bundle import deb822
        from debian_bundle.changelog import *
    except ImportError:
        sys.stderr.write("cant load debian module")
        sys.stderr.flush()
        sys.exit(1)

debian_version_chars = 'a-zA-Z\d.~+-'
#version_re = re.compile(r'\bVersion:\s*((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*\n' % debian_version_chars)

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

class DpkgInfo(PkgInfo):
    """Base class for dpkg Info"""

    def __init__(self, path):
        super( DpkgInfo, self ).__init__(path)
        self.ret = {}

    def getInfo( self, fields ): 
        for f in fields:
            log_error("getattr:%r"%getattr(self, 'get_%s'%f))
            getattr(self, 'get_%s'%f).__call__(  )
        log_error("aaaaaaaaaa:%r"%self.ret)
        return self.ret

    def get_name( self ):pass
    def get_arch( self ):pass

    def get_version( self ):pass
    def get_release( self ):pass
    def get_epoch( self ):pass
    def get_sourceNVRA( self ):pass

    def get_sourcepackage( self ):pass
    def get_type( self ):pass
    def get_size( self ):pass
    def get_buildtime( self ):pass
    def get_exclusivearch( self ):pass
    def get_excludearch( self ):pass
    def get_buildarchs( self ):pass

    def get_files( self ):pass

    def get_filenames( self ):pass
    def get_filemd5s( self ):pass
    def get_filesizes( self ):pass
    def get_fileflags( self ):pass
    def get_fileusername( self ):pass
    def get_filegroupname( self ):pass
    def get_filemtimes( self ):pass
    def get_filemodes( self ):pass

    def get_PROVIDENAME( self ):pass
    def get_PROVIDEFLAGS( self ):pass
    def get_PROVIDEVERSION( self ):pass

    def get_OBSOLETENAME( self ):pass
    def get_OBSOLETEFLAGS( self ):pass
    def get_OBSOLETEVERSION( self ):pass

    def get_REQUIRENAME( self ):pass
    def get_REQUIREFLAGS( self ):pass
    def get_REQUIREVERSION( self ):pass

    def get_CONFLICTNAME( self ):pass
    def get_CONFLICTFLAGS( self ):pass
    def get_CONFLICTVERSION( self ):pass

    def get_changelogtime( self ):pass
    def get_changelogname( self ):pass
    def get_changelogtext( self ):pass

    def get_summary( self ):pass
    def get_description( self ):pass


class DscInfo(DpkgInfo):

    def __init__(self, path):
        super( DscInfo, self ).__init__(path)
        fd = file(self.path)
        self._content = fd.read()
        fd.close()
        self._fromdir = os.path.dirname(self.path)


    def get_name( self ):
        name_re = re.compile(r'\bSource:\s*(?P<name>.+)\s*\n')
        m = name_re.search(self._content)
        if m:
            self.ret['name'] = m.group('name')

    def get_arch( self ):
        self.ret['arch'] = 'src'

    def get_version( self ):
        version_re = re.compile(r'\bVersion:\s*((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*\n' % debian_version_chars)
        m = version_re.search( self._content)
        if m :
            if '-' in m.group('version'):
                self.ret['release'] = m.group('version').split("-")[-1]
                self.ret['version'] = "-".join(m.group('version').split("-")[0:-1])
            else:
                self.ret['version'] = m.group('version')
                self.ret['release'] = "debiannative"
            if m.group('epoch'):
                self.ret['epoch'] = m.group('epoch')
            else:
                self.ret['epoch'] = None

    def get_sourcepackage( self ):
        self.ret['sourcepackage'] = 1

    def get_type( self ):
        self.ret['type'] = "dsc"

    def get_size( self ):
        self.ret['size'] = os.path.getsize( self.path )

    def get_buildtime( self ):
        self.ret['buildtime'] = int(os.stat(self.path).st_ctime)

    def get_exclusivearch( self ):
        self.ret['exclusivearch'] = ''

    def get_excludearch( self ):
        self.ret['excludearch'] = ''

    def get_buildarchs( self ):
        buildarchs_re = re.compile(r'\bArchitecture:\s*(?P<buildarchs>.+)\s*\n')
        m = buildarchs_re.search(self._content)
        if m:
            self.ret['buildarchs'] = m.group('buildarchs')

    def get_files( self ):
        files_re = re.compile(r'\bFiles:\s*\n(?P<files>(([ ]+[^\n]+\n)+))')
        md5 = hashlib.md5()
        md5.update(self._content)
        self.ret['files']=[{"md5sum":md5.hexdigest(),"size":os.path.getsize( self.path ),"path":self.path}]
        m = files_re.search(self._content)
        if m:
            for l in m.group('files').lstrip().rstrip().split("\n"):
                if len(l) > 0 :
                    ss=l.lstrip().rstrip().split(" ")
                    fileinfo={}
                    fileinfo['md5sum'] = ss[0]
                    fileinfo['size'] = ss[1]
                    fileinfo['path'] = os.path.join(self._fromdir,ss[2])
                    self.ret['files'].append(fileinfo)

    def get_filenames( self ):
        self.get_files()
        self.ret['filenames'] = []
        self.ret['filemd5s'] = []
        self.ret['filesizes'] = []
        self.ret['fileflags'] = []
        self.ret['fileusername'] = []
        self.ret['filegroupname'] = []
        self.ret['filemtimes'] = []
        self.ret['filemodes'] = []
        for i in self.ret['files']:
            self.ret['filenames'].append(os.path.basename(i['path']))
            self.ret['filemd5s'].append(i['md5sum'])
            self.ret['filesizes'].append(i['size'])
            self.ret['fileflags'].append(0)
            self.ret['fileusername'].append('')
            self.ret['filegroupname'].append('')
            self.ret['filemtimes'].append(0)
            self.ret['filemodes'].append(0)

    def get_PROVIDENAME( self ):
        self.ret['PROVIDENAME'] = []
        self.ret['PROVIDEFLAGS'] = []
        self.ret['PROVIDEVERSION'] = []

    def get_OBSOLETENAME( self ):
        self.ret['OBSOLETENAME'] = []
        self.ret['OBSOLETEFLAGS'] = []
        self.ret['OBSOLETEVERSION'] = []

    def get_REQUIRENAME( self ):
        self.ret['REQUIRENAME'] = []
        self.ret['REQUIREFLAGS'] = []
        self.ret['REQUIREVERSION'] = []
        builddep_re = re.compile(r'\bBuild-Depends:\s*(?P<builddep>.+)\s*\n')
        m = builddep_re.search( self._content )
        builddeps = ''
        if m:
            builddeps = m.group('builddep')

        buildindep_re = re.compile(r'\bBuild-Depends-Indep:\s*(?P<buildindep>.+)\s*\n')
        m = buildindep_re.search( self._content )
        buildindeps = None
        if m:
            buildindeps = m.group('buildindep')

        if buildindeps:
            builddeps += buildindeps
        deps = builddeps.split(', ')
        for d in deps:
            self.ret['REQUIRENAME'].append( d )
            self.ret['REQUIREFLAGS'].append(0)
            self.ret['REQUIREVERSION'].append('')

    def get_CONFLICTNAME( self ):
        self.ret['CONFLICTNAME'] = []
        self.ret['CONFLICTFLAGS'] = []
        self.ret['CONFLICTVERSION'] = []
        buildconf_re = re.compile(r'\bBuild-Conflicts:\s*(?P<buildconf>.+)\s*\n')
        m = buildconf_re.search( self._content )
        buildconfs = ''
        if m:
            buildconfs = m.group('buildconf')

        buildinconf_re = re.compile(r'\bBuild-Conflicts-Indep:\s*(?P<buildinconf>.+)\s*\n')
        m = buildinconf_re.search( self._content )
        buildinconfs = None
        if m:
            buildinconfs = m.group('buildinconf')

            if buildinconfs:
                buildconfs += buildinconfs
            if len(buildconfs) > 0:
                confs = buildconfs.split(', ')
                for d in confs:
                    self.ret['CONFLICTNAME'].append(d)
                    self.ret['CONFLICTFLAGS'].append(0)
                    self.ret['CONFLICTVERSION'].append('')

    def get_changelogname( self ):
        changelog=''
        self.ret['changelogtime']=[]
        self.ret['changelogname']=[]
        self.ret['changelogtext']=[]
        diffgz = glob.glob( '%s/*.diff.gz' % self._fromdir )
        if len(diffgz) > 0:
            changelog_re = re.compile(r'\+\+\+.*\/debian\/changelog\n\@\@.+\@\@\n(?P<changelog>((\+[^\n]*\n)+))\-\-\-.*\n')
            fd = gzip.open( diffgz[0], 'rb' )
            c = fd.read()
            m = changelog_re.search(c)
            rchangelog = ''
            if m:
                rchangelog=m.group('changelog')
            for s in rchangelog.split('\n'):
                changelog +=  s.lstrip('+') + '\n'
            fd.close()

        debiantarbz2 = glob.glob('%s/*.debian.tar.bz2'%self._fromdir)
        if len( debiantarbz2 ) > 0:
            fd =  tarfile.open( debiantarbz2[0], mode = 'r:bz2' )
            changelogfd = fd.extractfile('debian/changelog')
            changelog = changelogfd.read()
            changelogfd.close()
            fd.close()

        ntargz = glob.glob('%s/*[0-9].tar.gz'%self._fromdir)
        if len( ntargz ) > 0:
            fd = tarfile.open( ntargz[0], mode = 'r:gz' )
            cf = [a for a in fd.getnames() if a.find('debian/changelog') >= 0]
            changelogfd = fd.extractfile(cf[0])
            changelog = changelogfd.read()
            changelogfd.close()
            fd.close()
        blocks = Changelog(changelog)
        for b in blocks:
            self.ret['changelogname'].append( "%s %s"%( b.author, b.version ) )
            self.ret['changelogtime'].append( time.mktime( parsedate( b.date ) ) )
            self.ret['changelogtext'].append( '\n-'.join( b.changes() ) )

    def get_summary( self ):
        self.ret['summary'] = ''

    def get_description( self ):
        self.ret['description'] = ''


class DebInfo(DpkgInfo):

    def __init__(self, path):
        super( DebInfo, self ).__init__(path)
        self._deb = debfile.DebFile(self.path)
        self._info = self._deb.debcontrol()

    def get_name( self ):
        self.ret['name'] = self._info['Package']

    def get_arch( self ):
        self.ret['arch'] = self._info['Architecture']

    def get_version( self ):
        version_re = re.compile(r'((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*$' % debian_version_chars)
        m = version_re.match(self._info['Version'])
        if m :
            if '-' in m.group('version'):
                self.ret['release'] = m.group('version').split("-")[-1]
                self.ret['version'] = "-".join(m.group('version').split("-")[0:-1])
            else:
                self.ret['version'] = m.group('version')
                self.ret['release'] = "debiannative"
            if m.group('epoch'):
                self.ret['epoch'] = m.group('epoch')
            else:
                self.ret['epoch'] = None
    def get_sourceNVRA( self ):
        self.spkgname = ''
        self.spkgversion = ''
        self.spkgrelease = ''
        version_re = re.compile(r'((?P<epoch>\d+)\:)?(?P<version>[%s]+)\s*$' % debian_version_chars)
        self.get_version()
        if self._info.has_key('Source'):
            l = self._info['Source'].split(" ")
            self.spkgname = l[0]
            #print "mmmmmmmm %s %s" % (info['Source'],self.spkgname)
            VR = None
            if len(l) > 1:
                VR = l[1]
            #(self.spkgname,VR) = info['Source'].split(" ")
            if VR:
                VR = VR.strip("(").strip(")")
                m = version_re.match(VR)
                if m :
                    if '-' in m.group('version'):
                        self.spkgrelease = m.group('version').split("-")[-1]
                        self.spkgversion = "-".join(m.group('version').split("-")[0:-1])
                    else:
                        self.spkgversion = m.group('version')
                        self.spkgrelease = "debiannative"
            else:
                self.spkgversion = self.ret['version']
                self.spkgrelease = self.ret['release']
                #print "not VR  %s %s" % (self.spkgversion,self.spkgrelease)
        else:
            #if ret['arch'] == "all":
            self.get_name()
            self.spkgname = self.ret['name']
            self.spkgversion = self.ret['version']
            self.spkgrelease = self.ret['release']
        self.get_arch()
        self.ret['sourceNVRA'] = self.spkgname + "_"
        self.ret['sourceNVRA'] +=  self.spkgversion + "-"
        self.ret['sourceNVRA'] +=  self.spkgrelease + "."
        self.ret['sourceNVRA'] +=  self.ret['arch']
        #print "sourceNVRA  %s %s" % (ret['name'],ret['sourceNVRA'])


    def get_sourcepackage( self ):
        self.ret['sourcepackage'] = 0

    def get_type( self ):
        self.ret['type'] = "deb"

    def get_size( self ):
        self.ret['size'] = os.path.getsize(self.path)

    def get_buildtime( self ):
        self.ret['buildtime'] = int(os.stat(self.path).st_ctime)

    def get_files( self ):
        fileinfo={}
        fileinfo['size']="%d"%os.path.getsize(self.path)
        fileinfo['md5sum']="0"
        fileinfo['path']=self.path

        self.ret['files'] = [fileinfo]

    def get_filenames( self ):
        self.ret['filenames'] = []
        self.ret['filemd5s'] = []
        self.ret['filesizes'] = []
        self.ret['fileflags'] = []
        self.ret['fileusername'] = []
        self.ret['filegroupname'] = []
        self.ret['filemtimes'] = []
        self.ret['filemodes'] = []
        tgz = self._deb.data.tgz()
        md5sum = self._deb.md5sums()
        for i in tgz.getmembers():
            if i.isfile():
                self.ret['filenames'].append(i.name.lstrip('.'))
                if md5sum.has_key( i.name.lstrip('./') ):
                    self.ret['filemd5s'].append(md5sum[i.name.lstrip('./')])
                else:
                    self.ret['filemd5s'].append(0)
                self.ret['filesizes'].append(i.size)
                self.ret['fileflags'].append(0)
                self.ret['fileusername'].append(i.uname)
                self.ret['filegroupname'].append(i.gname)
                self.ret['filemtimes'].append(i.mtime)
                self.ret['filemodes'].append(i.mode)


    def get_PROVIDENAME( self ):
        self.ret['PROVIDENAME'] = []
        self.ret['PROVIDEFLAGS'] = []
        self.ret['PROVIDEVERSION'] = []
        if self._info.has_key('Provides'):
            for i in self._info['Provides'].split(', '):
                self.ret['PROVIDENAME'].append( i )
                self.ret['PROVIDEFLAGS'].append( 0 )
                self.ret['PROVIDEVERSION'].append( '' )

    def get_OBSOLETENAME( self ):
        self.ret['OBSOLETENAME'] = []
        self.ret['OBSOLETEFLAGS'] = []
        self.ret['OBSOLETEVERSION'] = []


    def get_REQUIRENAME( self ):
        self.ret['REQUIRENAME'] = []
        self.ret['REQUIREFLAGS'] = []
        self.ret['REQUIREVERSION'] = []
        if self._info.has_key('Depends'):
            for i in self._info['Depends'].split(','):
                self.ret['REQUIRENAME'].append( i )
                self.ret['REQUIREFLAGS'].append(0)
                self.ret['REQUIREVERSION'].append('')
        if self._info.has_key('Pre-Depends'):
             for i in self._info['Pre-Depends'].split(','):
                self.ret['REQUIRENAME'].append( i )
                self.ret['REQUIREFLAGS'].append(0)
                self.ret['REQUIREVERSION'].append('')


    def get_CONFLICTNAME( self ):
        self.ret['CONFLICTNAME'] = []
        self.ret['CONFLICTFLAGS'] = []
        self.ret['CONFLICTVERSION'] = []
        if self._info.has_key('Conflicts'):
            for i in self._info['Conflicts'].split(', '):
                self.ret['CONFLICTNAME'].append( i )
                self.ret['CONFLICTFLAGS'].append( 0 )
                self.ret['CONFLICTVERSION'].append( '' )
                


    def get_summary( self ):
        lines = self._info['description'].split('\n')
        self.ret['summary'] = lines[0]
        self.ret['description'] = string.join(map(lambda l: ' ' + l, lines[1:]), '\n')



