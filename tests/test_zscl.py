import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.main import main


def test_zscl():
    sys.argv = ['mammoth',
                '--model',
                'zscl',
                '--dataset',
                'seq-eurosat-rgb',
                '--non_verbose',
                '1',
                '--num_workers',
                '0',
                '--clip_backbone',
                'ViT-B/16',
                '--debug_mode',
                '1']

    main()
