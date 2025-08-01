import os
from collections import defaultdict
from functools import partial
from typing import Any, Dict, List, Tuple, Union

import numpy as np
import torch

def identity_projection(text_actions: List[str]) -> Tuple[List[str], List[bool]]:
    return text_actions, [True] * len(text_actions)