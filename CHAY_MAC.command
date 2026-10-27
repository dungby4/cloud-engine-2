#!/bin/zsh
cd "$(dirname "$0")"
node scripts/start-live.js
read -k 1 '?Nhấn phím bất kỳ để đóng...'
