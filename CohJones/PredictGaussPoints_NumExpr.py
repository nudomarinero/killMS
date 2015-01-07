import numpy as np
from pyrap.tables import table
from ClassMS import ClassMS
from ClassSM import ClassSM
from ClassTimeIt import ClassTimeIt
import numexpr as ne
#import ModNumExpr
from progressbar import ProgressBar
import multiprocessing
import ModLinAlg
#ne.evaluate=lambda sin: ("return %s"%sin)


class ClassPredict():
    def __init__(self,Precision="D"):
        self.NCPU=6
        ne.set_num_threads(self.NCPU)
        if Precision=="D":
            self.CType=np.complex128
            self.FType=np.float64
        if Precision=="S":
            self.CType=np.complex64
            self.FType=np.float32

    def predictKernelPolCluster(self,DicoData,SM,iDirection=None,ApplyJones=None):
        self.DicoData=DicoData
        self.SourceCat=SM.SourceCat

        freq=DicoData["freqs"]
        times=DicoData["times"]
        nf=freq.size
        na=DicoData["infos"][0]

        nrows=DicoData["A0"].size
        DataOut=np.zeros((nrows,nf,4),np.complex64)
        if nrows==0: return DataOut

        self.freqs=freq
        self.wave=299792458./self.freqs

        if iDirection!=None:
            ListDirection=[iDirection]
        else:
            ListDirection=range(SM.NDir)


        A0=DicoData["A0"]
        A1=DicoData["A1"]
        if ApplyJones!=None:
            na,NDir,_=ApplyJones.shape
            Jones=np.swapaxes(ApplyJones,0,1)
            Jones=Jones.reshape((NDir,na,4))
            JonesH=ModLinAlg.BatchH(Jones)

        for iCluster in ListDirection:
            ColOutDir=self.PredictDirSPW(iCluster)
            
            # print iCluster,ListDirection
            # print ColOutDir.shape
            # ColOutDir.fill(0)
            # print ColOutDir.shape
            # ColOutDir[:,:,0]=1
            # print ColOutDir.shape
            # ColOutDir[:,:,3]=1
            # print ColOutDir.shape

            # Apply Jones
            if ApplyJones!=None:

                J=Jones[iCluster]
                JH=JonesH[iCluster]
                for ichan in range(nf):
                    ColOutDir[:,ichan,:]=ModLinAlg.BatchDot(J[A0,:],ColOutDir[:,ichan,:])
                    ColOutDir[:,ichan,:]=ModLinAlg.BatchDot(ColOutDir[:,ichan,:],JH[A1,:])

            if "DicoBeam" in DicoData.keys():
                D=DicoData["DicoBeam"]
                Beam=D["Beam"]
                BeamH=D["BeamH"]
                lt0,lt1=D["t0"],D["t1"]
                for it in range(lt0.size):
                    t0,t1=lt0[it],lt1[it]
                    ind=np.where((times>t0)&(times<t1))[0]
                    if ind.size==0: continue
                    data=ColOutDir[ind]
                    A0sel=A0[ind]
                    A1sel=A1[ind]
                    for ichan in range(nf):
                        J=Beam[it,iCluster,:,ichan,:,:].reshape((na,4))
                        JH=Beam[it,iCluster,:,ichan,:,:].reshape((na,4))
                        data[:,ichan,:]=ModLinAlg.BatchDot(J[A0sel,:],data[:,ichan,:])
                        data[:,ichan,:]=ModLinAlg.BatchDot(data[:,ichan,:],JH[A1sel,:])
                

            DataOut+=ColOutDir


        return DataOut


    def PredictDirSPW(self,idir):

        ind0=np.where(self.SourceCat.Cluster==idir)[0]
        NSource=ind0.size
        SourceCat=self.SourceCat[ind0]
        freq=self.freqs
        pi=np.pi
        wave=self.wave#[0]

        uvw=self.DicoData["uvw"]

        U=self.FType(uvw[:,0].flatten().copy())
        V=self.FType(uvw[:,1].flatten().copy())
        W=self.FType(uvw[:,2].flatten().copy())

        U=U.reshape((1,U.size,1,1))
        V=V.reshape((1,U.size,1,1))
        W=W.reshape((1,U.size,1,1))

        
        #ColOut=np.zeros(U.shape,dtype=complex)
        f0=self.CType(2*pi*1j/wave)
        f0=f0.reshape((1,1,f0.size,1))

        rasel =SourceCat.ra
        decsel=SourceCat.dec
        
        TypeSources=SourceCat.Type
        Gmaj=SourceCat.Gmaj.reshape((NSource,1,1,1))
        Gmin=SourceCat.Gmin.reshape((NSource,1,1,1))
        Gangle=SourceCat.Gangle.reshape((NSource,1,1,1))

        RefFreq=SourceCat.RefFreq.reshape((NSource,1,1,1))
        alpha=SourceCat.alpha.reshape((NSource,1,1,1))

        fI=SourceCat.I.reshape((NSource,1,1))
        fQ=SourceCat.Q.reshape((NSource,1,1))
        fU=SourceCat.U.reshape((NSource,1,1))
        fV=SourceCat.V.reshape((NSource,1,1))
        Sky=np.zeros((NSource,1,1,4),np.complex64)
        Sky[:,:,:,0]=(fI+fQ);
        Sky[:,:,:,1]=(fU+1j*fV);
        Sky[:,:,:,2]=(fU-1j*fV);
        Sky[:,:,:,3]=(fI-fQ);

        Ssel  =Sky*(freq.reshape((1,1,freq.size,1))/RefFreq)**(alpha)
        Ssel=self.CType(Ssel)




        Ll=self.FType(SourceCat.l)
        Lm=self.FType(SourceCat.m)
        
        l=Ll.reshape(NSource,1,1,1)
        m=Lm.reshape(NSource,1,1,1)
        nn=self.FType(np.sqrt(1.-l**2-m**2)-1.)
        f=Ssel
        Ssel[Ssel==0]=1e-10

        KernelPha=ne.evaluate("f0*(U*l+V*m+W*nn)").astype(self.CType)
        indGauss=np.where(TypeSources==1)[0]

        NGauss=indGauss.size



        if NGauss>0:
            ang=Gangle[indGauss].reshape((NGauss,1,1,1))
            SigMaj=Gmaj[indGauss].reshape((NGauss,1,1,1))
            SigMin=Gmin[indGauss].reshape((NGauss,1,1,1))
            WaveL=wave
            SminCos=SigMin*np.cos(ang)
            SminSin=SigMin*np.sin(ang)
            SmajCos=SigMaj*np.cos(ang)
            SmajSin=SigMaj*np.sin(ang)
            up=ne.evaluate("U*SminCos-V*SminSin")
            vp=ne.evaluate("U*SmajSin+V*SmajCos")
            const=-(2*(pi**2)*(1/WaveL)**2)#*fudge
            const=const.reshape((1,1,freq.size,1))
            uvp=ne.evaluate("const*((U*SminCos-V*SminSin)**2+(U*SmajSin+V*SmajCos)**2)")
            #KernelPha=ne.evaluate("KernelPha+uvp")
            KernelPha[indGauss,:,:,:]+=uvp[:,:,:,:]
            print "CACA"


        LogF=np.log(f)
        
        Kernel=ne.evaluate("exp(KernelPha+LogF)")

        #Kernel=ne.evaluate("f*exp(KernelPha)").astype(self.CType)

        if Kernel.shape[0]>1:
            ColOut=ne.evaluate("sum(Kernel,axis=0)").astype(self.CType)
        else:
            ColOut=Kernel[0]

        return ColOut
