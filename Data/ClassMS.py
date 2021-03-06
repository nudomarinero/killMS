#!/usr/bin/env python
"""
killMS, a package for calibration in radio interferometry.
Copyright (C) 2013-2017  Cyril Tasse, l'Observatoire de Paris,
SKA South Africa, Rhodes University

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""
import numpy as np
from pyrap.tables import table
from killMS.Other.rad2hmsdms import rad2hmsdms
from killMS.Other import ModColor
from killMS.Other import reformat
import os
import pyrap.quanta as qa
import pyrap.measures as pm
import ephem
from killMS.Other import MyLogger
log=MyLogger.getLogger("ClassMS")
from killMS.Other import ClassTimeIt
from killMS.Other.progressbar import ProgressBar

class ClassMS():
    def __init__(self,MSname,Col="DATA",zero_flag=True,ReOrder=False,EqualizeFlag=False,DoPrint=True,DoReadData=True,
                 TimeChunkSize=None,GetBeam=False,RejectAutoCorr=False,SelectSPW=None,DelStationList=None,Field=0,DDID=0,
                 ReadUVWDT=False):


        if MSname=="": exit()
        self.ReadUVWDT=ReadUVWDT
        MSname=reformat.reformat(os.path.abspath(MSname),LastSlash=False)
        self.MSName=MSname
        self.ColName=Col
        self.zero_flag=zero_flag
        self.ReOrder=ReOrder
        self.EqualizeFlag=EqualizeFlag
        self.DoPrint=DoPrint
        self.TimeChunkSize=TimeChunkSize
        self.RejectAutoCorr=RejectAutoCorr
        self.SelectSPW=SelectSPW
        self.DelStationList=DelStationList
        self.Field=Field
        self.DDID=DDID
        self.TaQL = "FIELD_ID==%d && DATA_DESC_ID==%d" % (Field, DDID)
        self.ReadMSInfo(MSname,DoPrint=DoPrint)
        self.LFlaggedStations=[]

        self.CurrentChunkTimeRange_SinceT0_sec=None
        try:
            self.LoadLOFAR_ANTENNA_FIELD()
        except:
            self.LOFAR_ANTENNA_FIELD=None
            pass

        #self.LoadLOFAR_ANTENNA_FIELD()

        if DoReadData: self.ReadData()
        #self.RemoveStation()


        self.SR=None
        if GetBeam:
            self.LoadSR()

    def GiveMainTable (self,**kw):
        """Returns main MS table, applying TaQL selection if any"""
        t = table(self.MSName,ack=False,**kw)

        if self.TaQL:
            t = t.query(self.TaQL)
        return t

    def GiveDate(self,tt):
        time_start = qa.quantity(tt, 's')
        me = pm.measures()
        dict_time_start_MDJ = me.epoch('utc', time_start)
        time_start_MDJ=dict_time_start_MDJ['m0']['value']
        JD=time_start_MDJ+2400000.5-2415020
        d=ephem.Date(JD)

        return d.datetime()#.isoformat().replace("T","/")



    def GiveDataChunk(self,it0,it1):
        MapSelBLs=self.MapSelBLs
        nbl=self.nbl
        row0,row1=it0*nbl,it1*nbl
        NtimeBlocks=nt=it1-it0
        nrow=row1-row0
        _,nch,_=self.data.shape

        DataOut=self.data[row0:row1,:,:].copy()
        DataOut=DataOut.reshape((NtimeBlocks,nbl,nch,4))
        DataOut=DataOut[:,self.MapSelBLs,:,:]
        DataOut=DataOut.reshape((DataOut.shape[1]*NtimeBlocks,nch,4))

        flags=self.flag_all[row0:row1,:,:].copy()
        flags=flags.reshape((NtimeBlocks,nbl,nch,4))
        flags=flags[:,self.MapSelBLs,:,:]
        flags=flags.reshape((flags.shape[1]*NtimeBlocks,nch,4))

        uvw=self.uvw[row0:row1,:].copy()
        uvw=uvw.reshape((NtimeBlocks,self.nbl,3))
        uvw=uvw[:,self.MapSelBLs,:]
        uvw=uvw.reshape((uvw.shape[1]*NtimeBlocks,3))

        A0=self.A0[self.MapSelBLs].copy()
        A1=self.A1[self.MapSelBLs].copy()

        times=self.times_all[row0:row1].copy()
        times=times.reshape((NtimeBlocks,self.nbl))
        times=times[:,self.MapSelBLs]
        times=times.reshape((times.shape[1]*NtimeBlocks))
        
        DicoOut={"data":DataOut,
                 "flags":flags,
                 "A0A1":(A0,A1),
                 "times":times,
                 "uvw":uvw}
        return DicoOut


    def PutLOFARKeys(self):
        keys=["LOFAR_ELEMENT_FAILURE", "LOFAR_STATION", "LOFAR_ANTENNA_FIELD"]
        t=self.GiveMainTable()#table(self.MSName,ack=False)
        

        for key in keys:
            t.putkeyword(key,'Table: %s/%s'%(self.MSName,key))
        t.close()

    def DelData(self):
        try:
            del(self.Weights)
        except:
            pass

        try:
            del(self.data,self.flag_all)
        except:
            pass


    def LoadSR(self,useElementBeam=True,useArrayFactor=True):
        if self.SR!=None: return
        # t=table(self.MSName,ack=False,readonly=False)
        # if not("LOFAR_ANTENNA_FIELD" in t.getkeywords().keys()):
        #     self.PutLOFARKeys()
        # t.close()
               
        from lofar.stationresponse import stationresponse
        # f=self.ChanFreq.flatten()
        # if f.shape[0]>1:
        #     t=table(self.MSName+"/SPECTRAL_WINDOW/",ack=False)
        #     c=t.getcol("CHAN_WIDTH")
        #     c.fill(np.abs((f[0:-1]-f[1::])[0]))
        #     t.putcol("CHAN_WIDTH",c)
        #     t.close()

        self.SR = stationresponse(self.MSName,
                                      useElementResponse=useElementBeam,
                                      #useElementBeam=useElementBeam,
                                      useArrayFactor=useArrayFactor)#,useChanFreq=True)
        self.SR.setDirection(self.rarad,self.decrad)
        
    def CopyNonSPWDependent(self,MSnodata):
        MSnodata.A0=self.A0
        MSnodata.A1=self.A1
        MSnodata.uvw=self.uvw
        MSnodata.ntimes=self.ntimes
        MSnodata.times=self.times
        MSnodata.times_all=self.times_all
        MSnodata.LOFAR_ANTENNA_FIELD=self.LOFAR_ANTENNA_FIELD
        return MSnodata

    def LoadLOFAR_ANTENNA_FIELD(self):
        


        t=table("%s/LOFAR_ANTENNA_FIELD"%self.MSName,ack=False)
        #print>>log, ModColor.Str(" ... Loading LOFAR_ANTENNA_FIELD table...")
        na,NTiles,dummy=t.getcol("ELEMENT_OFFSET").shape

        try:
            dummy,nAntPerTiles,dummy=t.getcol("TILE_ELEMENT_OFFSET").shape
            TileOffXYZ=t.getcol("TILE_ELEMENT_OFFSET").reshape(na,1,nAntPerTiles,3)
            RCU=t.getcol("ELEMENT_RCU")
            RCUMask=(RCU!=-1)[:,:,0]
            Flagged=t.getcol("ELEMENT_FLAG")[:,:,0]
        except:
            nAntPerTiles=1
            # RCUMask=(RCU!=-1)[:,:,:]
            # RCUMask=RCUMask.reshape(na,96)
            RCUMask=np.ones((na,96),bool)
            TileOffXYZ=np.zeros((na,1,nAntPerTiles,3),float)
            Flagged=t.getcol("ELEMENT_FLAG")[:,:,0]
            #Flagged=Flagged.reshape(Flagged.shape[0],Flagged.shape[1],1,1)*np.ones((1,1,1,3),bool)
            
        StationXYZ=t.getcol("POSITION").reshape(na,1,1,3)
        ElementOffXYZ=t.getcol("ELEMENT_OFFSET")
        ElementOffXYZ=ElementOffXYZ.reshape(na,NTiles,1,3)
        
        Dico={}
        Dico["FLAGED"]=Flagged
        Dico["StationXYZ"]=StationXYZ
        Dico["ElementOffXYZ"]=ElementOffXYZ
        Dico["TileOffXYZ"]=TileOffXYZ
        #Dico["RCU"]=RCU
        Dico["RCUMask"]=RCUMask
        Dico["nAntPerTiles"]=nAntPerTiles

        t.close()
        self.LOFAR_ANTENNA_FIELD=Dico
        
        
    def GiveBeam(self,time,ra,dec):
        #self.LoadSR()
        Beam=np.zeros((ra.shape[0],self.na,self.NSPWChan,2,2),dtype=np.complex)
        for i in range(ra.shape[0]):
            self.SR.setDirection(ra[i],dec[i])
            Beam[i]=self.SR.evaluate(time)
        #Beam=np.swapaxes(Beam,1,2)
        return Beam


    def GiveMappingAnt(self,ListStrSel,(row0,row1)=(None,None),FlagAutoCorr=True,WriteAttribute=True):

        if type(ListStrSel)!=list:
            assert(False)

        #ListStrSel=["RT9-RTA", "RTA-RTB", "RTC-RTD", "RT6-RT7", "RT5"]

        print>>log, ModColor.Str("  ... Building BL-mapping for %s"%str(ListStrSel))

        if row1==None:
            row0=0
            row1=self.nbl
        A0=self.F_A0[row0:row1]
        A1=self.F_A1[row0:row1]
        MapOut=np.ones((self.nbl,),dtype=np.bool)
        if FlagAutoCorr:
            ind=np.where(A0==A1)[0]
            MapOut[ind]=False

        def GiveStrAntToNum(self,StrAnt):
            ind=[]
            for i in range(len(self.StationNames)):
                if StrAnt in self.StationNames[i]:
                    ind.append(i)
            #print ind
            return ind
        #MapOut=np.ones(A0.shape,bool)###)

        LFlaggedStations=[]
        LNumFlaggedStations=[]

        for blsel in ListStrSel:
            if blsel=="": continue
            if "-" in blsel:
                StrA0,StrA1=blsel.split("-")
                LNumStrA0=GiveStrAntToNum(self,StrA0)
                LNumStrA1=GiveStrAntToNum(self,StrA1)
                for NumStrA0 in LNumStrA0:
                    for NumStrA1 in LNumStrA1:
                        NumA0=np.where(np.array(self.StationNames)==NumStrA0)[0]
                        NumA1=np.where(np.array(self.StationNames)==NumStrA1)[0]
                        C0=((A0==NumA0)&(A1==NumA1))
                        C1=((A1==NumA0)&(A0==NumA1))
                        ind=np.where(C1|C0)[0]
                        MapOut[ind]=False
            else:
                #NumA0=np.where(np.array(self.StationNames)==blsel)[0]
                StrA0=blsel
                LNumStrA0=GiveStrAntToNum(self,StrA0)

                LNumFlaggedStations.append(LNumStrA0)

                for NumStrA0 in LNumStrA0:
                    LFlaggedStations.append(self.StationNames[NumStrA0])
                    # NumA0=np.where(np.array(self.StationNames)==NumStrA0)[0]
                    # stop
                    # print NumStrA0,NumA0
                    C0=(A0==NumStrA0)
                    C1=(A1==NumStrA0)
                    ind=np.where(C1|C0)[0]

                    MapOut[ind]=False

        if WriteAttribute:
            self.MapSelBLs=MapOut
            self.LFlaggedStations=list(set(LFlaggedStations))
            return self.MapSelBLs
        else:
            LNumFlaggedStations=sorted(list(set(range(self.na))-set(np.array(LNumFlaggedStations).flatten().tolist())))
            return LNumFlaggedStations
        


    # def GiveMappingAntOld(self,ListStrSel,(row0,row1)=(None,None),FlagAutoCorr=True):
    #     #ListStrSel=["RT9-RTA", "RTA-RTB", "RTC-RTD", "RT6-RT7", "RT5-RT*"]

    #     print ModColor.Str("  ... Building BL-mapping for %s"%str(ListStrSel))

    #     if row1==None:
    #         row0=0
    #         row1=self.nbl
    #     A0=self.A0[row0:row1]
    #     A1=self.A1[row0:row1]
    #     MapOut=np.ones((self.nbl,),dtype=np.bool)
    #     if FlagAutoCorr:
    #         ind=np.where(A0==A1)[0]
    #         MapOut[ind]=False


    #     for blsel in ListStrSel:
    #         if "-" in blsel:
    #             StrA0,StrA1=blsel.split("-")
    #             NumA0=np.where(np.array(self.StationNames)==StrA0)[0]
    #             NumA1=np.where(np.array(self.StationNames)==StrA1)[0]
    #             C0=((A0==NumA0)&(A1==NumA1))
    #             C1=((A1==NumA0)&(A0==NumA1))
    #         else:
    #             NumA0=np.where(np.array(self.StationNames)==blsel)[0]
    #             C0=(A0==NumA0)
    #             C1=(A1==NumA0)
    #         ind=np.where(C1|C0)[0]
    #         MapOut[ind]=False
    #     self.MapSelBLs=MapOut
    #     return self.MapSelBLs
                



    # def SelChannel(self,(start,end,step)=(None,None,None),Revert=False):
    #     if start!=None:
    #         if Revert==False:
    #             ind=np.arange(self.Nchan)[start:end:step]
    #         else:
    #             ind=np.array(sorted(list(set(np.arange(self.Nchan).tolist())-set(np.arange(self.Nchan)[start:end:step].tolist()))))
    #         self.data=self.data[:,ind,:]
    #         self.flag_all=self.flag_all[:,ind,:]
    #         shape=self.ChanFreq.shape
    #         self.ChanFreq=self.ChanFreq[ind]
                
        
    def ReadData(self,t0=0,t1=-1,DoPrint=False,ReadWeight=False):



        if DoPrint==True:
            print "   ... Reading MS"



        row0=0
        row1=self.F_nrows

        DATA_CHUNK={}
        if t1>t0:

            t0=t0*3600.
            t1=t1*3600.
            self.CurrentChunkTimeRange_SinceT0_sec=(t0,t1)
            t0=t0+self.F_tstart            
            t1=t1+self.F_tstart

            #ind0=np.argmin(np.abs(t0-self.F_times))
            #ind1=np.argmin(np.abs(t1-self.F_times))

            ind0=np.where((t0-self.F_times)<=0)[0][0]
            row0=ind0*self.nbl

            ind1=np.where((t1-self.F_times)<0)[0]
            if ind1.size==0:
                row1=self.F_nrows
            else:
                ind1=ind1[0]
                row1=ind1*self.nbl

        self.ROW0=row0
        self.ROW1=row1
        self.nRowRead=row1-row0

        DATA_CHUNK["ROW0"]=row0
        DATA_CHUNK["ROW1"]=row1
        DATA_CHUNK["nRowRead"]=self.nRowRead


        nRowRead=self.nRowRead

        #table_all=table(self.MSName,ack=False)
        table_all = self.GiveMainTable()
        SPW=table_all.getcol('DATA_DESC_ID',row0,nRowRead)
        A0=table_all.getcol('ANTENNA1',row0,nRowRead)[SPW==self.ListSPW[0]]
        A1=table_all.getcol('ANTENNA2',row0,nRowRead)[SPW==self.ListSPW[0]]
        #print self.ListSPW[0]
        time_all=table_all.getcol("TIME",row0,nRowRead)[SPW==self.ListSPW[0]]
        #print np.max(time_all)-np.min(time_all)
        time_slots_all=np.array(sorted(list(set(time_all))))
        ntimes=time_all.shape[0]/self.nbl

        flag_all=table_all.getcol("FLAG",row0,nRowRead)[SPW==self.ListSPW[0]]
        self.HasWeights=False
        if ReadWeight==True:
            self.Weights=table_all.getcol("WEIGHT",row0,nRowRead)
            self.HasWeights=True

        if self.EqualizeFlag:
            for i in range(self.Nchan):
                fcol=flag_all[:,i,0]|flag_all[:,i,1]|flag_all[:,i,2]|flag_all[:,i,3]
                for pol in range(4):
                    flag_all[:,i,pol]=fcol

        self.multidata=(type(self.ColName)==list)
        self.ReverseAntOrder=(np.where((A0==0)&(A1==1))[0]).shape[0]>0
        self.swapped=False

        uvw=table_all.getcol('UVW',row0,nRowRead)[SPW==self.ListSPW[0]]
        self.TimeInterVal=table_all.getcol("INTERVAL")

        if self.ReOrder:
            vis_all=table_all.getcol(self.ColName,row0,nRowRead)
            if self.zero_flag: vis_all[flag_all==1]=0.
            if self.zero_flag: 
                noise=(np.random.randn(vis_all.shape[0],vis_all.shape[1],vis_all.shape[2])\
                           +1j*np.random.randn(vis_all.shape[0],vis_all.shape[1],vis_all.shape[2]))*1e-6
                vis_all[flag_all==1]=noise[flag_all==1]
            vis_all[np.isnan(vis_all)]=0.
            listDataSPW=[np.swapaxes(vis_all[SPW==i,:,:],0,1) for i in self.ListSPW]
            self.data=np.concatenate(listDataSPW)#np.swapaxes(np.concatenate(listDataSPW),0,1)
            listFlagSPW=[np.swapaxes(flag_all[SPW==i,:,:],0,1) for i in self.ListSPW]
            flag_all=np.concatenate(listFlagSPW)#np.swapaxes(np.concatenate(listDataSPW),0,1)
            self.uvw=uvw
            self.swapped=True
            

        else:
            self.uvw=uvw
            if self.multidata:
                self.data=[]
                for colin in self.ColName:
                    print "... read %s"%colin
                    vis_all=table_all.getcol(colin,row0,nRowRead)[SPW==self.ListSPW[0]]
                    print " shape: %s"%str(vis_all.shape)
                    if self.zero_flag: vis_all[flag_all==1]=0.
                    vis_all[np.isnan(vis_all)]=0.
                    self.data.append(vis_all)
            else:
                vis_all=table_all.getcol(self.ColName,row0,nRowRead)
                #if self.zero_flag: vis_all[flag_all==1]=0.
                #vis_all[np.isnan(vis_all)]=0.
                self.data=vis_all


        self.flag_all=flag_all
        self.uvw_dt=None


        if self.ReadUVWDT:
            print>>log,"Adding uvw speed info to main table: %s"%self.MSName
            tu=table(self.MSName,readonly=False,ack=False)
            if 'UVWDT' not in tu.colnames():
                self.AddUVW_dt()
            tu.close()
            del(tu)
            print>>log,"Reading uvw_dt column"
            tu=table(self.MSName,readonly=False,ack=False)
            self.uvw_dt=np.float64(tu.getcol('UVWDT', row0, nRowRead))
            tu.close()



        table_all.close()


        if self.RejectAutoCorr:
            indGetCorrelation=np.where(A0!=A1)[0]
            A0=A0[indGetCorrelation]
            A1=A1[indGetCorrelation]
            self.uvw=self.uvw[indGetCorrelation,:]
            time_all=time_all[indGetCorrelation]
            if self.swapped:
                self.data=self.data[:,indGetCorrelation,:]
                self.flag_all=self.flag_all[:,indGetCorrelation,:]
            else:
                self.data=self.data[indGetCorrelation,:,:]
                self.flag_all=self.flag_all[indGetCorrelation,:,:]
            self.nbl=(self.na*(self.na-1))/2

        if self.DoRevertChans:
            self.flag_all=self.flag_all[:,::-1,:]
            if not(type(self.data)==list):
                self.data=self.data[:,::-1,:]
            else:
                for icol in range(len(self.data)):
                    self.data[icol]=self.data[icol][:,::-1,:]


        self.times_all=time_all
        self.times=time_slots_all
        self.ntimes=time_slots_all.shape[0]
        self.nrows=time_all.shape[0]

        self.IndFlag=np.where(flag_all==True)
    
        #self.NPol=vis_all.shape[2]
        self.A0=A0
        self.A1=A1

            

        # DATA_CHUNK["uvw"]=self.uvw
        # DATA_CHUNK["data"]=self.data
        # DATA_CHUNK["flags"]=self.flag_all
        # DATA_CHUNK["A0"]=self.A0
        # DATA_CHUNK["A1"]=self.A1
        # DATA_CHUNK["TimeInterVal"]=self.TimeInterVal
        # return DATA_CHUNK

        
    def ToOrigFreqOrder(self,data):
        
        if self.DoRevertChans:
            d=data[:,::-1].copy()
            return d
        else:
            return data

    def SaveAllDataStruct(self):
        t=self.GiveMainTable()#table(self.MSName,ack=False,readonly=False)

        t.putcol('ANTENNA1',self.A0)
        t.putcol('ANTENNA2',self.A1)
        t.putcol("TIME",self.times_all)
        t.putcol("TIME_CENTROID",self.times_all)
        t.putcol("UVW",self.uvw)
        t.putcol("FLAG",self.flag_all)
        for icol in range(len(self.ColName)):
            t.putcol(self.ColName[icol],self.data[icol])
        t.close()

    def RemoveStation(self):
        
        DelStationList=self.DelStationList
        if DelStationList==None: return

        StationNames=self.StationNames
        self.MapStationsKeep=np.arange(len(StationNames))
        DelNumStationList=[]
        for Station in DelStationList:
            ind=np.where(Station==np.array(StationNames))[0]
            self.MapStationsKeep[ind]=-1
            DelNumStationList.append(ind)
            indRemove=np.where((self.A0!=ind)&(self.A1!=ind))[0]
            self.A0=self.A0[indRemove]
            self.A1=self.A1[indRemove]
            self.data=self.data[indRemove,:,:]
            self.flag_all=self.flag_all[indRemove,:,:]
            self.times_all=self.times_all[indRemove,:,:]
        self.MapStationsKeep=self.MapStationsKeep[self.MapStationsKeep!=-1]
        StationNames=(np.array(StationNames)[self.MapStationsKeep]).tolist()

        na=self.MapStationsKeep.shape[0]
        self.na=na
        self.StationPos=self.StationPos[self.MapStationsKeep,:]
        self.nbl=(na*(na-1))/2+na
        

    def ReadMSInfo(self,MSname,DoPrint=True):
        T=ClassTimeIt.ClassTimeIt()
        T.enableIncr()
        T.disable()
        #print MSname+'/ANTENNA'

        # open main table
        table_all=table(MSname,ack=False)

        #print MSname+'/ANTENNA'
        ta=table(table_all.getkeyword('ANTENNA'),ack=False)
        #ta=table(MSname+'::ANTENNA',ack=False)

        StationNames=ta.getcol('NAME')

        na=ta.getcol('POSITION').shape[0]
        self.StationPos=ta.getcol('POSITION')
        nbl=(na*(na-1))/2+na
        #nbl=(na*(na-1))/2
        ta.close()
        T.timeit()


        #table_all=table(MSname,ack=False)
        self.ColNames=table_all.colnames()
        TimeIntervals=table_all.getcol("INTERVAL")
        SPW=table_all.getcol('DATA_DESC_ID')
        if self.SelectSPW!=None:
            self.ListSPW=self.SelectSPW
            #print "dosel"
        else:
            self.ListSPW=sorted(list(set(SPW.tolist())))
        T.timeit()

        self.F_nrows=table_all.getcol("TIME").shape[0]
        F_time_all=table_all.getcol("TIME")[SPW==self.ListSPW[0]]

        self.F_A0=table_all.getcol("ANTENNA1")[SPW==self.ListSPW[0]]
        self.F_A1=table_all.getcol("ANTENNA2")[SPW==self.ListSPW[0]]

        #nbl=(np.where(F_time_all==F_time_all[0])[0]).shape[0]
        T.timeit()

        F_time_slots_all=np.array(sorted(list(set(F_time_all.tolist()))))
        F_ntimes=F_time_slots_all.shape[0]

        T.timeit()

        ta_spectral=table(table_all.getkeyword('SPECTRAL_WINDOW'),ack=False)
        reffreq=ta_spectral.getcol('REF_FREQUENCY')
        chan_freq=ta_spectral.getcol('CHAN_FREQ')
        self.dFreq=ta_spectral.getcol("CHAN_WIDTH").flatten()
        self.ChanWidth=ta_spectral.getcol('CHAN_WIDTH')
        if chan_freq.shape[0]>len(self.ListSPW):
            print ModColor.Str("  ====================== >> More SPW in headers, modifying that error....")
            chan_freq=chan_freq[np.array(self.ListSPW),:]
            reffreq=reffreq[np.array(self.ListSPW)]
            

        T.timeit()

        wavelength=299792456./reffreq
        NSPW=chan_freq.shape[0]
        self.ChanFreq=chan_freq
        self.Freq_Mean=np.mean(chan_freq)
        wavelength_chan=299792456./chan_freq

        if NSPW>1:
            print "Don't deal with multiple SPW yet"


        Nchan=wavelength_chan.shape[1]
        NSPWChan=NSPW*Nchan
        ta=table(table_all.getkeyword('FIELD'),ack=False)
        rarad,decrad=ta.getcol('PHASE_DIR')[self.Field][0]
        if rarad<0.: rarad+=2.*np.pi

        T.timeit()

        radeg=rarad*180./np.pi
        decdeg=decrad*180./np.pi
        ta.close()
         
        self.DoRevertChans=False
        if Nchan>1:
            self.DoRevertChans=(self.ChanFreq.flatten()[0]>self.ChanFreq.flatten()[-1])
        if self.DoRevertChans:
            print ModColor.Str("  ====================== >> Revert Channel order!")
            wavelength_chan=wavelength_chan[0,::-1]
            self.ChanFreq=self.ChanFreq[0,::-1]
            self.dFreq=np.abs(self.dFreq)

        T.timeit()
        table_all.close()

        self.na=na
        self.Nchan=Nchan
        self.NSPW=NSPW
        self.NSPWChan=NSPWChan
        self.F_tstart=F_time_all[0]
        self.F_times_all=F_time_all
        self.F_times=F_time_slots_all
        self.F_ntimes=F_time_slots_all.shape[0]
        
        self.dt=TimeIntervals[0]
        self.DTs=F_time_all[-1]-F_time_all[0]+self.dt
        self.DTh=self.DTs/3600.

        self.radec=(rarad,decrad)
        self.rarad=rarad
        self.decrad=decrad
        self.reffreq=reffreq
        self.StationNames=StationNames
        self.wavelength_chan=wavelength_chan
        self.rac=rarad
        self.decc=decrad
        self.nbl=nbl
        self.StrRA  = rad2hmsdms(self.rarad,Type="ra").replace(" ",":")
        self.StrDEC = rad2hmsdms(self.decrad,Type="dec").replace(" ",".")

        T.timeit()
        # self.StrRADEC=(rad2hmsdms(self.rarad,Type="ra").replace(" ",":")\
        #                ,rad2hmsdms(self.decrad,Type="dec").replace(" ","."))

    # def Give_dUVW_dt(self,ttVec,A0,A1):
    #     uvw0=self.Give_dUVW_dt0(np.mean(ttVec),A0,A1,LongitudeDeg=6.8689,R="UVW")
    #     uvw1=self.Give_dUVW_dt0(np.mean(ttVec)+30.,A0,A1,LongitudeDeg=6.8689,R="UVW")
    #     duvw0=uvw1-uvw0
    #     duvw1=30*self.Give_dUVW_dt0(np.mean(ttVec)+15.,A0,A1,LongitudeDeg=6.8689,R="UVW_dt")
    #     print duvw0-duvw1
    #     stop

    def Give_dUVW_dt(self,ttVec,A0,A1,LongitudeDeg=6.8689,R="UVW_dt"):

        # tt=self.times_all[0]
        # A0=self.A0[self.times_all==tt]
        # A1=self.A1[self.times_all==tt]
        # uvw=self.uvw[self.times_all==tt]


        tt=np.mean(ttVec)
        import sidereal
        import datetime
        ra,d=self.radec
        D=self.GiveDate(tt)
        Lon=LongitudeDeg*np.pi/180
        h= sidereal.raToHourAngle(ra,D,Lon)
        

        c=np.cos
        s=np.sin
        L=self.StationPos[A1]-self.StationPos[A0]

        if R=="UVW":
            R=np.array([[ s(h)      ,  c(h)      , 0.  ],
                        [-s(d)*c(h) ,  s(d)*s(h) , c(d)],
                        [ c(d)*c(h) , -c(d)*s(h) , s(d)]])
            UVW=np.dot(R,L.T).T
            import pylab
            pylab.clf()
            # pylab.subplot(1,2,1)
            # pylab.scatter(uvw[:,0],uvw[:,1],marker='.')
            #pylab.subplot(1,2,2)
            pylab.scatter(UVW[:,0],UVW[:,1],marker='.')
            pylab.draw()
            pylab.show(False)
            return UVW
        else:
        # stop
            K=2.*np.pi/(24.*3600)
            R_dt=np.array([[K*c(h)      , -K*s(h)     , 0.  ],
                           [K*s(d)*s(h) , K*s(d)*c(h) , 0.  ],
                           [-K*c(d)*s(h), -K*c(d)*c(h), 0.  ]])

            UVW_dt=np.dot(R_dt,L.T).T
            return np.float32(UVW_dt)






    def __str__(self):
        ll=[]
        ll.append(ModColor.Str(" MS PROPERTIES: "))
        ll.append("   - File Name: %s"%ModColor.Str(self.MSName,col="green"))
        ll.append("   - Column Name: %s"%ModColor.Str(str(self.ColName),col="green"))
        ll.append("   - Selection: %s"%( ModColor.Str(str(self.TaQL),col="green")))
        ll.append("   - Pointing center: (ra, dec)=(%s, %s) "%(rad2hmsdms(self.rarad,Type="ra").replace(" ",":")\
                                                               ,rad2hmsdms(self.decrad,Type="dec").replace(" ",".")))
        ll.append("   - Frequency = %s MHz"%str(self.reffreq/1e6))
        ll.append("   - Wavelength = %5.2f meters"%(np.mean(self.wavelength_chan)))
        ll.append("   - Time bin = %4.1f seconds"%(self.dt))
        ll.append("   - Total Integration time = %6.2f hours"%self.DTh)
        ll.append("   - Number of antenna  = %i"%self.na)
        ll.append("   - Number of baseline = %i"%self.nbl)
        ll.append("   - Number of SPW = %i"%self.NSPW)
        ll.append("   - Number of channels = %i"%self.Nchan)
        
        ss="\n".join(ll)+"\n"
        return ss

    def radec2lm_scalar(self,ra,dec):
        l = np.cos(dec) * np.sin(ra - self.rarad)
        m = np.sin(dec) * np.cos(self.decrad) - np.cos(dec) * np.sin(self.decrad) * np.cos(ra - self.rarad)
        return l,m

    def SaveVis(self,vis=None,Col="CORRECTED_DATA",spw=0,DoPrint=True):
        if vis==None:
            vis=self.data
        if DoPrint: print>>log, "Writting data in column %s"%ModColor.Str(Col,col="green")

        print "Givemain"
        table_all=self.GiveMainTable(readonly=False)

        if self.swapped:
            visout=np.swapaxes(vis[spw*self.Nchan:(spw+1)*self.Nchan],0,1)
            flag_all=np.swapaxes(self.flag_all[spw*self.Nchan:(spw+1)*self.Nchan],0,1)
        else:
            visout=vis
            flag_all=self.flag_all

        print "Col"
        table_all.putcol(Col,visout.astype(self.data.dtype),self.ROW0,self.nRowRead)
        print "Flag"
        table_all.putcol("FLAG",flag_all,self.ROW0,self.nRowRead)
        print "Weight"
        if self.HasWeights:
            
            table_all.putcol("WEIGHT",self.Weights,self.ROW0,self.nRowRead)
            #print "ok w"
        print "Close"
        table_all.close()
        
    def GiveUvwBL(self,a0,a1):
        vecout=self.uvw[(self.A0==a0)&(self.A1==a1),:]
        return vecout

    def GiveVisBL(self,a0,a1,col=0,pol=None):
        if self.multidata:
            vecout=self.data[col][(self.A0==a0)&(self.A1==a1),:,:]
        else:
            vecout=self.data[(self.A0==a0)&(self.A1==a1),:,:]
        if pol!=None:
            vecout=vecout[:,:,pol]
        return vecout

    def GiveVisBLChan(self,a0,a1,chan,pol=None):
        if pol==None:
            vecout=(self.data[(self.A0==a0)&(self.A1==a1),chan,0]+self.data[(self.A0==a0)&(self.A1==a1),chan,3])/2.
        else:
            vecout=self.data[(self.A0==a0)&(self.A1==a1),chan,pol]
        return vecout

    def plotBL(self,a0,a1,pol=0):
        
        import pylab
        if self.multidata:
            vis0=self.GiveVisBL(a0,a1,col=0,pol=pol)
            vis1=self.GiveVisBL(a0,a1,col=1,pol=pol)
            pylab.clf()
            pylab.subplot(2,1,1)
            #pylab.plot(vis0.real)
            pylab.plot(np.abs(vis0))
            #pylab.subplot(2,1,2)
            #pylab.plot(vis1.real)
            pylab.plot(np.abs(vis1),ls=":")
            pylab.title("%i-%i"%(a0,a1))
            #pylab.plot(vis1.real-vis0.real)
            pylab.subplot(2,1,2)
            pylab.plot(np.angle(vis0))
            pylab.plot(np.angle(vis1),ls=":")
            pylab.draw()
            pylab.show()
        else:
            pylab.clf()
            vis=self.GiveVisBL(a0,a1,col=0,pol=pol)
            pylab.subplot(2,1,1)
            pylab.plot(np.abs(vis))
            #pylab.plot(np.real(vis))
            pylab.subplot(2,1,2)
            pylab.plot(np.angle(vis))
            #pylab.plot(np.imag(vis))
            pylab.draw()
            pylab.show()

    def GiveCol(self,ColName):
        t=self.GiveMainTable()
        col=t.getcol(ColName)
        t.close()
        return col

    def PutColInData(self,SpwChan,pol,data):
        if self.swapped:
            self.data[SpwChan,:,pol]=data
        else:
            self.data[:,SpwChan,pol]=data

    def Restore(self):
        backname="CORRECTED_DATA_BACKUP"
        backnameFlag="FLAG_BACKUP"
        t=table(self.MSName,readonly=False,ack=False)
        if backname in t.colnames():
            print>>log, "  Copying ",backname," to CORRECTED_DATA"
            #t.putcol("CORRECTED_DATA",t.getcol(backname))
            self.CopyCol(backname,"CORRECTED_DATA")
            print>>log, "  Copying ",backnameFlag," to FLAG"
            self.CopyCol(backnameFlag,"FLAG")
            #t.putcol(,t.getcol(backnameFlag))
        t.close()

    def ZeroFlagSave(self,spw=0):
        self.flag_all.fill(0)
        if self.swapped:
            flagout=np.swapaxes(self.flag_all[spw*self.Nchan:(spw+1)*self.Nchan],0,1)
        else:
            flagout=self.flag_all
        t=table(self.MSName,readonly=False,ack=False)
        t.putcol("FLAG",flagout)
        
        t.close()

    def CopyCol(self,Colin,Colout):
        t=table(self.MSName,readonly=False,ack=False)
        if self.TimeChunkSize==None:
            print>>log, "  ... Copying column %s to %s"%(Colin,Colout)
            t.putcol(Colout,t.getcol(Colin))
        else:
            print>>log, "  ... Copying column %s to %s"%(Colin,Colout)
            TimesInt=np.arange(0,self.DTh,self.TimeChunkSize).tolist()
            if not(self.DTh in TimesInt): TimesInt.append(self.DTh)

            RowsChunk=int(self.TimeChunkSize*3600/self.dt)*self.nbl
            NChunk=np.max([2,int(self.DTh/self.TimeChunkSize)])
            Rows=(np.int64(np.linspace(0,self.F_nrows,NChunk))).tolist()

            for i in range(len(Rows)-1):
                #t0,t1=TimesInt[i],TimesInt[i+1]
                #t0=t0*3600.+self.F_tstart
                #t1=t1*3600.+self.F_tstart
                #ind0=np.argmin(np.abs(t0-self.F_times))
                #ind1=np.argmin(np.abs(t1-self.F_times))
                row0=Rows[i]#ind0*self.nbl
                row1=Rows[i+1]#ind1*self.nbl
                print>>log, "      ... Copy in [%i, %i] rows"%( row0,row1)
                NRow=row1-row0
                t.putcol(Colout,t.getcol(Colin,row0,NRow),row0,NRow)
        t.close()

    def AddCol(self,ColName,LikeCol="DATA",ColDesc=None,ColDescDict=None):
        t=table(self.MSName,readonly=False,ack=False)
        if (ColName in t.colnames()):
            print>>log, "  Column %s already in %s"%(ColName,self.MSName)
            t.close()
            return
        print>>log, "  Putting column %s in %s"%(ColName,self.MSName)
        if ColDesc is None:
            desc=t.getcoldesc(LikeCol)
            desc["name"]=ColName
            desc['comment']=desc['comment'].replace(" ","_")
        # elif ColDescDict:
        #     desc=ColDescDict
        #     desc'shape': np.array([self.Nchan], dtype=int32)
        elif ColDesc=="IMAGING_WEIGHT":
            desc={'_c_order': True,
                  'comment': '',
                  "name": ColName,
                  'dataManagerGroup': 'imagingweight',
                  'dataManagerType': 'TiledShapeStMan',
                  'maxlen': 0,
                  'ndim': 1,
                  'option': 4,
                  'shape': np.array([self.Nchan], dtype=np.int32),
                  'valueType': 'float'}
        else:
            print "Not supported"
        t.addcols(desc)
        t.close()
        
    def PutBackupCol(self,incol="CORRECTED_DATA"):
        backname="%s_BACKUP"%incol
        backnameFlag="FLAG_BACKUP"
        self.PutCasaCols()
        t=table(self.MSName,readonly=False,ack=False)
        JustAdded=False
        if not(backname in t.colnames()):
            print>>log, "  Putting column ",backname," in MS"
            desc=t.getcoldesc("CORRECTED_DATA")
            desc["name"]=backname
            desc['comment']=desc['comment'].replace(" ","_")
            t.addcols(desc)
            print>>log, "  Copying %s in %s"%(incol,backname)
            self.CopyCol(incol,backname)
        else:
            print>>log, "  Column %s already there"%(backname)

        if not(backnameFlag in t.colnames()):
            desc=t.getcoldesc("FLAG")
            desc["name"]=backnameFlag
            desc['comment']=desc['comment'].replace(" ","_")
            t.addcols(desc)
            self.CopyCol("FLAG",backnameFlag)

            JustAdded=True

        t.close()
        return JustAdded

    def PutNewCol(self,Name,LikeCol="CORRECTED_DATA"):
        if not(Name in self.ColNames):
            print>>log, "  Putting column %s in MS, with format of %s"%(Name,LikeCol)
            t=table(self.MSName,readonly=False,ack=False)
            desc=t.getcoldesc(LikeCol)
            desc["name"]=Name
            t.addcols(desc) 
            t.close()
    
    def RotateMS(self,radec):
        import ModRotate
        ModRotate.Rotate(self,radec)
        ta=table(self.MSName+'::FIELD',ack=False,readonly=False)
        ra,dec=radec
        radec=np.array([[[ra,dec]]])
        ta.putcol("DELAY_DIR",radec)
        ta.putcol("PHASE_DIR",radec)
        ta.putcol("REFERENCE_DIR",radec)
        ta.close()
        t=table(self.MSName,ack=False,readonly=False)
        t.putcol(self.ColName,self.data)
        t.putcol("UVW",self.uvw)
        t.close()
    
    def PutCasaCols(self):
        import pyrap.tables
        pyrap.tables.addImagingColumns(self.MSName,ack=False)
        #self.PutNewCol("CORRECTED_DATA")
        #self.PutNewCol("MODEL_DATA")

    def AddUVW_dt(self):
        print>>log,"Compute UVW speed column"
        MSName=self.MSName
        MS=self
        t=table(MSName,readonly=False,ack=False)
        times=t.getcol("TIME")
        A0=t.getcol("ANTENNA1")
        A1=t.getcol("ANTENNA2")
        UVW=t.getcol("UVW")
        UVW_dt=np.zeros_like(UVW)
        if "UVWDT" not in t.colnames():
            print>>log,"Adding column UVWDT in %s"%self.MSName
            desc=t.getcoldesc("UVW")
            desc["name"]="UVWDT"
            desc['comment']=desc['comment'].replace(" ","_")
            t.addcols(desc)
        
        # # #######################
        # LTimes=np.sort(np.unique(times))
        # for iTime,ThisTime in enumerate(LTimes):
        #     print iTime,LTimes.size
        #     ind=np.where(times==ThisTime)[0]
        #     UVW_dt[ind]=MS.Give_dUVW_dt(times[ind],A0[ind],A1[ind])
        # # #######################
        
        na=MS.na
        pBAR= ProgressBar('white', width=50, block='=', empty=' ',Title=" Calc dUVW/dt ", HeaderSize=10,TitleSize=13)
        pBAR.render(0, '%4i/%i' % (0,na))
        for ant0 in range(na):
            for ant1 in range(ant0,MS.na):
                if ant0==ant1: continue
                C0=((A0==ant0)&(A1==ant1))
                C1=((A1==ant0)&(A0==ant1))
                ind=np.where(C0|C1)[0]
                UVWs=UVW[ind]
                timess=times[ind]
                dtimess=timess[1::]-timess[0:-1]
                UVWs_dt0=(UVWs[1::]-UVWs[0:-1])/dtimess.reshape((-1,1))
                UVW_dt[ind[0:-1]]=UVWs_dt0
                UVW_dt[ind[-1]]=UVWs_dt0[-1]
            intPercent = int(100 * (ant0+1) / float(na))
            pBAR.render(intPercent, '%4i/%i' % (ant0+1, na))
                    
    
        print>>log,"Writting in column UVWDT"
        t.putcol("UVWDT",UVW_dt)
        t.close()
    
        # import pylab
        # u,v,w=t.getcol("UVW").T
        # A0=t.getcol("ANTENNA1")
        # A1=t.getcol("ANTENNA2")
        # ind=np.where((A0==0)&(A1==10))[0]
        # us=u[ind]
        # du,dv,dw=t.getcol("UVWDT").T
        # dus1=du[ind]
        # dus0=us[1::]-us[0:-1]
        # pylab.show()
        # DT=t.getcol("INTERVAL")[0]
        # pylab.plot(dus0/DT)
        # pylab.plot(dus1)
        # pylab.show()
    
