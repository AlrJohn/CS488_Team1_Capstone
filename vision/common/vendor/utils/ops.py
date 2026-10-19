import numpy as np
from ...instance_memory import assign_minimum

def xywh2ltwh(x):
    y=np.copy(x)
    y[...,0]=x[...,0]-x[...,2]/2
    y[...,1]=x[...,1]-x[...,3]/2
    return y

def linear_sum_assignment(cost):
    if cost.shape[0]>cost.shape[1]:
        pairs=[(b,a) for a,b in assign_minimum(cost.T.tolist())]
    else:pairs=assign_minimum(cost.tolist())
    return tuple(np.array(v,dtype=int) for v in zip(*pairs)) if pairs else (np.array([],int),np.array([],int))
