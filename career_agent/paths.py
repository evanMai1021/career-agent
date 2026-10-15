"""集中声明仓库资源位置，不读取文件或改变当前工作目录。"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = PROJECT_ROOT / "web"
