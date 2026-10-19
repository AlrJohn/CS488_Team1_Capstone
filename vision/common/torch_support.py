"""Optional workstation-only PyTorch support; never needed by the Hailo runner."""
import os
from pathlib import Path


def setup():
    root=Path(__file__).resolve().parents[1]/'.cache'
    for key,folder in [('YOLO_CONFIG_DIR','ultralytics'),('MPLCONFIGDIR','matplotlib'),('TORCH_HOME','torch')]:
        p=root/folder;p.mkdir(parents=True,exist_ok=True);os.environ[key]=str(p)
    os.environ['ULTRALYTICS_SAFE_LOAD']='true'
    os.environ['TORCH_FORCE_WEIGHTS_ONLY_LOAD']='1'
    os.environ['YOLO_AUTOINSTALL']='false'
    os.environ['WANDB_MODE']='disabled'
    import torch
    from ultralytics import settings
    from ultralytics.nn.tasks import _SafeLoad
    if not _SafeLoad.SUPPORTED or not _SafeLoad.restricted():raise RuntimeError('Restricted checkpoint loader required')
    settings.update({key:False for key in ('sync','wandb','mlflow','clearml','comet','neptune','tensorboard','dvc','raytune') if key in settings})
    torch.set_num_threads(4)
    return torch


def raw_model(path):
    torch=setup()
    from ultralytics import YOLO
    net=YOLO(str(path)).model.float().eval()
    net.fuse(verbose=False)
    head=net.model[-1]
    if (head.nc,head.nm,head.reg_max)!=(1,32,16):raise ValueError('Wrong checkpoint architecture')
    class RawHeads(torch.nn.Module):
        def __init__(self):
            super().__init__();self.net=net;self.values={}
            for i,stride in enumerate((8,16,32)):
                for kind,layers in [('box',head.cv2),('score',head.cv3),('coeff',head.cv4)]:
                    name=f'{kind}_s{stride}'
                    layers[i].register_forward_hook(lambda module,args,value,key=name:self.values.__setitem__(key,value))
            head.proto.register_forward_hook(lambda module,args,value:self.values.__setitem__('proto',value))
        def forward(self,x):
            self.net(x)
            return tuple(self.values[name] for name in OUTPUT_NAMES)
    return RawHeads().eval()


OUTPUT_NAMES=[f'{kind}_s{stride}' for stride in (8,16,32) for kind in ('box','score','coeff')]+['proto']
