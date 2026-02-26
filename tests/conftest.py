"""pytest 설정: 프로젝트 루트를 sys.path에 추가"""
import sys
from pathlib import Path

root = Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
