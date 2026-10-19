"""Fine-tune a can segmenter on a private, separately split YOLO dataset."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, type=Path, help='Private YOLO segmentation YAML with separate train/val/test groups')
    parser.add_argument('--base', type=Path, default=ROOT/'models/can-camera-v1.pt')
    parser.add_argument('--output', required=True, type=Path, help='New ignored run directory; never the shipped models directory')
    parser.add_argument('--device', default='0')
    parser.add_argument('--epochs', type=int, default=80)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to((ROOT/'models').resolve()):
        parser.error('Choose a new output directory outside the shipped models folder.')
    if args.epochs < 1 or not args.base.is_file() or not args.data.is_file():
        parser.error('Positive epochs and existing local data/base files are required.')
    import yaml
    data = yaml.safe_load(args.data.read_text())
    names = data.get('names')
    if names not in ({0:'can'}, {'0':'can'}, ['can']) or not data.get('train') or not data.get('val'):
        parser.error('Use one can class and distinct train/val splits.')
    if data['train'] == data['val'] or (data.get('test') and data['test'] in (data['train'],data['val'])):
        parser.error('Train, validation and test split locations must be different.')
    from common.torch_support import setup
    setup()
    from ultralytics import YOLO
    from ultralytics.nn.tasks import _SafeLoad
    from ultralytics.utils.torch_utils import strip_optimizer
    config = json.loads((ROOT/'configs/training-camera-v1.json').read_text())
    config.update(data=str(args.data.resolve()),epochs=args.epochs,device=args.device,
                  project=str(args.output.resolve().parent),name=args.output.name,exist_ok=False)
    model = YOLO(str(args.base))
    if model.names != {0:'can'} or model.task != 'segment':
        raise ValueError('Base must be a one-class can segmenter.')
    model.train(**config)
    best = args.output/'weights/best.pt'
    target = args.output/'can-candidate.pt'
    with _SafeLoad.loading(best):
        strip_optimizer(best,s=str(target))
    metadata = dict(model=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        base_sha256=hashlib.sha256(args.base.read_bytes()).hexdigest(),classes={'0':'can'},task='segment',
        data_yaml_sha256=hashlib.sha256(args.data.read_bytes()).hexdigest(),test_used=False,
        status='New training candidate; evaluate on held-out groups before replacement')
    target.with_suffix('.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(target)


if __name__ == '__main__':
    main()
