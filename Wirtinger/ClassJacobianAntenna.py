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
from killMS.Array import NpShared
from killMS.Predict.PredictGaussPoints_NumExpr5 import ClassPredict
import os
from killMS.Data import ClassVisServer
#from Sky import ClassSM
from killMS.Array import ModLinAlg
from killMS.Other import ClassTimeIt
from killMS.Array.Dot import NpDotSSE

def testLM():
    import pylab
    SM=ClassSM.ClassSM("../TEST/ModelRandom00.txt.npy")
    rabeam,decbeam=SM.ClusterCat.ra,SM.ClusterCat.dec
    LofarBeam=("AE",5,rabeam,decbeam)
    VS=ClassVisServer.ClassVisServer("../TEST/0000.MS/")#,LofarBeam=LofarBeam)
    MS=VS.MS
    SM.Calc_LM(MS.rac,MS.decc)



    nd=SM.NDir
    npol=4
    na=MS.na
    Gains=np.zeros((na,nd,npol),dtype=np.complex64)
    Gains[:,:,0]=1
    Gains[:,:,-1]=1
    #Gains+=(np.random.randn(*Gains.shape)*0.5+1j*np.random.randn(*Gains.shape)
    #Gains=np.random.randn(*Gains.shape)+1j*np.random.randn(*Gains.shape)
    #GainsOrig=Gains.copy()
    ###############
    #GainsOrig=np.load("Rand.npz")["GainsOrig"]
    #Gains*=1e-3
    #Gains[:,0,:]=GainsOrig[:,0,:]
    ###############

    PolMode="IFull"
    # ### Scalar gains
    # PolMode="Scalar"
    # g=np.random.randn(*(Gains[:,:,0].shape))+1j*np.random.randn(*(Gains[:,:,0].shape))
    # g=g.reshape((na,nd,1))
    # Gains*=g
    # ####
    
    #Gains[:,2,:]=0
    #Gains[:,1,:]=0
    
    #Gains[:,1::,:]=0
    


    DATA=VS.GiveNextVis()


    # Apply Jones
    PM=ClassPredict(Precision="S")
    #DATA["data"]=PM.predictKernelPolCluster(DATA,SM,ApplyJones=Gains)
    
    ############################
    iAnt=0
    JM=ClassJacobianAntenna(SM,iAnt,PolMode=PolMode)
    JM.setDATA(DATA)
    JM.CalcKernelMatrix()

    if PolMode=="Scalar":
        Gains=Gains[:,:,0].reshape((na,nd,1))
        G=Gains.copy().reshape((na,nd,1,1))
    else:
        G=Gains.copy().reshape((na,nd,2,2))
        

    y=JM.GiveDataVec()
    xtrue=JM.GiveSubVecGainAnt(Gains).flatten()
    x=Gains
    #################
    Radd=np.random.randn(*(G[iAnt].shape))#*0.3
    #np.savez("Rand",Radd=Radd,GainsOrig=GainsOrig)
    #################
    #Radd=np.load("Rand.npz")["Radd"]

    G[iAnt]+=Radd


    print "start"
    for i in range(10):
        xbef=G[iAnt].copy()
        x=JM.doLMStep(G)
        G[iAnt]=x
        
        pylab.figure(1)
        pylab.clf()
        pylab.plot(np.abs(xtrue.flatten()))
        pylab.plot(np.abs(x.flatten()))
        pylab.plot(np.abs(xtrue.flatten())-np.abs(x.flatten()))
        pylab.plot(np.abs(xbef.flatten()))
        pylab.ylim(-2,2)
        pylab.draw()
        pylab.show(False)

        # pylab.figure(3)
        # pylab.clf()
        # pylab.subplot(1,3,1)
        # pylab.imshow(np.abs(JM.Jacob)[0:20],interpolation="nearest")
        # pylab.subplot(1,3,2)
        # pylab.imshow(np.abs(JM.JHJ),interpolation="nearest")
        # pylab.subplot(1,3,3)
        # pylab.imshow(np.abs(JM.JHJinv),interpolation="nearest")
        # pylab.draw()
        # pylab.show(False)

    stop    
    



class ClassJacobianAntenna():
    def __init__(self,SM,iAnt,PolMode="IFull",Precision="S",PrecisionDot="D",IdSharedMem="",
                 PM=None,GD=None,NChanSols=1,ChanSel=None,
                 SharedDicoDescriptors=None,
                 **kwargs):
        T=ClassTimeIt.ClassTimeIt("  InitClassJacobianAntenna")
        T.disable()

        self.ChanSel=ChanSel
        self.SharedDicoDescriptors=SharedDicoDescriptors
        self.GD=GD
        self.IdSharedMem=IdSharedMem
        self.PolMode=PolMode
        #self.PM=ClassPredict(Precision="S")
        self.Rinv_flat=None
        for key in kwargs.keys():
            setattr(self,key,kwargs[key])
        self.PM=PM
        self.SM=SM
        T.timeit("Init0")
        if PM==None:
            self.PM=ClassPredict(Precision=Precision,
                                 DoSmearing=self.DoSmearing,
                                 IdMemShared=IdSharedMem)
            
            if self.GD["ImageSkyModel"]["BaseImageName"]!="":
                self.PM.InitGM(self.SM)

        T.timeit("PM")
        if PrecisionDot=="D":
            self.CType=np.complex128
            self.FType=np.float64

        if PrecisionDot=="S":
            self.CType=np.complex64
            self.FType=np.float32

        self.CType=np.complex128
        self.TypeDot="Numpy"
        #self.TypeDot="SSE"

        self.iAnt=int(iAnt)
        self.SharedDataDicoName="%sDicoData.%2.2i"%(self.IdSharedMem,self.iAnt)
        self.NChanSols=NChanSols
        
        if self.PolMode=="IFull":
            self.NJacobBlocks_X=2
            self.NJacobBlocks_Y=2
            self.npolData=4
        
        elif self.PolMode=="Scalar":
            self.NJacobBlocks_X=1
            self.NJacobBlocks_Y=1
            self.npolData=1
        
        elif self.PolMode=="IDiag":
            self.NJacobBlocks_X=2
            self.NJacobBlocks_Y=1
            self.npolData=2
        

        self.Reinit()
        T.timeit("rest")

    def Reinit(self):
        self.HasKernelMatrix=False
        self.LQxInv=None

    def GiveSubVecGainAnt(self,GainsIn):
        # if (GainsIn.size==self.NDir*2*2): return GainsIn.copy()
        Gains=GainsIn.copy().reshape((self.na,self.NDir,self.NJacobBlocks_X,self.NJacobBlocks_Y))[self.iAnt]
        return Gains
        
    def setDATA(self,DATA):
        self.DATA=DATA
        
    def setDATA_Shared(self):
        # SharedNames=["SharedVis.freqs","SharedVis.times","SharedVis.A1","SharedVis.A0","SharedVis.flags","SharedVis.infos","SharedVis.uvw","SharedVis.data"]
        # self.DATA={}
        # for SharedName in SharedNames:
        #     key=SharedNames.split(".")[1]
        #     self.DATA[key]=NpShared.GiveArray(SharedName)

        T=ClassTimeIt.ClassTimeIt("  setDATA_Shared")
        T.disable()
        
        #self.DATA=NpShared.SharedToDico("%sSharedVis"%self.IdSharedMem)
        self.DATA=NpShared.SharedObjectToDico(self.SharedDicoDescriptors["SharedVis"])



        _,self.NChanMS,_=self.DATA["data"].shape
        if self.ChanSel==None:
            self.ch0=0
            self.ch1=self.NChanMS
        else:
            self.ch0,self.ch1=self.ChanSel

        
        self.NChanData=self.ch1-self.ch0

        T.timeit("SharedToDico0")
        #DicoBeam=NpShared.SharedToDico("%sPreApplyJones"%self.IdSharedMem)
        DicoBeam=NpShared.SharedObjectToDico(self.SharedDicoDescriptors["PreApplyJones"])
        
        T.timeit("SharedToDico1")
        if DicoBeam!=None:
            self.DATA["DicoPreApplyJones"]=DicoBeam
            # self.DATA["DicoClusterDirs"]=NpShared.SharedToDico("%sDicoClusterDirs"%self.IdSharedMem)
            self.DATA["DicoClusterDirs"]=NpShared.SharedObjectToDico(self.SharedDicoDescriptors["DicoClusterDirs"])


        T.timeit("SharedToDico2")


        #self.DATA["UVW_RefAnt"]=NpShared.GiveArray("%sUVW_RefAnt"%self.IdSharedMem)



           
            

                                        
    def JHJinv_x(self,Gains):
        G=[]
        #nd,_,_=Gains.shape
        Gains=Gains.reshape((self.NDir,self.NJacobBlocks_X,self.NJacobBlocks_Y))
        for polIndex in range(self.NJacobBlocks_X):
            Gain=Gains[:,polIndex,:]
            #print "JHJinv_x: %i %s . %s "%(polIndex,str(self.L_JHJinv[polIndex].shape),str(Gain.flatten().shape))
            Vec=np.dot(self.L_JHJinv[polIndex],Gain.flatten())
            Vec=Vec.reshape((self.NDir,1,self.NJacobBlocks_Y))
            G.append(Vec)
            
        Gout=np.concatenate(G,axis=1)
        #print "JHJinv_x: Gout %s "%(str(Gout.shape))
        
        return Gout.flatten()



    def Msq_x(self,LM,Gains):
        G=[]
        Gains=Gains.reshape((self.NDir,self.NJacobBlocks_X,self.NJacobBlocks_Y))
        for polIndex in range(self.NJacobBlocks_X):
            Gain=Gains[:,polIndex,:]
            #print "Msq_x: %i %s . %s"%(polIndex,str(LM[polIndex].shape),str(Gain.flatten().shape))
            Vec=np.dot(LM[polIndex],Gain.flatten())
            Vec=Vec.reshape((self.NDir,1,self.NJacobBlocks_Y))
            G.append(Vec)
            
        Gout=np.concatenate(G,axis=1)
        #print "Msq_x: Gout %s "%(str(Gout.shape))
        
        return Gout.flatten()




    def JH_z(self,zin):
        #z=zin.reshape((self.NJacobBlocks,zin.size/self.NJacobBlocks))
        #z=zin.reshape((1,zin.size))
        Gains=np.zeros((self.NDir,self.NJacobBlocks_X,self.NJacobBlocks_Y),self.CType)
        for polIndex in range(self.NJacobBlocks_X):
            Jacob=self.LJacob[polIndex]
            
            flags=self.DicoData["flags_flat"][polIndex]
            ThisZ=zin[polIndex][flags==0]#self.DicoData["flags_flat"[polIndex]
            
            J=Jacob[flags==0]


            ThisZ=ThisZ.flatten()

            if self.TypeDot=="Numpy":
                Gain=np.dot(J.T.conj(),ThisZ)
            elif self.TypeDot=="SSE":
                ThisZ=ThisZ.reshape((1,ThisZ.size))
                JTc=self.LJacobTc[polIndex]#.copy()
                Gain=NpDotSSE.dot_A_BT(JTc,ThisZ)


            Gains[:,polIndex,:]=Gain.reshape((self.NDir,self.NJacobBlocks_Y))

        return Gains

    # def GiveDataVec(self):
    #     y=[]
    #     yf=[]
    #     for polIndex in range(self.NJacobBlocks):
    #         DataVec=self.DicoData["data"][:,:,polIndex,:].flatten()
    #         Flags=self.DicoData["flags"][:,:,polIndex,:].flatten()

    #         y.append(DataVec)
    #         yf.append(Flags)

    #     y=np.concatenate(y)
    #     yf=np.concatenate(yf)
    #     return y,yf


    def J_x(self,Gains):
        z=[]
        Gains=Gains.reshape((self.NDir,self.NJacobBlocks_X,self.NJacobBlocks_Y))
        for polIndex in range(self.NJacobBlocks_X):
            Jacob=self.LJacob[polIndex]
            
            Gain=Gains[:,polIndex,:].flatten()

            #flags=self.DicoData["flags_flat"][polIndex]
            J=Jacob#[flags==0]
            # print J.shape, Gain.shape

            # # Numpy

            if self.TypeDot=="Numpy":
                Z=np.dot(J,Gain)
            elif self.TypeDot=="SSE":
                Gain=Gain.reshape((1,Gain.size))
                Z=NpDotSSE.dot_A_BT(J,Gain).ravel()

            z.append(Z)



        z=np.array(z)
        return z

    def PredictOrigFormat(self,GainsIn):
        if self.GD["VisData"]["FreePredictGainColName"]!=None:
            self.PredictOrigFormat_Type(GainsIn,Type="Gains")
        if self.GD["VisData"]["FreePredictColName"]!=None:
            self.PredictOrigFormat_Type(GainsIn,Type="NoGains")


    def PredictOrigFormat_Type(self,GainsIn,Type="Gains"):
        #print "    COMPUTE PredictOrigFormat"
        Gains=GainsIn.copy()
        na,nd,_,_=Gains.shape
        #Type="NoGains"
        if Type=="NoGains":
            if self.PolMode=="Scalar":
                Gains=np.ones((na,nd,1,1),np.complex64)
            elif self.PolMode=="IDiag":
                Gains=np.ones((na,nd,2,1),np.complex64)
            else:
                Gains=np.zeros((na,nd,2,2),np.complex64)
                Gains[:,:,0,0]=1
                Gains[:,:,1,1]=1
            NameShmData="%sPredictedData"%self.IdSharedMem
            NameShmIndices="%sIndicesData"%self.IdSharedMem
        elif Type=="Gains":
            NameShmData="%sPredictedDataGains"%self.IdSharedMem
            NameShmIndices="%sIndicesDataGains"%self.IdSharedMem
        
            
        PredictedData=NpShared.GiveArray(NameShmData)
        Indices=NpShared.GiveArray(NameShmIndices)

        Ga=self.GiveSubVecGainAnt(Gains).copy()

        self.CalcJacobianAntenna(Gains)
        #self.PrepareJHJ_LM()
        zp=self.J_x(Ga)#self.DicoData["data_flat"]#
        DicoData=self.DicoData

        nr,nch,_,_=DicoData["flags"].shape
            
        indRowsThisChunk=self.DATA["indRowsThisChunk"]
        indOrig=DicoData["indOrig"]
        indThis=np.arange(DicoData["indOrig"].size)

        IndicesSel0=Indices[indRowsThisChunk,:,:][indOrig,self.ch0:self.ch1,0].ravel()
        IndicesSel1=Indices[indRowsThisChunk,:,:][indOrig,self.ch0:self.ch1,1].ravel()
        IndicesSel2=Indices[indRowsThisChunk,:,:][indOrig,self.ch0:self.ch1,2].ravel()
        IndicesSel3=Indices[indRowsThisChunk,:,:][indOrig,self.ch0:self.ch1,3].ravel()
        
        D=np.rollaxis(zp.reshape(self.NJacobBlocks_X,nr,nch,self.NJacobBlocks_Y),0,3).reshape(nr,nch,self.NJacobBlocks_X,self.NJacobBlocks_Y)

        if self.PolMode=="Scalar":
            # PredictedData.ravel()[IndicesSel0]=D[indThis,:,0,0].ravel()
            PredictedData.flat[IndicesSel0]=D[indThis,:,0,0].ravel()
            PredictedData.flat[IndicesSel3]=D[indThis,:,0,0].ravel()
        elif self.PolMode=="IDiag":
            PredictedData.flat[IndicesSel0]=D[indThis,:,0,0].ravel()
            PredictedData.flat[IndicesSel3]=D[indThis,:,1,0].ravel()
        elif self.PolMode=="IFull":
            PredictedData.flat[IndicesSel0]=D[indThis,:,0,0].ravel()
            PredictedData.flat[IndicesSel1]=D[indThis,:,0,1].ravel()
            PredictedData.flat[IndicesSel2]=D[indThis,:,1,0].ravel()
            PredictedData.flat[IndicesSel3]=D[indThis,:,1,1].ravel()


        # d0=self.DATA["data"]#[indOrig,:,0]
        # #d1=D[indThis,:,0,0]
        # d2=PredictedData[indRowsThisChunk,:,:]#[indOrig,:,0]

        # pylab.clf()
        # pylab.plot(d0[:,2,0].real)
        # # pylab.plot(d1[:,2,0].real)
        # pylab.plot(d2[:,2,0].real)
        # pylab.plot((d0-d2)[:,2,0].real)
        # pylab.draw()
        # pylab.show(False)
        # pylab.pause(0.1)
        # # stop




    def CalcJacobianAntenna(self,GainsIn):
        if not(self.HasKernelMatrix): stop
        iAnt=self.iAnt
        NDir=self.NDir
        n4vis=self.n4vis
        #print "n4vis",n4vis
        na=self.na
        #print GainsIn.shape,na,NDir,self.NJacobBlocks,self.NJacobBlocks
        Gains=GainsIn.reshape((na,NDir,self.NJacobBlocks_X,self.NJacobBlocks_Y))
        Jacob=np.zeros((n4vis,self.NJacobBlocks_Y,NDir,self.NJacobBlocks_Y),self.CType)

        if (self.PolMode=="IFull")|(self.PolMode=="Scalar"):
            self.LJacob=[Jacob]*self.NJacobBlocks_X
        elif self.PolMode=="IDiag":
            self.LJacob=[Jacob,Jacob.copy()]
        LJacob=self.LJacob
        
        for iDir in range(NDir):
            G=Gains[self.A1,iDir].conj()

            K_XX=self.K_XX[iDir]
            K_YY=self.K_YY[iDir]

            nr=G.shape[0]

            if self.PolMode=="Scalar":
                J0=Jacob[:,0,iDir,0]
                g0_conj=G[:,0,0].reshape((nr,1))
                J0[:]=(g0_conj*K_XX).reshape((K_XX.size,))

            
            elif self.PolMode=="IFull":
                J0=Jacob[:,0,iDir,0]
                g0_conj=G[:,0,0].reshape((nr,1))
                J0[:]=(g0_conj*K_XX).reshape((K_XX.size,))

                J1=Jacob[:,0,iDir,1]
                J2=Jacob[:,1,iDir,0]
                J3=Jacob[:,1,iDir,1]
                g1_conj=G[:,1,0].reshape((nr,1))
                g2_conj=G[:,0,1].reshape((nr,1))
                g3_conj=G[:,1,1].reshape((nr,1))

                J1[:]=(g2_conj*K_YY).reshape((K_XX.size,))
                J2[:]=(g1_conj*K_XX).reshape((K_XX.size,))
                J3[:]=(g3_conj*K_YY).reshape((K_XX.size,))

            elif self.PolMode=="IDiag":
                J0=LJacob[0][:,0,iDir,0]
                g0_conj=G[:,0,0].reshape((nr,1))
                J0[:]=(g0_conj*K_XX).reshape((K_XX.size,))

                J1=LJacob[1][:,0,iDir,0]
                g1_conj=G[:,1,0].reshape((nr,1))
                J1[:]=(g1_conj*K_YY).reshape((K_XX.size,))


        for J in LJacob:
            J.shape=(n4vis*self.NJacobBlocks_Y,NDir*self.NJacobBlocks_Y)


        self.LJacobTc=[]
        for polIndex in range(self.NJacobBlocks_X):
            flags=self.DicoData["flags_flat"][polIndex]
            J=self.LJacob[polIndex][flags==0]
            self.LJacobTc.append(J.T.conj().copy())

        self.L_JHJ=[]
        for polIndex in range(self.NJacobBlocks_X):
            flags=self.DicoData["flags_flat"][polIndex]
            J=self.LJacob[polIndex][flags==0]
            nrow,_=J.shape
            self.nrow_nonflagged=nrow
            JH=J.T.conj()
            if type(self.Rinv_flat)!=type(None):
                Rinv=self.Rinv_flat[polIndex][flags==0].reshape((nrow,1))

                if self.TypeDot=="Numpy":
                    JHJ=np.dot(J.T.conj(),Rinv*J)
                elif self.TypeDot=="SSE":
                    RinvJ_T=(Rinv*J).T.copy()
                    JTc=self.LJacobTc[polIndex]#.copy()
                    JHJ=NpDotSSE.dot_A_BT(JTc,RinvJ_T)

            else:
                if self.TypeDot=="Numpy":
                    JHJ=np.dot(J.T.conj(),J)
                elif self.TypeDot=="SSE":
                    J_T=J.T.copy()
                    JTc=self.LJacobTc[polIndex]#.copy()
                    JHJ=NpDotSSE.dot_A_BT(JTc,J_T)
                

            self.L_JHJ.append(self.CType(JHJ))


        # self.JHJinv=np.linalg.inv(self.JHJ)
        # self.JHJinv=np.diag(np.diag(self.JHJinv))

    def CalcKernelMatrix(self,rms=0.):
        # Out[28]: ['freqs', 'times', 'A1', 'A0', 'flags', 'uvw', 'data']
        T=ClassTimeIt.ClassTimeIt("CalcKernelMatrix Ant=%i"%self.iAnt)
        T.disable()
        DATA=self.DATA
        iAnt=self.iAnt
        na=int(DATA['infos'][0])
        self.na=na
        NDir=self.SM.NDir
        self.NDir=NDir
        self.iAnt=iAnt



        T.timeit("stuff")
        
        self.DicoData=self.GiveData(DATA,iAnt,rms=rms)

        T.timeit("data")
        # self.Data=self.DicoData["data"]
        self.A1=self.DicoData["A1"]
        # print "AntMax1",self.SharedDataDicoName,np.max(self.A1)
        # print self.DicoData["A1"]
        # print "AntMax0",self.SharedDataDicoName,np.max(self.DicoData["A0"])
        # print self.DicoData["A0"]
        nrows,nchan,_,_=self.DicoData["flags"].shape
        n4vis=nrows*nchan
        self.n4vis=n4vis
        
        KernelSharedName="%sKernelMat.%2.2i"%(self.IdSharedMem,self.iAnt)
        self.KernelMat_AllChan=NpShared.GiveArray(KernelSharedName)

        if type(self.KernelMat_AllChan)!=type(None):
            self.HasKernelMatrix=True
            if self.PolMode=="IFull":
                self.K_XX_AllChan=self.KernelMat_AllChan[0]
                self.K_YY_AllChan=self.KernelMat_AllChan[1]
                self.NJacobBlocks_X=2
                self.NJacobBlocks_Y=2
            elif self.PolMode=="Scalar":
                #n4vis=self.DicoData["data_flat"].size
                self.K_XX_AllChan=self.KernelMat_AllChan[0]
                self.K_YY_AllChan=self.K_XX_AllChan
                #self.n4vis=n4vis
                self.NJacobBlocks_X=1
                self.NJacobBlocks_Y=1
            elif self.PolMode=="IDiag":
                #n4vis=self.DicoData["data_flat"].size
                self.K_XX_AllChan=self.KernelMat_AllChan[0]
                self.K_YY_AllChan=self.KernelMat_AllChan[1]
                #self.n4vis=n4vis
                self.NJacobBlocks_X=2
                self.NJacobBlocks_Y=1
            # self.Data=self.Data.reshape((nrows,nchan,self.NJacobBlocks,self.NJacobBlocks))

            #print "Kernel From shared"
            return
        else:
            #print "    COMPUTE KERNEL"
            pass

        T.timeit("stuff 2")
        # GiveArray(Name)
        nchan_AllChan=self.DicoData["freqs_full"].size
        n4vis_AllChan=nrows*nchan_AllChan
        self.n4vis_AllChan=n4vis_AllChan
            
        if self.PolMode=="IFull":
            #self.K_XX=np.zeros((NDir,n4vis/nchan,nchan),np.complex64)
            #self.K_YY=np.zeros((NDir,n4vis/nchan,nchan),np.complex64)
            self.KernelMat_AllChan=NpShared.zeros(KernelSharedName,(2,NDir,n4vis_AllChan/nchan_AllChan,nchan_AllChan),dtype=self.CType)
            self.K_XX_AllChan=self.KernelMat_AllChan[0]
            self.K_YY_AllChan=self.KernelMat_AllChan[1]
            # KernelMatrix=NpShared.zeros(KernelSharedName,(n4vis,NDir,2),dtype=np.complex64)
            self.NJacobBlocks_X=2
            self.NJacobBlocks_Y=2
        elif self.PolMode=="Scalar":
            #n4vis=self.Data.size
            # KernelMatrix_XX=np.zeros((NDir,n4vis,nchan),np.complex64)
            # KernelMatrix=NpShared.zeros(KernelSharedName,(n4vis,NDir,1),dtype=np.complex64)
            self.KernelMat_AllChan=NpShared.zeros(KernelSharedName,(1,NDir,n4vis_AllChan/nchan_AllChan,nchan_AllChan),dtype=self.CType)
            self.K_XX_AllChan=self.KernelMat_AllChan[0]
            self.K_YY_AllChan=self.K_XX_AllChan
            self.NJacobBlocks_X=1
            self.NJacobBlocks_Y=1
        elif self.PolMode=="IDiag":
            self.KernelMat_AllChan=NpShared.zeros(KernelSharedName,(2,NDir,n4vis_AllChan/nchan_AllChan,nchan_AllChan),dtype=self.CType)
            self.K_XX_AllChan=self.KernelMat_AllChan[0]
            self.K_YY_AllChan=self.KernelMat_AllChan[1]
            self.NJacobBlocks_X=2
            self.NJacobBlocks_Y=1
        T.timeit("stuff 3")
            
        #self.Data=self.Data.reshape((nrows,nchan,self.NJacobBlocks,self.NJacobBlocks))

        #self.K_XX=[]
        #self.K_YY=[]

        ApplyTimeJones=None
        #print self.DicoData.keys()
        if "DicoPreApplyJones" in self.DicoData.keys():
            ApplyTimeJones=self.DicoData["DicoPreApplyJones"]

        #import gc
        #gc.enable()
        # gc.set_debug(gc.DEBUG_LEAK)


        # ##############################################
        # from SkyModel.Sky import ClassSM
        # SM=ClassSM.ClassSM("ModelImage.txt.npy")
        # SM.Type="Catalog"
        # SM.Calc_LM(self.SM.rac,self.SM.decc)
        # self.KernelMat1=np.zeros((1,NDir,n4vis/nchan,nchan),dtype=self.CType)
        # self.K1_XX=self.KernelMat1[0]
        # self.K1_YY=self.K1_XX
        # import pylab
        # pylab.figure(0)
        # pylab.clf()
        # pylab.figure(1)
        # pylab.clf()
        # pylab.figure(0)
         
        


        for iDir in range(NDir):
            
            K=self.PM.predictKernelPolCluster(self.DicoData,self.SM,iDirection=iDir,ApplyTimeJones=ApplyTimeJones)
            #K=self.PM.predictKernelPolCluster(self.DicoData,self.SM,iDirection=iDir)#,ApplyTimeJones=ApplyTimeJones)
            #K*=-1
            T.timeit("Calc K0")


                #gc.collect()
                #print gc.garbage


            # if (iDir==31)&(self.iAnt==51):
            #     ifile=0
            #     while True:
            #         fname="png/Kernel.%5.5i.npy"%ifile
            #         if not(os.path.isfile(fname)) :
            #             np.save(fname,K)
            #             break
            #         ifile+=1

            K_XX=K[:,:,0]
            K_YY=K[:,:,3]
            if self.PolMode=="Scalar":
                K_XX=(K_XX+K_YY)/2.
                K_YY=K_XX

            self.K_XX_AllChan[iDir,:,:]=K_XX
            self.K_YY_AllChan[iDir,:,:]=K_YY
            #self.K_XX.append(K_XX)
            #self.K_YY.append(K_YY)



        #     ######################
        #     # K1=self.PM.predictKernelPolCluster(self.DicoData,SM,iDirection=iDir)#,ApplyTimeJones=ApplyTimeJones)
        #     K1=self.PM.predictKernelPolCluster(self.DicoData,self.SM,iDirection=iDir,ApplyTimeJones=ApplyTimeJones,ForceNoDecorr=True)

        #     A0=self.DicoData["A0"]
        #     A1=self.DicoData["A1"]
        #     ind=np.arange(K1.shape[0])#np.where((A0==0)&(A1==26))[0]
        #     d1=K[ind,0,0] 
        #     d0=K1[ind,0,0]
        #     #op0=np.abs
        #     op0=np.real
        #     #op1=np.imag
        #     pylab.figure(0)
        #     pylab.subplot(1,NDir,iDir+1)
        #     pylab.plot(op0(d0))
        #     pylab.plot(op0(d1))
        #     #pylab.plot(op0(d1)/op0(d0))
        #     pylab.ylim(-100,100)
        #     pylab.draw()
        #     pylab.show(False)

        #     op1=np.angle
        #     pylab.figure(1)
        #     pylab.subplot(1,NDir,iDir+1)
        #     pylab.plot(op1(d0))
        #     pylab.plot(op1(d1))
        #     #pylab.plot(op1(d1)-op1(d0))
        #     pylab.ylim(-np.pi,np.pi)

        #     # pylab.subplot(2,1,2)
        #     # #pylab.plot(op1(d0))
        #     # pylab.plot(op1(d1*d0.conj()))#,ls="--")
        #     # #pylab.plot(op1(d0*d1.conj()),ls="--")
        #     # #pylab.ylim(-1,1)
        #     pylab.draw()
        #     pylab.show(False)
            
        # #     K1_XX=K1[:,:,0]
        # #     K1_YY=K1[:,:,3]
        # #     if self.PolMode=="Scalar":
        # #         K1_XX=(K1_XX+K1_YY)/2.
        # #         K1_YY=K1_XX

        # #     self.K1_XX[iDir,:,:]=K1_XX
        # #     self.K1_YY[iDir,:,:]=K1_YY
        # #     #self.K_XX.append(K_XX)
        # #     #self.K_YY.append(K_YY)

        # #     del(K1,K1_XX,K1_YY)
        # #     del(K,K_XX,K_YY)
        # stop


        # 
        #stop
        #gc.collect()
        self.HasKernelMatrix=True
        T.timeit("stuff 4")

    def SelectChannelKernelMat(self):
        self.K_XX=self.K_XX_AllChan[:,:,self.ch0:self.ch1]
        self.K_YY=self.K_YY_AllChan[:,:,self.ch0:self.ch1]

        


        NDir=self.SM.NDir
        for iDir in range(NDir):
            
            K=self.K_XX[iDir,:,:]

            indRow,indChan=np.where(K==0)
            self.DicoData["flags"][indRow,indChan,:]=1
        DicoData=self.DicoData
        nr,nch=K.shape
        flags_flat=np.rollaxis(DicoData["flags"],2).reshape(self.NJacobBlocks_X,nr*nch*self.NJacobBlocks_Y)
        DicoData["flags_flat"][flags_flat]=1


        self.DataAllFlagged=False
        NP,_=DicoData["flags_flat"].shape
        for ipol in range(NP):
            f=(DicoData["flags_flat"][ipol]==0)
            ind=np.where(f)[0]
            if ind.size==0: 
                self.DataAllFlagged=True
                continue
            fracFlagged=ind.size/float(f.size)
            if fracFlagged<0.2:#ind.size==0:
                self.DataAllFlagged=True


        #print "SelectChannelKernelMat",np.count_nonzero(DicoData["flags_flat"]),np.count_nonzero(DicoData["flags"])



    def GiveData(self,DATA,iAnt,rms=0.):
        
        #DicoData=NpShared.SharedToDico(self.SharedDataDicoName)
        if self.SharedDicoDescriptors["SharedAntennaVis"]==None:
            #print "     COMPUTE DATA"
            DicoData={}
            ind0=np.where(DATA['A0']==iAnt)[0]
            ind1=np.where(DATA['A1']==iAnt)[0]
            DicoData["A0"] = np.concatenate([DATA['A0'][ind0], DATA['A1'][ind1]])
            DicoData["A1"] = np.concatenate([DATA['A1'][ind0], DATA['A0'][ind1]])
            D0=DATA['data'][ind0,self.ch0:self.ch1]
            D1=DATA['data'][ind1,self.ch0:self.ch1].conj()
            c1=D1[:,:,1].copy()
            c2=D1[:,:,2].copy()
            D1[:,:,1]=c2
            D1[:,:,2]=c1
            DicoData["data"] = np.concatenate([D0, D1])
            DicoData["indOrig"] = ind0
            DicoData["indOrig1"] = ind1
            DicoData["uvw"]  = np.concatenate([DATA['uvw'][ind0], -DATA['uvw'][ind1]])
            if "UVW_dt" in DATA.keys():
                DicoData["UVW_dt"]  = np.concatenate([DATA["UVW_dt"][ind0], -DATA["UVW_dt"][ind1]])

            if "W" in DATA.keys():
                DicoData["W"] = np.concatenate([DATA['W'][ind0,self.ch0:self.ch1], DATA['W'][ind1,self.ch0:self.ch1]])

            # DicoData["IndexTimesThisChunk"]=np.concatenate([DATA["IndexTimesThisChunk"][ind0], DATA["IndexTimesThisChunk"][ind1]]) 
            # DicoData["UVW_RefAnt"]=DATA["UVW_RefAnt"][it0:it1]

            if "Kp" in DATA.keys():
                 DicoData["Kp"]=DATA["Kp"]

            D0=DATA['flags'][ind0,self.ch0:self.ch1]
            D1=DATA['flags'][ind1,self.ch0:self.ch1].conj()
            c1=D1[:,:,1].copy()
            c2=D1[:,:,2].copy()
            D1[:,:,1]=c2
            D1[:,:,2]=c1
            DicoData["flags"] = np.concatenate([D0, D1])



            if self.SM.Type=="Image":
                #DicoData["flags_image"]=DicoData["flags"].copy()
                nr,_,_=DicoData["data"].shape
                _,nch,_=DATA['data'].shape
                DicoData["flags_image"]=np.zeros((nr,nch,4),np.bool8)
                #DicoData["flags_image"].fill(0)

            nr,nch,_=DicoData["data"].shape
            
            if self.PolMode=="Scalar":
                d=(DicoData["data"][:,:,0]+DicoData["data"][:,:,-1])/2
                DicoData["data"] = d.reshape((nr,nch,1))
                f=(DicoData["flags"][:,:,0]|DicoData["flags"][:,:,-1])
                DicoData["flags"] = f.reshape((nr,nch,1))
            elif self.PolMode=="IDiag":
                d=DicoData["data"][:,:,0::3]
                DicoData["data"] = d.copy().reshape((nr,nch,2))
                f=DicoData["flags"][:,:,0::3]
                DicoData["flags"] = f.copy().reshape((nr,nch,2))



            DicoData["freqs"]   = DATA['freqs'][self.ch0:self.ch1]
            DicoData["dfreqs"]   = DATA['dfreqs'][self.ch0:self.ch1]
            DicoData["times"] = np.concatenate([DATA['times'][ind0], DATA['times'][ind1]])
            DicoData["infos"] = DATA['infos']

            # nr,nch,_=DicoData["data"].shape

            FlagsShape=DicoData["flags"].shape
            FlagsSize=DicoData["flags"].size
            DicoData["flags"]=DicoData["flags"].reshape(nr,nch,self.NJacobBlocks_X,self.NJacobBlocks_Y)
            DicoData["data"]=DicoData["data"].reshape(nr,nch,self.NJacobBlocks_X,self.NJacobBlocks_Y)

            DicoData["flags_flat"]=np.rollaxis(DicoData["flags"],2).reshape(self.NJacobBlocks_X,nr*nch*self.NJacobBlocks_Y)
            DicoData["data_flat"]=np.rollaxis(DicoData["data"],2).reshape(self.NJacobBlocks_X,nr*nch*self.NJacobBlocks_Y)



            # ###################
            # NJacobBlocks_X=2
            # NJacobBlocks_Y=2
            # F0=np.zeros((nr,nch,NJacobBlocks_X,NJacobBlocks_Y))
            # FlagsShape=F0.shape
            # FlagsSize=F0.size
            # F0=np.arange(FlagsSize).reshape(FlagsShape)
            # F0Flat=np.rollaxis(F0,2).reshape(NJacobBlocks_X,nr*nch*NJacobBlocks_Y)
            # F1=np.rollaxis(F0Flat.reshape(NJacobBlocks_X,nr,nch,NJacobBlocks_Y),0,3).reshape(FlagsShape)
            # print np.count_nonzero((F0-F1).ravel())
            # stop
            # ###################


            del(DicoData["data"])


            if rms!=0.:
                DicoData["rms"]=np.array([rms],np.float32)
                u,v,w=DicoData["uvw"].T
                if self.ResolutionRad!=None:
                    freqs=DicoData["freqs"]
                    wave=np.mean(299792456./freqs)
                    d=np.sqrt((u/wave)**2+(v/wave)**2)
                    FWHMFact=2.*np.sqrt(2.*np.log(2.))
                    sig=self.ResolutionRad/FWHMFact
                    V=(1./np.exp(-d**2*np.pi*sig**2))**2
                    
                    V=V.reshape((V.size,1,1))*np.ones((1,freqs.size,self.npolData))
                else:
                    V=np.ones((u.size,freqs.size,self.npolData),np.float32)
                    
                if "W" in DicoData.keys():
                    W=DicoData["W"]**2
                    W_nrows,W_nch=W.shape
                    W[W==0]=1.e-6
                    V=V/W.reshape((W_nrows,W_nch,1))
                    
                R=rms**2*V
                
                Rinv=1./R
                Weights=W.reshape((W_nrows,W_nch,1))
                
                self.R_flat=np.rollaxis(R,2).reshape(self.NJacobBlocks_X,nr*nch*self.NJacobBlocks_Y)
                self.Rinv_flat=np.rollaxis(Rinv,2).reshape(self.NJacobBlocks_X,nr*nch*self.NJacobBlocks_Y)
                self.Weights_flat=np.rollaxis(Weights,2).reshape(self.NJacobBlocks_X,nr*nch*self.NJacobBlocks_Y)

                self.R_flat=np.require(self.R_flat,dtype=self.CType)
                self.Rinv_flat=np.require(self.Rinv_flat,dtype=self.CType)

                Rmin=np.min(R)
                #Rmax=np.max(R)
                Flag=(self.R_flat>1e3*Rmin)
                DicoData["flags_flat"][Flag]=1
                DicoData["Rinv_flat"]=self.Rinv_flat
                DicoData["R_flat"]=self.R_flat
                DicoData["Weights_flat"]=self.Weights_flat
                

            self.DataAllFlagged=False
            NP,_=DicoData["flags_flat"].shape
            for ipol in range(NP):
                f=(DicoData["flags_flat"][ipol]==0)
                ind=np.where(f)[0]
                
                if ind.size==0: 
                    self.DataAllFlagged=True
                    continue

                fracFlagged=ind.size/float(f.size)
                if fracFlagged<0.2:#ind.size==0:
                    self.DataAllFlagged=True

            DicoData=NpShared.DicoToShared(self.SharedDataDicoName,DicoData)
            self.SharedDicoDescriptors["SharedAntennaVis"]=NpShared.SharedDicoDescriptor(self.SharedDataDicoName,DicoData)
        else:
            DicoData=NpShared.SharedObjectToDico(self.SharedDicoDescriptors["SharedAntennaVis"])
            if rms!=0.:
                self.Rinv_flat=DicoData["Rinv_flat"]
                self.R_flat=DicoData["R_flat"]
                self.Weights_flat=DicoData["Weights_flat"]

            #print "DATA From shared"
            #print np.max(DicoData["A0"])
            #np.save("testA0",DicoData["A0"])
            #DicoData["A0"]=np.load("testA0.npy")
            #DicoData=NpShared.SharedToDico(self.SharedDataDicoName)
            #print np.max(DicoData["A0"])
            #print

            #stop

        if "DicoPreApplyJones" in DATA.keys():
            DicoJonesMatrices={}
            ind0=DicoData["indOrig"]
            ind1=DicoData["indOrig1"]
            #DicoApplyJones=NpShared.SharedToDico("%sPreApplyJonesFile"%self.IdSharedMem)
            
            DicoJonesMatrices["DicoApplyJones"]=DATA["DicoPreApplyJones"]
            DicoJonesMatrices["DicoApplyJones"]["DicoClusterDirs"]=DATA["DicoClusterDirs"]
            MapTimes=DATA["Map_VisToJones_Time"]
            MapTimesSel=np.concatenate([MapTimes[ind0], MapTimes[ind1]])
            DicoJonesMatrices["DicoApplyJones"]["Map_VisToJones_Time"]=MapTimesSel


            DicoData["DicoPreApplyJones"]=DicoJonesMatrices
            #print DATA["Map_VisToJones_Time"].max()
            #stop

        self.DoTikhonov=False
        #self.GD["CohJones"]["LambdaTk"]=0
        if (self.GD["CohJones"]["LambdaTk"]!=0)&(self.GD["Solvers"]["SolverType"]=="CohJones"):
            self.DoTikhonov=True
            self.LambdaTk=self.GD["CohJones"]["LambdaTk"]
            self.Linv=NpShared.GiveArray("%sLinv"%self.IdSharedMem)
            self.X0=NpShared.GiveArray("%sX0"%self.IdSharedMem)
            

        # DicoData["A0"] = np.concatenate([DATA['A0'][ind0]])
        # DicoData["A1"] = np.concatenate([DATA['A1'][ind0]])
        # D0=DATA['data'][ind0]
        # DicoData["data"] = np.concatenate([D0])
        # DicoData["uvw"]  = np.concatenate([DATA['uvw'][ind0]])
        # DicoData["flags"] = np.concatenate([DATA['flags'][ind0]])
        # DicoData["freqs"]   = DATA['freqs']

        self.DataAllFlagged=False
        NP,_=DicoData["flags_flat"].shape
        for ipol in range(NP):
            f=(DicoData["flags_flat"][ipol]==0)
            ind=np.where(f)[0]
            if ind.size==0: 
                self.DataAllFlagged=True
                continue
            fracFlagged=ind.size/float(f.size)
            if fracFlagged<0.2:#ind.size==0:
                self.DataAllFlagged=True

        DicoData["freqs_full"]   = self.DATA['freqs']
        DicoData["dfreqs_full"]   = self.DATA['dfreqs']

        return DicoData

###########################################
###########################################
###########################################


def testPredict():
    import pylab
    VS=ClassVisServer.ClassVisServer("../TEST/0000.MS/")

    MS=VS.MS
    SM=ClassSM.ClassSM("../TEST/ModelRandom00.txt.npy")
    SM.Calc_LM(MS.rac,MS.decc)




    nd=SM.NDir
    npol=4
    na=MS.na
    Gains=np.zeros((na,nd,npol),dtype=np.complex64)
    Gains[:,:,0]=1
    Gains[:,:,-1]=1
    #Gains+=np.random.randn(*Gains.shape)*0.5+1j*np.random.randn(*Gains.shape)
    Gains=np.random.randn(*Gains.shape)+1j*np.random.randn(*Gains.shape)
    #Gains[:,1,:]=0
    #Gains[:,2,:]=0
    #g=np.random.randn(*(Gains[:,:,0].shape))+1j*np.random.randn(*(Gains[:,:,0].shape))
    #g=g.reshape((na,nd,1))
    #Gains*=g

    DATA=VS.GiveNextVis(0,50)

    # Apply Jones
    PM=ClassPredict(Precision="S")
    DATA["data"]=PM.predictKernelPolCluster(DATA,SM,ApplyJones=Gains)
    
    ############################
    PolMode="IFull"#"Scalar"
    iAnt=10
    JM=ClassJacobianAntenna(SM,iAnt,PolMode=PolMode)
    JM.setDATA(DATA)
    JM.CalcKernelMatrix()
    if PolMode=="Scalar":
        Gains=Gains[:,:,0].reshape((na,nd,1))

    Jacob= JM.CalcJacobianAntenna(Gains)

    y=JM.GiveDataVec()
    
#    Gain=JM.ThisGain[:,1,:]
    predict=JM.J_x(Gains[iAnt])

    pylab.figure(1)
    pylab.clf()
    pylab.subplot(2,1,1)
    pylab.plot(predict.real)
    pylab.plot(y.real)
    pylab.plot((predict-y).real)
    pylab.subplot(2,1,2)
    pylab.plot(predict.imag)
    pylab.plot(y.imag)
    pylab.plot((predict-y).imag)
    pylab.draw()
    pylab.show(False)

    pylab.figure(2)
    pylab.clf()
    pylab.subplot(1,2,1)
    pylab.imshow(np.abs(JM.JHJ),interpolation="nearest")
    pylab.subplot(1,2,2)
    pylab.imshow(np.abs(JM.JHJinv),interpolation="nearest")
    pylab.draw()
    pylab.show(False)

    pylab.figure(3)
    pylab.clf()
    pylab.imshow(np.abs(JM.Jacob)[0:20],interpolation="nearest")
    pylab.draw()
    pylab.show(False)

    stop    
    
