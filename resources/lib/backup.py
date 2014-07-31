import xbmc
import xbmcgui
import xbmcvfs
import utils as utils
import time
import json
from vfs import XBMCFileSystem,DropboxFileSystem,ZipFileSystem

def folderSort(aKey):
    result = aKey[0]
    
    if(len(result) < 8):
        result = result + "0000"

    return result
    

class XbmcBackup:
    #constants for initiating a back or restore
    Backup = 0
    Restore = 1

    #file systems
    xbmc_vfs = None
    remote_vfs = None
    saved_remote_vfs = None
    
    restoreFile = None
    remote_base_path = None
    
    #for the progress bar
    progressBar = None
    filesLeft = 0
    filesTotal = 1

    fileManager = None
    restore_point = None
    skip_advanced = False   #if we should check for the existance of advancedsettings in the restore
    
    def __init__(self):
        self.xbmc_vfs = XBMCFileSystem(xbmc.translatePath('special://home'))

        self.configureRemote()
        utils.log(utils.getString(30046))

    def configureRemote(self):
        if(utils.getSetting('remote_selection') == '1'):
            self.remote_base_path = utils.getSetting('remote_path_2');
            self.remote_vfs = XBMCFileSystem(utils.getSetting('remote_path_2'))
	    utils.setSetting("remote_path","")
        elif(utils.getSetting('remote_selection') == '0'):
            self.remote_base_path = utils.getSetting('remote_path');
            self.remote_vfs = XBMCFileSystem(utils.getSetting("remote_path"))
        elif(utils.getSetting('remote_selection') == '2'):
            self.remote_base_path = "/"
            self.remote_vfs = DropboxFileSystem("/")

    def remoteConfigured(self):
        result = True

        if(self.remote_base_path == ""):
            result = False

        return result

    def listBackups(self):
        result = []

        #get all the folders in the current root path
        dirs,files = self.remote_vfs.listdir(self.remote_base_path)
        
        for aDir in dirs:
            if(self.remote_vfs.exists(self.remote_base_path + aDir + "/xbmcbackup.val")):

                #folder may or may not contain time, older versions didn't include this
                folderName = ''
                if(len(aDir) > 8):
                    folderName = aDir[6:8] + '-' + aDir[4:6] + '-' + aDir[0:4] + " " + aDir[8:10] + ":" + aDir[10:12]
                else:
                    folderName = aDir[6:8] + '-' + aDir[4:6] + '-' + aDir[0:4]

                result.append((aDir,folderName))

        for aFile in files:
            file_ext = aFile.split('.')[-1]
           
            if(file_ext == 'zip'):
                
                #folder may or may not contain time, older versions didn't include this
                folderName = ''
                if(len(aFile ) > 8):
                    folderName = aFile [6:8] + '-' + aFile [4:6] + '-' + aFile [0:4] + " " + aFile [8:10] + ":" + aFile [10:12]
                else:
                    folderName = aFile [6:8] + '-' + aFile [4:6] + '-' + aFile [0:4]

                result.append((aFile ,folderName))
                

        result.sort(key=folderSort)
        
        return result

    def selectRestore(self,restore_point):
        self.restore_point = restore_point

    def skipAdvanced(self):
        self.skip_advanced = True

    def run(self,mode=-1,progressOverride=False):
        #set windows setting to true
        window = xbmcgui.Window(10000)
        window.setProperty(utils.__addon_id__ + ".running","true")
        
        #append backup folder name
        progressBarTitle = utils.getString(30010) + " - "
        if(mode == self.Backup and self.remote_vfs.root_path != ''):
            if(utils.getSetting("compress_backups") == 'true'):
                #save the remote file system and use the zip vfs
                self.saved_remote_vfs = self.remote_vfs
                self.remote_vfs = ZipFileSystem(xbmc.translatePath(utils.data_dir() + "xbmc_backup_temp.zip"),"w")
                
            self.remote_vfs.set_root(self.remote_vfs.root_path + time.strftime("%Y%m%d%H%M") + "/")
            progressBarTitle = progressBarTitle + utils.getString(30016)
        elif(mode == self.Restore and self.restore_point != None and self.remote_vfs.root_path != ''):
            if(self.restore_point.split('.')[-1] != 'zip'):
                self.remote_vfs.set_root(self.remote_vfs.root_path + self.restore_point + "/")
            progressBarTitle = progressBarTitle + utils.getString(30017)
        else:
            #kill the program here
            self.remote_vfs = None
            return

        utils.log(utils.getString(30047) + ": " + self.xbmc_vfs.root_path)
        utils.log(utils.getString(30048) + ": " + self.remote_vfs.root_path)

        
        #setup the progress bar
        self.progressBar = BackupProgressBar(progressOverride)
        self.progressBar.create(progressBarTitle,utils.getString(30049) + "......")

        if(mode == self.Backup):
            utils.log(utils.getString(30023) + " - " + utils.getString(30016))
            #check if remote path exists
            if(self.remote_vfs.exists(self.remote_vfs.root_path)):
                #may be data in here already
                utils.log(utils.getString(30050))
            else:
                #make the remote directory
                self.remote_vfs.mkdir(self.remote_vfs.root_path)

            #create a validation file for backup rotation
            self._createValidationFile()

            utils.log(utils.getString(30051))
            allFiles = []
            fileManager = FileManager(self.xbmc_vfs)
         
            #go through each of the user selected items and write them to the backup store
            if(utils.getSetting('backup_addons') == 'true'):
                fileManager.addFile("-addons")
                fileManager.walkTree(xbmc.translatePath('special://home/addons'))

            fileManager.addFile("-userdata")

            if(utils.getSetting('backup_addon_data') == 'true'):
                fileManager.addFile("-userdata/addon_data")
                fileManager.walkTree(xbmc.translatePath('special://home/userdata/addon_data'))

            if(utils.getSetting('backup_database') == 'true'):
                fileManager.addFile("-userdata/Database")
                fileManager.walkTree(xbmc.translatePath('special://home/userdata/Database'))
        
            if(utils.getSetting("backup_playlists") == 'true'):
                fileManager.addFile("-userdata/playlists")
                fileManager.walkTree(xbmc.translatePath('special://home/userdata/playlists'))

            if(utils.getSetting('backup_profiles') == 'true'):
                fileManager.addFile("-userdata/profiles")
                fileManager.walkTree(xbmc.translatePath('special://home/userdata/profiles'))
            
            if(utils.getSetting("backup_thumbnails") == "true"):
                fileManager.addFile("-userdata/Thumbnails")
                fileManager.walkTree(xbmc.translatePath('special://home/userdata/Thumbnails'))
	  
            if(utils.getSetting("backup_config") == "true"):
                fileManager.addFile("-userdata/keymaps")
                fileManager.walkTree(xbmc.translatePath('special://home/userdata/keymaps'))
                
                fileManager.addFile("-userdata/peripheral_data")
                fileManager.walkTree(xbmc.translatePath('special://home/userdata/peripheral_data'))
            
                #this part is an oddity
                dirs,configFiles = self.xbmc_vfs.listdir(xbmc.translatePath('special://home/userdata/'))
                for aFile in configFiles:
                    if(aFile.endswith(".xml")):
                        fileManager.addFile(xbmc.translatePath('special://home/userdata/') + aFile)

            #add to array
            self.filesTotal = fileManager.size()
            allFiles.append({"source":self.xbmc_vfs.root_path,"dest":self.remote_vfs.root_path,"files":fileManager.getFiles()})

            #check if there are custom directories
            if(utils.getSetting('custom_dir_1_enable') == 'true' and utils.getSetting('backup_custom_dir_1') != ''):

                #create a special remote path with hash                
                self.xbmc_vfs.set_root(utils.getSetting('backup_custom_dir_1'))
                fileManager.addFile("-custom_" + self._createCRC(self.xbmc_vfs.root_path))

                #walk the directory
                fileManager.walkTree(self.xbmc_vfs.root_path)
                self.filesTotal = self.filesTotal + fileManager.size()
                allFiles.append({"source":self.xbmc_vfs.root_path,"dest":self.remote_vfs.root_path + "custom_" + self._createCRC(self.xbmc_vfs.root_path),"files":fileManager.getFiles()})

            if(utils.getSetting('custom_dir_2_enable') == 'true' and utils.getSetting('backup_custom_dir_2') != ''):

                #create a special remote path with hash                
                self.xbmc_vfs.set_root(utils.getSetting('backup_custom_dir_2'))
                fileManager.addFile("-custom_" + self._createCRC(self.xbmc_vfs.root_path))

                #walk the directory
                fileManager.walkTree(self.xbmc_vfs.root_path)
                self.filesTotal = self.filesTotal + fileManager.size()
                allFiles.append({"source":self.xbmc_vfs.root_path,"dest":self.remote_vfs.root_path + "custom_" + self._createCRC(self.xbmc_vfs.root_path),"files":fileManager.getFiles()})


            #backup all the files
            self.filesLeft = self.filesTotal
            for fileGroup in allFiles:
                self.xbmc_vfs.set_root(fileGroup['source'])
                self.remote_vfs.set_root(fileGroup['dest'])
                self.backupFiles(fileGroup['files'],self.xbmc_vfs,self.remote_vfs)

            if(utils.getSetting("compress_backups") == 'true'):
                #send the zip file to the real remote vfs
                zip_name = self.remote_vfs.root_path[:-1] + ".zip"
                self.remote_vfs.cleanup()
                self.xbmc_vfs.rename(xbmc.translatePath(utils.data_dir() + "xbmc_backup_temp.zip"), xbmc.translatePath(utils.data_dir() + zip_name))
                fileManager.addFile(xbmc.translatePath(utils.data_dir() + zip_name))
               
                #set root to data dir home 
                self.xbmc_vfs.set_root(xbmc.translatePath(utils.data_dir()))
               
                self.remote_vfs = self.saved_remote_vfs
                self.progressBar.updateProgress(0, "Copying Zip Archive")
                self.backupFiles(fileManager.getFiles(),self.xbmc_vfs, self.remote_vfs)
                
                #delete the temp zip file
                self.xbmc_vfs.rmdir(xbmc.translatePath(utils.data_dir() + zip_name))

            #remove old backups
            self._rotateBackups()

        elif (mode == self.Restore):
            utils.log(utils.getString(30023) + " - " + utils.getString(30017))

            #catch for if the restore point is actually a zip file
            if(self.restore_point.split('.')[-1] == 'zip'):
                #copy just this file from the remote vfs
                zipFile = []
                zipFile.append(self.restore_point)
               
                #set root to data dir home 
                self.xbmc_vfs.set_root(xbmc.translatePath(utils.data_dir()))
               
                self.progressBar.updateProgress(0, "Copying Zip Archive")
                self.backupFiles(zipFile,self.remote_vfs, self.xbmc_vfs)

                #set the new remote vfs
                self.remote_vfs = ZipFileSystem(xbmc.translatePath(utils.data_dir() + self.restore_point),'r')
            else:
                #for restores remote path must exist
                if(not self.remote_vfs.exists(self.remote_vfs.root_path)):
                    xbmcgui.Dialog().ok(utils.getString(30010),utils.getString(30045),self.remote_vfs.root_path)
                    return

            if(not self._checkValidationFile(self.remote_vfs.root_path)):
                #don't continue
                return

            utils.log(utils.getString(30051))
            allFiles = []
            fileManager = FileManager(self.remote_vfs)
         
            #go through each of the user selected items and write them to the backup store

            if(utils.getSetting("backup_config") == "true"):
                #check for the existance of an advancedsettings file
                if(self.remote_vfs.exists(self.remote_vfs.root_path + "userdata/advancedsettings.xml") and not self.skip_advanced):
                    #let the user know there is an advanced settings file present
                    restartXbmc = xbmcgui.Dialog().yesno(utils.getString(30038),utils.getString(30039),utils.getString(30040), utils.getString(30041))

                    if(restartXbmc):
                        #add only this file to the file list
                        fileManager.addFile(self.remote_vfs.root_path + "userdata/advancedsettings.xml")
                        self.backupFiles(fileManager.getFiles(),self.remote_vfs,self.xbmc_vfs)

                        #let the service know to resume this backup on startup
                        self._createResumeBackupFile()

                        #do not continue running
                        xbmcgui.Dialog().ok(utils.getString(30077),utils.getString(30078))
                        
                        return
                
                self.xbmc_vfs.mkdir(xbmc.translatePath('special://home/userdata/keymaps'))
                fileManager.walkTree(self.remote_vfs.root_path + "userdata/keymaps")
                
                self.xbmc_vfs.mkdir(xbmc.translatePath('special://home/userdata/peripheral_data'))
                fileManager.walkTree(self.remote_vfs.root_path + "userdata/peripheral_data")
            
                #this part is an oddity
                dirs,configFiles = self.remote_vfs.listdir(self.remote_vfs.root_path + "userdata/")
                for aFile in configFiles:
                    if(aFile.endswith(".xml")):
                        fileManager.addFile(self.remote_vfs.root_path + "userdata/" + aFile)

            if(utils.getSetting('backup_addons') == 'true'):
                self.xbmc_vfs.mkdir(xbmc.translatePath('special://home/addons'))
                fileManager.walkTree(self.remote_vfs.root_path + "addons")

            self.xbmc_vfs.mkdir(xbmc.translatePath('special://home/userdata'))

            if(utils.getSetting('backup_addon_data') == 'true'):
                self.xbmc_vfs.mkdir(xbmc.translatePath('special://home/userdata/addon_data'))
                fileManager.walkTree(self.remote_vfs.root_path + "userdata/addon_data")

            if(utils.getSetting('backup_database') == 'true'):
                self.xbmc_vfs.mkdir(xbmc.translatePath('special://home/userdata/Database'))
                fileManager.walkTree(self.remote_vfs.root_path + "userdata/Database")
        
            if(utils.getSetting("backup_playlists") == 'true'):
                self.xbmc_vfs.mkdir(xbmc.translatePath('special://home/userdata/playlists'))
                fileManager.walkTree(self.remote_vfs.root_path + "userdata/playlists")

            if(utils.getSetting('backup_profiles') == 'true'):
                self.xbmc_vfs.mkdir(xbmc.translatePath('special://home/userdata/profiles'))
                fileManager.walkTree(self.remote_vfs.root_path + "userdata/profiles")
                
            if(utils.getSetting("backup_thumbnails") == "true"):
                self.xbmc_vfs.mkdir(xbmc.translatePath('special://home/userdata/Thumbnails'))
                fileManager.walkTree(self.remote_vfs.root_path + "userdata/Thumbnails")
	  
            #add to array
            self.filesTotal = fileManager.size()
            allFiles.append({"source":self.remote_vfs.root_path,"dest":self.xbmc_vfs.root_path,"files":fileManager.getFiles()})    

            #check if there are custom directories
            if(utils.getSetting('custom_dir_1_enable') == 'true' and utils.getSetting('backup_custom_dir_1') != ''):

                self.xbmc_vfs.set_root(utils.getSetting('backup_custom_dir_1'))
                if(self.remote_vfs.exists(self.remote_vfs.root_path + "custom_" + self._createCRC(self.xbmc_vfs.root_path))):
                    #index files to restore
                    fileManager.walkTree(self.remote_vfs.root_path + "custom_" + self._createCRC(self.xbmc_vfs.root_path))
                    self.filesTotal = self.filesTotal + fileManager.size()
                    allFiles.append({"source":self.remote_vfs.root_path + "custom_" + self._createCRC(self.xbmc_vfs.root_path),"dest":self.xbmc_vfs.root_path,"files":fileManager.getFiles()})
                else:
                    xbmcgui.Dialog().ok(utils.getString(30010),utils.getString(30045),self.remote_vfs.root_path + "custom_" + self._createCRC(utils.getSetting('backup_custom_dir_1')))

            if(utils.getSetting('custom_dir_2_enable') == 'true' and utils.getSetting('backup_custom_dir_2') != ''):

                self.xbmc_vfs.set_root(utils.getSetting('backup_custom_dir_2'))
                if(self.remote_vfs.exists(self.remote_vfs.root_path + "custom_" + self._createCRC(self.xbmc_vfs.root_path))):
                    #index files to restore
                    fileManager.walkTree(self.remote_vfs.root_path + "custom_" + self._createCRC(self.xbmc_vfs.root_path))
                    self.filesTotal = self.filesTotal + fileManager.size()
                    allFiles.append({"source":self.remote_vfs.root_path + "custom_" + self._createCRC(self.xbmc_vfs.root_path),"dest":self.xbmc_vfs.root_path,"files":fileManager.getFiles()})
                else:
                    xbmcgui.Dialog().ok(utils.getString(30010),utils.getString(30045),self.remote_vfs.root_path + "custom_" + self._createCRC(utils.getSetting('backup_custom_dir_2')))


            #restore all the files
            self.filesLeft = self.filesTotal
            for fileGroup in allFiles:
                self.remote_vfs.set_root(fileGroup['source'])
                self.xbmc_vfs.set_root(fileGroup['dest'])
                self.backupFiles(fileGroup['files'],self.remote_vfs,self.xbmc_vfs)

            #call update addons to refresh everything
            xbmc.executebuiltin('UpdateLocalAddons')

        self.xbmc_vfs.cleanup()
        self.remote_vfs.cleanup()
        self.progressBar.close()

        #reset the window setting
        window.setProperty(utils.__addon_id__ + ".running","")

    def backupFiles(self,fileList,source,dest):
        utils.log("Writing files to: " + dest.root_path)
        utils.log("Source: " + source.root_path)
        for aFile in fileList:
            if(not self.progressBar.checkCancel()):
                utils.log('Writing file: ' + aFile,xbmc.LOGDEBUG)
                if(aFile.startswith("-")):
                    self._updateProgress(aFile[len(source.root_path) + 1:])
                    dest.mkdir(dest.root_path + aFile[len(source.root_path) + 1:])
                else:
                    self._updateProgress()
                    if(isinstance(source,DropboxFileSystem)):
                        #if copying from dropbox we need the file handle, use get_file
                        source.get_file(aFile,dest.root_path + aFile[len(source.root_path):])
                    else:
                        #copy using normal method
                        dest.put(aFile,dest.root_path + aFile[len(source.root_path):])

    def _createCRC(self,string):
        #create hash from string
        string = string.lower()        
        bytes = bytearray(string.encode())
        crc = 0xffffffff;
        for b in bytes:
            crc = crc ^ (b << 24)          
            for i in range(8):
                if (crc & 0x80000000 ):                 
                    crc = (crc << 1) ^ 0x04C11DB7                
                else:
                    crc = crc << 1;                        
                    crc = crc & 0xFFFFFFFF
        
        return '%08x' % crc

    def _updateProgress(self,message=None):
        self.filesLeft = self.filesLeft - 1
        self.progressBar.updateProgress(int((float(self.filesTotal - self.filesLeft)/float(self.filesTotal)) * 100),message)

    def _rotateBackups(self):
        total_backups = int(utils.getSetting('backup_rotation'))
        if(total_backups > 0):
            #get a list of valid backup folders
            dirs = self.listBackups()

            if(len(dirs) > total_backups):
                #remove backups to equal total wanted
                remove_num = 0
                self.filesTotal = self.filesTotal + remove_num + 1

                #update the progress bar if it is available
                while(remove_num < (len(dirs) - total_backups) and not self.progressBar.checkCancel()):
                    self._updateProgress(utils.getString(30054) + " " + dirs[remove_num][1])
                    utils.log("Removing backup " + dirs[remove_num][0])
                    self.remote_vfs.rmdir(self.remote_base_path + dirs[remove_num][0] + "/")
                    remove_num = remove_num + 1

    def _createValidationFile(self):
        vFile = xbmcvfs.File(xbmc.translatePath(utils.data_dir() + "xbmcbackup.val"),'w')
        vFile.write(json.dumps({"name":"XBMC Backup Validation File","xbmc_version":xbmc.getInfoLabel('System.BuildVersion')}))
        vFile.write("")
        vFile.close()

        self.remote_vfs.put(xbmc.translatePath(utils.data_dir() + "xbmcbackup.val"),self.remote_vfs.root_path + "xbmcbackup.val")

    def _checkValidationFile(self,path):
        result = False
        
        #copy the file and open it
        self.xbmc_vfs.put(path + "xbmcbackup.val",xbmc.translatePath(utils.data_dir() + "xbmcbackup.val"))

        vFile = xbmcvfs.File(xbmc.translatePath(utils.data_dir() + "xbmcbackup.val"),'r')
        jsonString = vFile.read()
        vFile.close()

        try:
            json_dict = json.loads(jsonString)

            if(xbmc.getInfoLabel('System.BuildVersion') == json_dict['xbmc_version']):
                result = True
            else:
                result = xbmcgui.Dialog().yesno(utils.getString(30085),utils.getString(30086),utils.getString(30044))
                
        except ValueError:
            #may fail on older archives
            result = True

        return result

    def _createResumeBackupFile(self):
        rFile = xbmcvfs.File(xbmc.translatePath(utils.data_dir() + "resume.txt"),'w')
        rFile.write(self.restore_point)
        rFile.close()

class FileManager:
    fileArray = []
    not_dir = ['.zip','.xsp','.rar']
    vfs = None

    def __init__(self,vfs):
        self.vfs = vfs

    def walkTree(self,directory):
       
        if(self.vfs.exists(directory)):
            dirs,files = self.vfs.listdir(directory)
        
            #create all the subdirs first
            for aDir in dirs:
                dirPath = xbmc.translatePath(directory + "/" + aDir)
                file_ext = aDir.split('.')[-1]
              
                #don't backup your own zip file
                if(aDir != "xbmc_backup_temp.zip"):
                    self.addFile("-" + dirPath)

                #catch for "non directory" type files
                shouldWalk = True

                for s in file_ext:
                    if(s in self.not_dir):
                        shouldWalk = False
                
                if(shouldWalk):
                    self.walkTree(dirPath)  
            
            #copy all the files
            for aFile in files:
                if(aFile != 'xbmc_backup_temp.zip'):
                    utils.log(aFile)
                    filePath = xbmc.translatePath(directory + "/" + aFile)
                    self.addFile(filePath)
                    
    def addFile(self,filename):
        try:
            filename = filename.decode('UTF-8')
        except UnicodeDecodeError:
            filename = filename.decode('ISO-8859-2')
            
        #write the full remote path name of this file
        utils.log("Add File: " + filename,xbmc.LOGDEBUG)
        self.fileArray.append(filename)

    def getFiles(self):
        result = self.fileArray
        self.fileArray = []
        return result

    def size(self):
        return len(self.fileArray)

class BackupProgressBar:
    NONE = 2
    DIALOG = 0
    BACKGROUND = 1

    mode = 2
    progressBar = None
    override = False
    
    def __init__(self,progressOverride):
        self.override = progressOverride
        
        #check if we should use the progress bar
        if(int(utils.getSetting('progress_mode')) != 2):
            #check if background or normal
            if(int(utils.getSetting('progress_mode')) == 0 and not self.override):
                self.mode = self.DIALOG
                self.progressBar = xbmcgui.DialogProgress()
            else:
                self.mode = self.BACKGROUND
                self.progressBar = xbmcgui.DialogProgressBG()

    def create(self,heading,message):
        if(self.mode != self.NONE):
            self.progressBar.create(heading,message)

    def updateProgress(self,percent,message=None):
        
        #update the progress bar
        if(self.mode != self.NONE):
            if(message != None):
                #need different calls for dialog and background bars
                if(self.mode == self.DIALOG):
                    self.progressBar.update(percent,message)
                else:
                    self.progressBar.update(percent,message=message)
            else:
                 self.progressBar.update(percent)

    def checkCancel(self):
        result = False

        if(self.mode == self.DIALOG):
            result = self.progressBar.iscanceled()

        return result

    def close(self):
        if(self.mode != self.NONE):
            self.progressBar.close()
