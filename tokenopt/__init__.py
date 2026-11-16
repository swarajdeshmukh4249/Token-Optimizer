"""Adaptive multimodal token optimizer (DS-II CS2308, Group 6).

    from tokenopt import optimize_image, load_image, plan_followup
"""
from .adapters.chat import plan_followup, plan_for_chat
from .image_opt import load_image, optimize_image
from .video_opt import optimize_video, read_video

__version__ = "0.1.0"
__all__ = ["load_image", "optimize_image", "optimize_video", "read_video",
           "plan_for_chat", "plan_followup", "__version__"]
