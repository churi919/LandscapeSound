"""Explicit first-download step; later app use is offline."""
import local_config
import os
os.environ['HF_HUB_OFFLINE'] = '0'
from analyzer import load_models

if __name__ == '__main__':
    models = load_models()
    print('Both local models are ready; inference device:', models[0])
