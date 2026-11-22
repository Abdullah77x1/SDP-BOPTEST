"""Separately qualified G146 continuation. No import-time execution."""
from pathlib import Path
HOME=Path(__file__).resolve().parent
ROOT=HOME.parent
VERSION='SDP_B2I_1.0.0'
IDS=['B1V01_G146_'+arm for arm in ('NREF','C15','C45')]
STATE=HOME/'runtime_state'
