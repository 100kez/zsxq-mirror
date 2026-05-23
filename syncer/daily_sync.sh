#!/bin/bash
# 知识星球增量同步 — 由 cron 调用
cd /root/quant_project
SINCE=$(date -d '3 days ago' +%Y-%m-%d)
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 开始同步，起始日期: $SINCE ==="
/usr/bin/python3 -u syncer/sync_zsxq.py --since "$SINCE"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 同步结束 ==="

# 仅 20 点那一轮跑 AI 盘后总结（早盘和午盘没意义）
HOUR=$(date +%H)
if [ "$HOUR" = "20" ]; then
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') 开始 AI 盘后总结 ==="
    /usr/bin/python3 -u manage.py daily_summary
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') 盘后总结结束 ==="
fi
