"""
models.py - gated-attention MIL over frozen UNI2-h features.

Why attention MIL rather than mean pooling or a full transformer:

* The report describes a tumour that may occupy a small fraction of the slide.
  Mean pooling over ~6,000 patches drowns that signal in normal mucosa, fat and
  background. Attention lets the model concentrate on the patches that matter.
* A full self-attention transformer over 6,000-31,000 tokens is quadratic and
  needs far more data than 315 training cases to fit. Gated attention MIL
  (Ilse et al., 2018) has one attention vector, trains on a laptop, and is the
  standard baseline in computational pathology - which also makes it a fair
  reference point to compare against in the thesis.
* The attention weights ARE the explanation. Paired with the level-0 coords
  stored in each H5 file, they paint directly onto the slide, so every
  prediction can be shown with the tissue that produced it.

The trunk is shared across tasks and each task gets a small linear head:
predicting site, grade, stage and nodal status from one representation forces
that representation to encode the findings a report is actually made of, and
it is far more sample-efficient than five separate models on 315 cases.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class GatedAttentionMIL(nn.Module):
    def __init__(self, in_dim=1536, hidden=512, attn_dim=256, tasks=None, dropout=0.25):
        super().__init__()
        self.tasks = tasks or {}
        self.encoder = nn.Sequential(
            nn.Linear(in_dim, hidden), nn.ReLU(), nn.Dropout(dropout),
        )
        # gated attention: tanh branch scores relevance, sigmoid branch gates it
        self.attn_V = nn.Sequential(nn.Linear(hidden, attn_dim), nn.Tanh())
        self.attn_U = nn.Sequential(nn.Linear(hidden, attn_dim), nn.Sigmoid())
        self.attn_w = nn.Linear(attn_dim, 1)
        self.norm = nn.LayerNorm(hidden)
        self.heads = nn.ModuleDict(
            {t: nn.Linear(hidden, len(c)) for t, c in self.tasks.items()}
        )

    def forward(self, x, mask=None, return_attention=False):
        """x: (B, N, in_dim)   mask: (B, N) True where the patch is real."""
        h = self.encoder(x)                                   # (B, N, H)
        a = self.attn_w(self.attn_V(h) * self.attn_U(h)).squeeze(-1)   # (B, N)
        if mask is not None:
            a = a.masked_fill(~mask, float("-inf"))           # padding must not vote
        a = torch.softmax(a, dim=1)
        z = self.norm(torch.bmm(a.unsqueeze(1), h).squeeze(1))  # (B, H)
        logits = {t: head(z) for t, head in self.heads.items()}
        return (logits, a) if return_attention else logits
