"""CPU deployment adapter: per-Linear PyTorch dynamic INT8, BF16 activations outside linear layers.
Quantization changes the evaluated deployment. No training or evaluation references used.
"""
import torch
from torch import nn
from torch.ao.nn.quantized.dynamic import Linear as DynamicLinear
from torch.ao.quantization import default_dynamic_qconfig

class BF16DynamicLinear(nn.Module):
    def __init__(self, original):
        super().__init__()
        # Clone to float32 without changing shared embedding/lm_head parameter dtype.
        dense=nn.Linear(original.in_features,original.out_features,bias=original.bias is not None,dtype=torch.float32)
        with torch.no_grad():
            dense.weight.copy_(original.weight)
            if original.bias is not None:dense.bias.copy_(original.bias)
        dense.qconfig=default_dynamic_qconfig
        self.linear=DynamicLinear.from_float(dense)
        self.in_features=original.in_features
        self.out_features=original.out_features
    def forward(self,x):
        return self.linear(x.float()).to(x.dtype)

def quantize_linears(module):
    count=0
    for name,child in list(module.named_children()):
        if isinstance(child,nn.Linear):
            setattr(module,name,BF16DynamicLinear(child));count+=1
        else:count+=quantize_linears(child)
    return count
