"""Add verified Music4All-Onion data slides to the supplied HUST presentation."""

import argparse
import bz2
import csv
import hashlib
import json
from pathlib import Path

from lastfm_eda import ROOT, plt
from PIL import Image, ImageDraw, ImageOps
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Inches, Pt

NAVY = "063561"
BLUE = "1F69A8"
TEAL = "237D78"
RED = "BE1E3C"
INK = "172B3C"
GRAY = "526372"
LIGHT = "EEF3F8"
OUT = ROOT / "docs/presentations"
ASSETS = ROOT / "data/presentations/data_assets"
SOURCE = ROOT / "data/presentations/source_snapshot.pptx"
SOURCE_LABEL = (
    "Nguồn: Music4All-Onion v2 · DOI: 10.5281/zenodo.15394646 · EDA toàn bộ file count"
)


def number(value):
    return f"{value:,}".replace(",", ".")


def percent(value):
    return f"{100 * value:.2f}%".replace(".", ",")


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1024 * 1024):
            sha.update(block)
    return sha.hexdigest()


def text(
    slide,
    value,
    x,
    y,
    w,
    h,
    size=22,
    color=INK,
    bold=False,
    font="Calibri",
    align=PP_ALIGN.LEFT,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.auto_size = MSO_AUTO_SIZE.NONE
    frame.margin_left = frame.margin_right = Inches(0.03)
    frame.margin_top = frame.margin_bottom = Inches(0.02)
    for i, line in enumerate(value.split("\n")):
        p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        p.text = line
        p.alignment = align
        p.font.name = font
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = RGBColor.from_string(color)
        p.space_after = Pt(8)
        p.line_spacing = 1.08
    return box


def reset(slide, title, notes=""):
    for shape in list(slide.shapes):
        shape._element.getparent().remove(shape._element)
    text(slide, title, 0.37, 0.11, 12.25, 0.5, size=28, color="FFFFFF", bold=True)
    text(
        slide,
        SOURCE_LABEL,
        4.2,
        6.54,
        8.65,
        0.22,
        size=9,
        color=GRAY,
        align=PP_ALIGN.RIGHT,
    )
    if notes:
        slide.notes_slide.notes_text_frame.text = notes


def bullets(slide, lines, x, y, w, size=22, gap=0.95, height=0.85):
    for i, line in enumerate(lines):
        text(slide, "•", x, y + i * gap, 0.25, 0.4, size=size, color=RED, bold=True)
        text(slide, line, x + 0.31, y + i * gap, w - 0.31, height, size=size)


def table(slide, rows, x, y, widths, row_heights, size=18):
    shape = slide.shapes.add_table(
        len(rows),
        len(widths),
        Inches(x),
        Inches(y),
        Inches(sum(widths)),
        Inches(sum(row_heights)),
    )
    grid = shape.table
    for col, width in zip(grid.columns, widths):
        col.width = Inches(width)
    for i, (row, height) in enumerate(zip(rows, row_heights)):
        grid.rows[i].height = Inches(height)
        for j, value in enumerate(row):
            cell = grid.cell(i, j)
            cell.text = str(value)
            cell.margin_left = Inches(0.12)
            cell.margin_right = Inches(0.09)
            cell.margin_top = cell.margin_bottom = Inches(0.06)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(
                NAVY if i == 0 else LIGHT if i % 2 else "FFFFFF"
            )
            for p in cell.text_frame.paragraphs:
                p.font.name = "Calibri"
                p.font.size = Pt(size)
                p.font.bold = i == 0
                p.font.color.rgb = RGBColor.from_string("FFFFFF" if i == 0 else INK)
                p.space_after = Pt(0)
    return shape


def picture(slide, path, x, y, w, h):
    with Image.open(path) as im:
        ratio = min(w / im.width, h / im.height)
        dw, dh = im.width * ratio, im.height * ratio
    slide.shapes.add_picture(
        str(path),
        Inches(x + (w - dw) / 2),
        Inches(y + (h - dh) / 2),
        Inches(dw),
        Inches(dh),
    )


def make_charts(metadata, interactions):
    ASSETS.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13})
    top = metadata["top_genres"][:10][::-1]
    fig, ax = plt.subplots(figsize=(8.3, 4.8), layout="constrained")
    ax.barh([row[0] for row in top], [row[1] for row in top], color="#" + BLUE)
    for index, (_, count) in enumerate(top):
        ax.text(count + 280, index, number(count), va="center", fontsize=12)
    ax.set_xlim(0, top[-1][1] * 1.21)
    ax.set_xlabel("Số bài có trọng số genre dương")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.15)
    ax.set_axisbelow(True)
    fig.savefig(ASSETS / "genres_top10.png", dpi=220)
    plt.close(fig)

    coverage = interactions["coverage"]
    keys = ["nonzero_genre", "nonempty_tags", "both_nonempty"]
    labels = ["Có genre", "Có tags", "Có cả hai"]
    fig, ax = plt.subplots(figsize=(8.3, 4.8), layout="constrained")
    x = list(range(3))
    for offset, field, label, color in [
        (-0.18, "track_fraction", "Độ phủ theo bài", BLUE),
        (0.18, "play_fraction", "Độ phủ theo lượt nghe", TEAL),
    ]:
        bars = ax.bar(
            [v + offset for v in x],
            [100 * coverage[k][field] for k in keys],
            width=0.34,
            label=label,
            color="#" + color,
        )
        for bar, key in zip(bars, keys):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1,
                percent(coverage[key][field]),
                ha="center",
                fontsize=10.5,
            )
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 116)
    ax.set_ylabel("Tỷ lệ trong tập có tương tác (%)")
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.12),
        ncol=2,
        fontsize=11,
        frameon=False,
    )
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(ASSETS / "coverage_by_tracks_plays.png", dpi=220)
    plt.close(fig)

    total = metadata["genre_rows"]
    useful = [metadata["genre_tracks_nonzero"], metadata["tag_tracks_nonempty"]]
    empty = [metadata["genre_tracks_zero"], metadata["tag_tracks_empty"]]
    missing = [0, total - metadata["metadata_id_intersection"]]
    fig, ax = plt.subplots(figsize=(8.3, 4.3), layout="constrained")
    left = [0, 0]
    for values, label, color in [
        (useful, "Có feature hữu dụng", BLUE),
        (empty, "Feature rỗng", "A6B4C2"),
        (missing, "Thiếu ID trong file", RED),
    ]:
        values = [100 * v / total for v in values]
        ax.barh(["Genre", "Tags"], values, left=left, label=label, color="#" + color)
        for i, value in enumerate(values):
            if value > 8:
                ax.text(
                    left[i] + value / 2,
                    i,
                    f"{value:.2f}%".replace(".", ","),
                    ha="center",
                    va="center",
                    fontsize=14,
                    color="white" if color != "A6B4C2" else "#172B3C",
                    weight="bold",
                )
        left = [a + b for a, b in zip(left, values)]
    ax.set_xlim(0, 100)
    ax.invert_yaxis()
    ax.set_xlabel("Tỷ lệ trên 109.269 ID trong catalog genre (%)")
    ax.legend(
        loc="lower left", bbox_to_anchor=(0, 1.04), ncol=2, fontsize=10, frameon=False
    )
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(ASSETS / "metadata_completeness.png", dpi=220)
    plt.close(fig)


def new_slide(prs, layout, title, notes):
    slide = prs.slides.add_slide(layout)
    reset(slide, title, notes)
    return slide


def build(source, output):
    metrics = json.loads((ROOT / "docs/eda/music4all-onion/metrics.json").read_text())
    meta, interaction = metrics["metadata"], metrics["interactions"]
    if not interaction:
        raise ValueError("Full interaction audit is required")
    make_charts(meta, interaction)
    prs = Presentation(source)
    if len(prs.slides) != 14:
        raise ValueError("Unexpected source deck; inspect before modifying")
    original = list(prs.slides)
    layout = original[5].slide_layout
    cov = interaction["coverage"]
    # Preserve the introduction wording while fitting its existing text box.
    for paragraph in original[3].shapes[0].text_frame.paragraphs:
        paragraph.space_after = Pt(8)
        paragraph.line_spacing = 1.08
        paragraph.font.size = Pt(24)
        for run in paragraph.runs:
            run.font.size = Pt(24)

    s = original[5]
    reset(
        s,
        "3.1. Dữ liệu nghiên cứu: Music4All-Onion",
        "Nguồn: Music4All-Onion v2 trên Zenodo, DOI 10.5281/zenodo.15394646. "
        "Đã đo trên toàn bộ file genre, tags và interaction count, không lấy mẫu. "
        "Đây là dữ liệu nguồn nhóm nhận, trong đó count và genre TF-IDF đã được tác giả tiền xử lý. "
        "Không mô tả đây là dữ liệu nhóm tự crawl hoặc kết quả mô hình đã huấn luyện.",
    )
    text(
        s,
        "Dữ liệu hành vi kết hợp đặc trưng thể loại trong cùng hệ ID bài hát",
        0.5,
        1.05,
        12.1,
        0.6,
        size=25,
        color=NAVY,
        bold=True,
    )
    for x, value, label in [
        (0.6, number(interaction["users"]), "người dùng"),
        (4.8, number(interaction["tracks"]), "bài có lịch sử nghe"),
        (9.0, number(meta["genre_rows"]), "bài có dòng genre"),
    ]:
        text(s, value, x, 2.02, 3.65, 0.6, size=36, color=BLUE, bold=True)
        text(s, label, x, 2.65, 3.65, 0.48, size=21, color=GRAY)
    bullets(
        s,
        [
            "Interaction: user_id – track_id – count, phục vụ lọc cộng tác.",
            "Nội dung: vector 685 genre và tags, phục vụ content-based.",
            "Các file đã tải chưa chứa timestamp, audio hoặc metadata tên bài đầy đủ.",
        ],
        0.6,
        3.58,
        12.0,
        size=23,
        gap=0.83,
        height=0.72,
    )

    s = original[6]
    reset(
        s,
        "3.2. Dữ liệu nguồn: lịch sử nghe tổng hợp",
        "Các ví dụ trong bảng được lấy nguyên từ hai dòng đầu file count thật. "
        "Mỗi dòng là một cặp user–track và tổng play count. Không có like, skip, "
        "thời lượng thực nghe hoặc thời điểm nghe trong file này.",
    )
    text(
        s,
        "File: userid_trackid_count.tsv.bz2  |  TSV nén BZip2",
        0.52,
        1.05,
        12.1,
        0.45,
        size=20,
        color=GRAY,
    )
    table(
        s,
        [
            ["Trường", "Kiểu", "Ý nghĩa"],
            ["user_id", "ID dạng chuỗi", "Định danh người dùng"],
            ["track_id", "Chuỗi", "Định danh bài hát trong Music4All-Onion"],
            ["count", "Số nguyên dương", "Tổng số lượt người dùng nghe bài"],
        ],
        0.55,
        1.67,
        [2.25, 2.65, 7.25],
        [0.45, 0.48, 0.48, 0.48],
        size=19,
    )
    text(
        s,
        "Hai dòng thực tế trong file nguồn",
        0.55,
        3.86,
        12.0,
        0.42,
        size=22,
        color=NAVY,
        bold=True,
    )
    table(
        s,
        [
            ["user_id", "track_id", "count"],
            ["92915", "2fwmmHiKaZqDUlY0", "1"],
            ["92915", "b4rHYoJ9wWDSZT3M", "1"],
        ],
        0.55,
        4.4,
        [2.25, 7.25, 2.65],
        [0.4, 0.42, 0.42],
        size=18,
    )
    text(
        s,
        "Một dòng là một cặp user–bài hát, không phải một event nghe riêng lẻ.",
        0.55,
        5.97,
        12.1,
        0.4,
        size=21,
        color=RED,
        bold=True,
    )

    added = []
    s = new_slide(
        prs,
        layout,
        "3.3. Dữ liệu nguồn: genre và tags",
        "Genre là feature TF-IDF tác giả đã cung cấp, không phải nhãn nhóm tự dự đoán. "
        "Các giá trị hiển thị được đọc trực tiếp từ dòng đầu file genre, giữ nguyên số. "
        "Tags là chuỗi dictionary Python, được parser an toàn bằng ast.literal_eval. "
        "Không coi mọi tag là thể loại, và không coi TF-IDF là xác suất.",
    )
    added.append(s)
    with bz2.open(
        ROOT / "data/raw/music4all-onion/id_genres_tf-idf.tsv.bz2", "rt"
    ) as f:
        reader = csv.reader(f, delimiter="\t")
        header, first = next(reader), next(reader)
    example = dict(zip(header, first))
    text(s, "GENRE TF-IDF", 0.55, 1.08, 5.9, 0.45, size=23, color=NAVY, bold=True)
    text(s, "id_genres_tf-idf.tsv.bz2", 0.55, 1.61, 5.9, 0.4, size=17, color=GRAY)
    table(
        s,
        [
            ["Cột (trích)", "Giá trị thật"],
            ["id", example["id"]],
            ["pop", example["pop"]],
            ["rock", example["rock"]],
            ["electronic", example["electronic"]],
        ],
        0.55,
        2.15,
        [1.8, 4.05],
        [0.46] * 5,
        size=17,
    )
    text(
        s,
        "• 685 cột genre ngoài cột ID.\n• Một bài có thể thuộc nhiều genre.\n• TF-IDF không phải xác suất.",
        0.55,
        4.78,
        5.85,
        1.35,
        size=20,
    )
    text(s, "TAGS DICTIONARY", 6.85, 1.08, 5.9, 0.45, size=23, color=NAVY, bold=True)
    text(s, "id_tags_dict.tsv.bz2", 6.85, 1.61, 5.85, 0.4, size=17, color=GRAY)
    table(
        s,
        [
            ["Cột", "Giá trị thật"],
            ["id", "0009fFIM1eYThaPg"],
            ["(tag, weight)", "{'pop': 100}"],
        ],
        6.85,
        2.15,
        [1.8, 4.05],
        [0.46, 0.46, 0.68],
        size=17,
    )
    text(
        s,
        "• Cú pháp dictionary Python, không phải JSON.\n• Có cả genre và nhãn cá nhân như “favorites”.\n• Ghép các file bằng ID bài hát.",
        6.85,
        4.1,
        5.85,
        2.0,
        size=20,
    )

    s = new_slide(
        prs,
        layout,
        "3.4. Phân tích chất lượng và làm sạch",
        "Mẫu số biểu đồ là 109.269 ID trong catalog genre. Tags có 109.269 dòng "
        "nhưng chỉ 108.286 ID khác nhau: có 983 dòng lặp ID. Tập tag dương giữa "
        "các dòng lặp không xung đột. Hợp nhất để không đếm track nhiều lần. "
        "27 vector genre toàn 0, 20.194 dictionary tag rỗng; 983 ID genre không "
        "có dòng tags. Đây là các vấn đề khác nhau. File interaction không có "
        "cặp trùng hoặc count không hợp lệ theo bộ kiểm tra hiện tại.",
    )
    added.append(s)
    picture(s, ASSETS / "metadata_completeness.png", 0.43, 1.15, 8.0, 4.66)
    bullets(
        s,
        [
            "27 bài có vector genre toàn 0.",
            "983 dòng tags lặp ID; đã hợp nhất khi thống kê.",
            "20.194 ID có tags rỗng; không đồng nghĩa thiếu dòng.",
            "Kiểm tra checksum, kiểu count và ID trước khi ghép.",
        ],
        8.7,
        1.3,
        4.05,
        size=20,
        gap=1.15,
        height=1.02,
    )
    text(
        s,
        "Có dòng metadata chưa chắc có feature dùng được.",
        0.6,
        5.92,
        12.0,
        0.4,
        size=23,
        bold=True,
        color=RED,
    )

    s = new_slide(
        prs,
        layout,
        "3.5. Phân tích phân bố thể loại",
        "Đếm bài có trọng số dương theo genre trên toàn bộ 109.269 dòng genre, "
        "không chỉ 56.512 bài có interaction. Rock 23.949, pop 20.267, electronic "
        "11.739. Một bài có nhiều nhãn nên tổng số lượt gán nhãn không bằng số bài. "
        "Genre có phân bố lệch; cần đánh giá theo nhóm và diversity, không chỉ accuracy tổng.",
    )
    added.append(s)
    picture(s, ASSETS / "genres_top10.png", 0.4, 1.08, 8.0, 4.98)
    bullets(
        s,
        [
            "Rock, pop và electronic xuất hiện nhiều nhất.",
            "Một bài có thể có nhiều nhãn thể loại.",
            "Cần xét mất cân bằng nhãn và đa dạng khi đánh giá.",
        ],
        8.7,
        1.55,
        4.05,
        size=22,
        gap=1.4,
        height=1.23,
    )
    text(
        s,
        "Phạm vi: toàn catalog genre; không phải bảng xếp hạng lượt nghe.",
        0.6,
        6.12,
        12.0,
        0.3,
        size=16,
        color=GRAY,
    )

    s = new_slide(
        prs,
        layout,
        "3.6. Độ phủ feature trên dữ liệu tương tác",
        f"Đã đo toàn bộ {interaction['pair_rows']:,} cặp, "
        f"{interaction['total_plays']:,} lượt nghe từ sum(count). "
        f"Có genre hữu dụng: {cov['nonzero_genre']['tracks']:,} bài. "
        f"Có cả genre và tags: {cov['both_nonempty']['tracks']:,} bài, "
        "chiếm 80,65% số bài nhưng 97,35% lượt nghe. Lọc bắt buộc tags có thể "
        "thiên về bài phổ biến. Độ thưa ma trận là 99,26%, chưa phải score mô hình.",
    )
    added.append(s)
    picture(s, ASSETS / "coverage_by_tracks_plays.png", 0.38, 1.22, 8.1, 4.78)
    text(
        s,
        percent(cov["nonzero_genre"]["track_fraction"]),
        8.82,
        1.36,
        3.75,
        0.65,
        size=38,
        color=BLUE,
        bold=True,
    )
    text(s, "bài có tương tác có genre hữu dụng", 8.82, 2.08, 3.75, 0.85, size=22)
    bullets(
        s,
        [
            "Chọn genre làm feature chính.",
            "Tags là feature bổ sung; tránh loại quá nhiều bài ít phổ biến.",
        ],
        8.7,
        3.28,
        4.05,
        size=22,
        gap=1.3,
        height=1.15,
    )
    text(
        s,
        "Mẫu số khác nhau: số bài ≠ số lượt nghe. Ma trận user–song có độ thưa 99,26%.",
        0.6,
        6.13,
        12.1,
        0.3,
        size=16,
        color=GRAY,
    )

    s = new_slide(
        prs,
        layout,
        "3.7. Xử lý dữ liệu cho hệ gợi ý dự kiến",
        "Chưa huấn luyện mô hình. Nhánh tương tác cung cấp ma trận sparse và "
        "confidence dự kiến log1p(count); nhánh nội dung dùng genre sau L2 normalization. "
        "Genre TF-IDF là feature cung cấp sẵn, phải chốt giả định thời điểm tồn tại metadata. "
        "Chưa tải timestamp nên không được tuyên bố đã temporal split, hiểu thứ tự nghe "
        "hoặc tính trending theo tuần. Các file đã tải cũng chưa có audio, like/skip/search.",
    )
    added.append(s)
    table(
        s,
        [
            ["Dữ liệu nguồn", "Xử lý dự kiến", "Đầu vào phương pháp"],
            [
                "user_id – track_id – count",
                "Ánh xạ ID; ma trận sparse;\nthử log1p(count)",
                "Lọc cộng tác: ALS",
            ],
            [
                "id – vector genre",
                "Lọc vector rỗng;\nchuẩn hóa L2",
                "Content-based: cosine",
            ],
            ["id – tags dictionary", "Gộp ID lặp; lọc nhãn nhiễu", "Feature bổ sung"],
        ],
        0.55,
        1.2,
        [3.6, 4.65, 3.9],
        [0.48, 0.84, 0.84, 0.72],
        size=20,
    )
    text(s, "Phần đã hoàn thành", 0.6, 4.45, 5.75, 0.45, size=23, color=BLUE, bold=True)
    text(
        s,
        "Kiểm tra nguồn, schema, chất lượng và độ phủ; chưa train mô hình.",
        0.6,
        4.99,
        5.75,
        1.2,
        size=22,
    )
    text(s, "Phần cần bổ sung", 6.85, 4.45, 5.75, 0.45, size=23, color=RED, bold=True)
    text(
        s,
        "Timestamp cho phiên nghe và xu hướng; metadata tên bài và mapping provider.",
        6.85,
        4.99,
        5.75,
        1.2,
        size=22,
    )

    provider = original[13]
    # Retain the original API screenshots, adjusting only the role and section text.
    provider.shapes[0].text_frame.clear()
    provider.shapes[0].text_frame.paragraphs[0].text = ""
    provider.shapes[1].text_frame.clear()
    provider.shapes[1].text_frame.paragraphs[0].text = ""
    text(
        provider,
        "3.8. Nguồn catalog cho ứng dụng",
        0.37,
        0.11,
        12.2,
        0.5,
        size=28,
        color="FFFFFF",
        bold=True,
    )
    text(
        provider,
        "iTunes / Jamendo: metadata và preview/audio, bổ sung cho nhánh ứng dụng",
        0.55,
        1.06,
        12.1,
        0.5,
        size=23,
        color=NAVY,
        bold=True,
    )
    text(
        provider,
        "Chưa mapping ID Music4All-Onion sang provider; không coi API metadata là lịch sử người dùng.",
        0.6,
        6.35,
        12.0,
        0.3,
        size=15,
        color=RED,
    )
    provider.notes_slide.notes_text_frame.text = (
        "Giữ hình response API của bản gốc. Music4All-Onion dùng cho nghiên cứu recommendation; "
        "iTunes/Jamendo dùng cho catalog, search và playback có điều kiện. Chưa có mapping ID "
        "giữa benchmark và provider, chưa tự nhập metadata vào Supabase."
    )

    # Keep the architecture slides while aligning their stated inputs with this dataset.
    for index, replacements in {
        8: {
            "Đầu vào: lượt nghe, thời lượng nghe, thích hoặc lưu bài hát.": "Đầu vào nghiên cứu: user–song và play count từ Music4All-Onion.",
        },
        9: {
            "Biểu diễn bài hát: mã hóa nghệ sĩ, album; dùng TF-IDF cho các trường văn bản phù hợp. ": "Biểu diễn bài hát: dùng vector genre TF-IDF; tags là feature bổ sung.",
            "Hồ sơ người dùng: tổng hợp vector của các bài đã tương tác, ưu tiên bài được thích, nghe lâu và nghe gần đây.": "Hồ sơ người dùng: tổng hợp vector genre từ các bài đã nghe, theo trọng số play count.",
        },
    }.items():
        for shape in original[index].shapes:
            if not shape.has_text_frame:
                continue
            for paragraph in shape.text_frame.paragraphs:
                for old, new in replacements.items():
                    if old in paragraph.text:
                        value = paragraph.text.replace(old, new)
                        font = paragraph.runs[0].font if paragraph.runs else None
                        size = font.size if font and font.size else Pt(24)
                        paragraph.text = value
                        paragraph.font.name = "Calibri"
                        paragraph.font.size = size

    ordered = original[:7] + added + [provider] + original[7:13]
    by_id = {
        slide.slide_id: entry for slide, entry in zip(prs.slides, prs.slides._sldIdLst)
    }
    ordered_entries = [by_id[slide.slide_id] for slide in ordered]
    ids = prs.slides._sldIdLst
    for entry in list(ids):
        ids.remove(entry)
    for entry in ordered_entries:
        ids.append(entry)
    OUT.mkdir(parents=True, exist_ok=True)
    prs.save(output)
    manifest = {
        "source_snapshot_sha256": digest(source),
        "output_sha256": digest(output),
        "source_slide_count": 14,
        "output_slide_count": len(prs.slides),
        "new_slides": len(added),
        "data_slide_numbers": list(range(6, 14)),
        "new_chart_files": [
            "genres_top10.png",
            "metadata_completeness.png",
            "coverage_by_tracks_plays.png",
        ],
        "notes": "Original slides retained; provider slide moved before architecture; "
        "two method descriptions aligned to measured dataset inputs.",
    }
    (OUT / "presentation_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(json.dumps(manifest, indent=2))


def contact_sheet(directory, destination):
    files = sorted(directory.glob("slide_*.png"))
    files = [path for path in files if 6 <= int(path.stem.split("_")[-1]) <= 13]
    thumb_w, thumb_h = 480, 270
    sheet = Image.new(
        "RGB", (thumb_w * 3, (thumb_h + 30) * ((len(files) + 2) // 3)), "#e6e9ed"
    )
    draw = ImageDraw.Draw(sheet)
    for i, path in enumerate(files):
        with Image.open(path) as im:
            thumb = ImageOps.contain(im.convert("RGB"), (thumb_w, thumb_h))
            x, y = (i % 3) * thumb_w, (i // 3) * (thumb_h + 30)
            sheet.paste(thumb, (x, y))
            draw.text((x + 8, y + thumb_h + 6), path.stem, fill="black")
    sheet.save(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUT / "HUST_Music_Recommendation_Data_Updated.pptx",
    )
    parser.add_argument("--contact-sheet", type=Path)
    args = parser.parse_args()
    if args.contact_sheet:
        contact_sheet(args.contact_sheet, OUT / "preview_data_slides.jpg")
    else:
        build(args.source, args.output)
