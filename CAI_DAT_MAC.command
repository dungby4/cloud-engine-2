#!/bin/zsh
set -e
cd "$(dirname "$0")"
command -v node >/dev/null || { echo 'Cần Node.js 20 trở lên'; exit 1; }
node -e "if(Number(process.versions.node.split('.')[0])<20)process.exit(1)"
python3 -c 'import sys; assert sys.version_info >= (3,9), "Can Python 3.9+"'
npm ci --ignore-scripts --no-audit --no-fund
python3 -m venv python_v79/.venv
python_v79/.venv/bin/python -m pip install websockets==15.0.1
npx playwright install chromium
node scripts/set-windows-defaults.js
echo 'Cài xong. Mở CHAY_MAC.command để chạy.'
read -k 1 '?Nhấn phím bất kỳ để đóng...'
