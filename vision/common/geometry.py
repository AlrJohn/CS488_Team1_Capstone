"""Image and box coordinates shared by ONNX and Hailo inference."""
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class Transform:
    original: tuple
    network: tuple
    gain: float
    padding: tuple


def letterbox(bgr, shape=(320,640)):
    h,w=bgr.shape[:2];nh,nw=shape
    gain=min(nh/h,nw/w)
    rh,rw=round(h*gain),round(w*gain)
    left,top=round((nw-rw)/2-.1),round((nh-rh)/2-.1)
    resized=cv2.resize(bgr,(rw,rh),interpolation=cv2.INTER_LINEAR) if (rw,rh)!=(w,h) else bgr
    padded=cv2.copyMakeBorder(resized,top,nh-rh-top,left,nw-rw-left,cv2.BORDER_CONSTANT,value=(114,114,114))
    return cv2.cvtColor(padded,cv2.COLOR_BGR2RGB),Transform((h,w),shape,gain,(left,top))


class Boxes:
    """NumPy-only subset of Ultralytics Boxes used by the frozen ByteTracker."""
    def __init__(self,data,shape):
        self.data=np.asarray(data,dtype=np.float32).reshape(-1,6)
        self.orig_shape=tuple(shape)
    def __len__(self):return len(self.data)
    def __getitem__(self,index):return Boxes(self.data[index],self.orig_shape)
    @property
    def xyxy(self):return self.data[:,:4]
    @property
    def xywh(self):
        x=self.xyxy;y=np.empty_like(x)
        y[:,:2]=(x[:,:2]+x[:,2:])/2;y[:,2:]=x[:,2:]-x[:,:2]
        return y
    @property
    def conf(self):return self.data[:,4]
    @property
    def cls(self):return self.data[:,5]


def restore_view(config,shape):
    h,w=shape
    r=config['normalized_xywh']
    if len(r)!=4 or not all(type(v) in (float,int) and np.isfinite(v) and 0<=v<=1 for v in r) or min(r[2:])<=0 or r[0]+r[2]>1.00001 or r[1]+r[3]>1.00001:
        raise ValueError('Invalid normalized count ROI')
    x,y,rw,rh=[round(a*b) for a,b in zip(r,(w,h,w,h))]
    rw,rh=min(rw,w-x),min(rh,h-y)
    if min(rw,rh)<40:raise ValueError('Count ROI too small')
    return [x,y,rw,rh]
