"""Consistent SQLite backup via online backup API, not copying a live WAL database."""
import argparse,sqlite3,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('destination');args=p.parse_args()
path=Path(args.destination);path.parent.mkdir(parents=True,exist_ok=True)
source=sqlite3.connect(os.environ.get('DATABASE_PATH','data/pcl.sqlite3'))
target=sqlite3.connect(path);source.backup(target);target.close();source.close();path.chmod(0o600)
print('Backup completed')
