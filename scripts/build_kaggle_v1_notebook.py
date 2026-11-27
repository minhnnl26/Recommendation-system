"""Build a self-contained notebook from reviewed training modules, with no outputs."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    training = ROOT / "recommender/training"
    embedded = {
        name: (training / name).read_text()
        for name in (
            "data_utils.py",
            "prepare.py",
            "train.py",
            "predict.py",
            "quick_v1.py",
            "requirements-kaggle.txt",
            "configs/v1.json",
        )
    }
    cells = []

    def cell(kind, source):
        value = {
            "cell_type": kind,
            "metadata": {},
            "source": source.splitlines(keepends=True),
        }
        if kind == "code":
            value.update(execution_count=None, outputs=[])
        cells.append(value)

    cell(
        "markdown",
        """# Music4All-Onion — Kaggle V1, kết quả đầu tiên
Chỉ attach **userid_trackid_count.tsv.bz2** và **id_genres_tf-idf.tsv.bz2**. Không cần code ZIP, Git clone, Supabase, original MP3 hoặc lyrics. Bật Internet để cài dependencies; CPU là mặc định. Python 3.10–3.12.

V1 đọc tối đa 500.000 dòng đầu nguồn, lấy tối đa 1.000 user đầu tiên, tối đa 100 cặp/user; giữ user có >=5 cặp. Đây là sample theo thứ tự file, không ngẫu nhiên, không đại diện toàn dataset. Catalog genre vẫn giữ đầy đủ ID. Fit 32 factors × 8 iterations; eval tối đa 100 user/split. Không cam kết thời gian Kaggle trước khi chạy thật.

So sánh popularity, content, ALS, hybrid. Hash leave-two-out **không phải temporal**. Kết quả chỉ là baseline V1; metric có thể thấp hoặc bằng 0 và không được sửa số liệu. Không có tên bài/audio trong input.
""",
    )
    cell(
        "code",
        "import sys, json, subprocess, os\nfrom pathlib import Path\nassert (3,10) <= sys.version_info[:2] < (3,13), 'Use Python 3.10–3.12'\nos.environ['OPENBLAS_NUM_THREADS']='1'\nos.environ['OMP_NUM_THREADS']='4'\nCODE=Path('/kaggle/working/music4all-v1-code')\nCODE.mkdir(parents=True, exist_ok=True)\nEMBEDDED = "
        + repr(embedded)
        + "\nfor name, text in EMBEDDED.items():\n    target=CODE/name\n    target.parent.mkdir(parents=True, exist_ok=True)\n    target.write_text(text, encoding='utf-8')\nsubprocess.run([sys.executable,'-m','pip','install','-r',str(CODE/'requirements-kaggle.txt')],check=True)\nprint('Code ready. Training runs in a fresh subprocess, not in the notebook kernel.')\n",
    )
    cell(
        "code",
        """# Auto-find the two attached input files. If multiple copies exist, set paths manually.
from datetime import datetime, timezone
def unique_input(name):
    matches=list(Path('/kaggle/input').rglob(name))
    assert len(matches)==1, f'Attach exactly one {name}; found {len(matches)}'
    return matches[0]
COUNT=unique_input('userid_trackid_count.tsv.bz2')
GENRE=unique_input('id_genres_tf-idf.tsv.bz2')
RUN_ID=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
RUN=Path('/kaggle/working')/f'music4all-v1-{RUN_ID}'
SCRATCH=Path('/tmp')/f'music4all-v1-{RUN_ID}'
INPUT=SCRATCH/'attached'
INPUT.mkdir(parents=True)
(INPUT/COUNT.name).symlink_to(COUNT)
(INPUT/GENRE.name).symlink_to(GENRE)
CONFIG=CODE/'configs/v1.json'
settings=json.loads(CONFIG.read_text())
# Keep defaults for your first run. Do not choose parameters by looking at test metrics.
print({key:settings[key] for key in ['max_source_rows','sample_users','max_pairs_per_user','factors','iterations','eval_users']})
""",
    )
    cell(
        "code",
        """subprocess.run([
    sys.executable,str(CODE/'quick_v1.py'),
    '--onion-root',str(INPUT),'--output',str(RUN),
    '--scratch',str(SCRATCH/'processing'),'--config',str(CONFIG)
],check=True)
print((RUN/'metrics_summary.csv').read_text())
""",
    )
    cell(
        "code",
        """# Display a clear table without requiring pandas or importing numpy in this kernel.
import csv, html
from IPython.display import HTML, display
rows=list(csv.reader((RUN/'metrics_summary.csv').open()))
table='<table>'+''.join('<tr>'+''.join(f'<td>{html.escape(value)}</td>' for value in row)+'</tr>' for row in rows)+'</table>'
display(HTML(table))
print('V1 source-order sample, hash split; NOT a full-dataset or temporal result.')
""",
    )
    cell(
        "code",
        """users=json.loads((RUN/'prepared/user_ids.json').read_text())
result=subprocess.run([sys.executable,str(CODE/'predict.py'),'--run',str(RUN),'--user-id',users[0],'--limit','10'],check=True,capture_output=True,text=True)
recommendations=json.loads(result.stdout)
(RUN/'recommendations_example.json').write_text(json.dumps(recommendations,ensure_ascii=False,indent=2))
print(result.stdout)
""",
    )
    cell(
        "code",
        """# Download one ZIP containing model, mappings, matrices, configuration and results.
import shutil
from IPython.display import FileLink
archive=shutil.make_archive(str(RUN), 'zip', root_dir=RUN.parent, base_dir=RUN.name)
print('Save Version → Save & Run All to retain outputs. Download before closing.')
display(FileLink(archive))
print('Send: metrics_summary.csv + config.json + v1_sampling.json + screenshot of the table.')
print('Send model ZIP privately to backend; do not commit raw model/history/dataset to GitHub.')
""",
    )
    cell(
        "markdown",
        """## Nếu lỗi / làm gì tiếp
- Không tìm thấy file: Add Input chứa đúng hai tên file .tsv.bz2 rồi Run All; không dùng file ZIP chưa giải nén.
- Lỗi pip/mạng: bật Internet. Nếu Python 3.13+, chọn môi trường 3.10–3.12 tương thích pins.
- Có kết quả V1 trước, sau đó mới tăng sample hoặc làm temporal với timestamp trong notebook chính.
- Backend tích hợp artifact ALS và mapping; frontend hiển thị Track ID khi thiếu tên, chưa bật Play khi không có audio.
- Không sửa test metric để đẹp; chọn cấu hình bằng validation, giữ test cho báo cáo cuối.
""",
    )
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    target = ROOT / "recommender/notebooks/music4all_kaggle_v1_quick.ipynb"
    target.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Built", target.name)


if __name__ == "__main__":
    build()
